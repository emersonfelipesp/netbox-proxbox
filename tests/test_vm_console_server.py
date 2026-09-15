"""Behavior and security contracts for the standalone VM console boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = REPO_ROOT / "netbox_proxbox" / "services" / "vm_console.py"
VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "vm_console.py"


class _Query:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def filter(self, **_kwargs: object) -> "_Query":
        return self

    def order_by(self, *_args: object) -> "_Query":
        return self

    def __iter__(self):
        return iter(self.values)


def _load_service(monkeypatch: pytest.MonkeyPatch, *, fastapi_rows=None):
    django_http = ModuleType("django.http")
    django_http.HttpRequest = object
    monkeypatch.setitem(sys.modules, "django.http", django_http)

    class ProxmoxEndpoint:
        def __init__(self, *, pk: int = 7, enabled: bool = True) -> None:
            self.pk = pk
            self.enabled = enabled

    class FastAPIEndpoint:
        objects = _Query(fastapi_rows or [])

    models = ModuleType("netbox_proxbox.models")
    models.FastAPIEndpoint = FastAPIEndpoint
    models.ProxmoxEndpoint = ProxmoxEndpoint
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    schemas = ModuleType("netbox_proxbox.schemas.backend_proxy")
    schemas.BackendRequestContext = object
    monkeypatch.setitem(sys.modules, "netbox_proxbox.schemas.backend_proxy", schemas)

    backend_context = ModuleType("netbox_proxbox.services.backend_context")
    backend_context.get_fastapi_request_context = lambda endpoint_id=None: None
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_context", backend_context
    )
    backend_sync = ModuleType("netbox_proxbox.views.backend_sync")
    backend_sync.resolve_backend_endpoint_id = lambda *_args, **_kwargs: (
        None,
        "missing",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.backend_sync", backend_sync)

    spec = importlib.util.spec_from_file_location(
        "_vm_console_service_test", SERVICE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module, ProxmoxEndpoint, backend_context, backend_sync


def _vm(endpoint: object, **overrides: object) -> SimpleNamespace:
    node = SimpleNamespace(name="pve-01", endpoint_id=endpoint.pk)
    cluster = SimpleNamespace(endpoint_id=endpoint.pk)
    state = SimpleNamespace(
        virtual_machine_id=11,
        endpoint=endpoint,
        proxmox_node=node,
        proxmox_node_name="pve-01",
        proxmox_cluster=cluster,
        proxmox_vm_id=101,
        proxmox_vm_type="qemu",
        proxmox_endpoint_raw_id=31,
    )
    for name, value in overrides.items():
        setattr(state, name, value)
    return SimpleNamespace(pk=11, proxbox_sync_state=state)


def test_console_identity_requires_the_complete_typed_sync_tuple(monkeypatch) -> None:
    module, endpoint_type, _context, _sync = _load_service(monkeypatch)
    endpoint = endpoint_type()

    identity = module.resolve_console_identity(_vm(endpoint))

    assert (
        identity.virtual_machine_id,
        identity.endpoint,
        identity.vmid,
        identity.node,
        identity.vm_type,
        identity.backend_raw_id,
    ) == (11, endpoint, 101, "pve-01", "qemu", 31)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"virtual_machine_id": 12}, "inconsistent"),
        ({"proxmox_node": None}, "node is unavailable"),
        ({"proxmox_node_name": "foreign"}, "node identity has drifted"),
        (
            {"proxmox_cluster": SimpleNamespace(endpoint_id=99)},
            "cluster identity has drifted",
        ),
        ({"proxmox_vm_id": 0}, "guest identity is incomplete"),
        ({"proxmox_vm_type": "template"}, "guest identity is incomplete"),
    ],
)
def test_console_identity_fails_closed_on_drift(
    monkeypatch, overrides: dict[str, object], message: str
) -> None:
    module, endpoint_type, _context, _sync = _load_service(monkeypatch)

    with pytest.raises(module.ConsoleResolutionError, match=message):
        module.resolve_console_identity(_vm(endpoint_type(), **overrides))


def test_console_identity_rejects_a_disabled_endpoint(monkeypatch) -> None:
    module, endpoint_type, _context, _sync = _load_service(monkeypatch)

    with pytest.raises(module.ConsoleResolutionError, match="endpoint is unavailable"):
        module.resolve_console_identity(_vm(endpoint_type(enabled=False)))


def test_console_backend_requires_one_matching_trusted_backend(monkeypatch) -> None:
    fastapi_rows = [SimpleNamespace(pk=3), SimpleNamespace(pk=4)]
    module, endpoint_type, backend_context, backend_sync = _load_service(
        monkeypatch, fastapi_rows=fastapi_rows
    )
    endpoint = endpoint_type()
    identity = module.resolve_console_identity(_vm(endpoint))
    contexts = {
        3: SimpleNamespace(
            http_url="https://api-a.example.test",
            headers={"X-Proxbox-API-Key": "secret"},
            verify_ssl=True,
            detail={"websocket_url": "wss://relay-a.example.test/ws"},
        ),
        4: SimpleNamespace(
            http_url="https://api-b.example.test",
            headers={"X-Proxbox-API-Key": "secret"},
            verify_ssl=True,
            detail={"websocket_url": "wss://relay-b.example.test/ws"},
        ),
    }
    module.get_fastapi_request_context = lambda endpoint_id=None: contexts[endpoint_id]
    module.resolve_backend_endpoint_id = lambda _endpoint, *, base_url, **_kwargs: (
        (31, None) if "api-b" in base_url else (None, "not registered")
    )

    selected = module.resolve_console_backend(identity)

    assert selected.backend_endpoint_id == 31
    assert selected.websocket_base == "wss://relay-b.example.test/ws"


def test_console_backend_rejects_ambiguous_matches(monkeypatch) -> None:
    module, endpoint_type, backend_context, backend_sync = _load_service(
        monkeypatch, fastapi_rows=[SimpleNamespace(pk=3), SimpleNamespace(pk=4)]
    )
    identity = module.resolve_console_identity(
        _vm(endpoint_type(), proxmox_endpoint_raw_id=None)
    )
    module.get_fastapi_request_context = lambda endpoint_id=None: SimpleNamespace(
        http_url=f"https://api-{endpoint_id}.example.test",
        headers={},
        verify_ssl=True,
        detail={"websocket_url": f"wss://relay-{endpoint_id}.example.test/ws"},
    )
    module.resolve_backend_endpoint_id = lambda *_args, **_kwargs: (31, None)

    with pytest.raises(module.ConsoleResolutionError, match="Multiple proxbox-api"):
        module.resolve_console_backend(identity)


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.example.test/proxmox/console/browser-stream?token=abcdefghijklmnopqrstuvwxyz_12345",
        "/proxmox/console/browser-stream?other=abcdefghijklmnopqrstuvwxyz_12345",
        "/proxmox/console/browser-stream?token=abcdefghijklmnopqrstuvwxyz_12345#fragment",
        "/proxmox/console/browser-stream?token=abcdefghijklmnopqrstuvwxyz_12345&other=value",
        "/ssh/sessions/1/ws",
    ],
)
def test_browser_websocket_url_rejects_untrusted_paths(monkeypatch, path: str) -> None:
    module, _endpoint, _context, _sync = _load_service(monkeypatch)

    with pytest.raises(module.ConsoleResolutionError, match="invalid"):
        module.browser_websocket_url(
            "wss://relay.example.test/ws",
            path,
            stream_token="abcdefghijklmnopqrstuvwxyz_12345",
        )


def test_browser_websocket_url_uses_only_the_configured_authority(monkeypatch) -> None:
    module, _endpoint, _context, _sync = _load_service(monkeypatch)

    assert (
        module.browser_websocket_url(
            "wss://relay.example.test/ws",
            "/proxmox/console/browser-stream",
            stream_token="abcdefghijklmnopqrstuvwxyz_12345",
        )
        == "wss://relay.example.test/proxmox/console/browser-stream"
    )


@pytest.mark.parametrize("token", ["short", "!" * 43, 43])
def test_browser_websocket_url_rejects_an_invalid_response_token(
    monkeypatch, token: object
) -> None:
    module, _endpoint, _context, _sync = _load_service(monkeypatch)

    with pytest.raises(module.ConsoleResolutionError, match="invalid"):
        module.browser_websocket_url(
            "wss://relay.example.test/ws",
            "/proxmox/console/browser-stream",
            stream_token=token,
        )


def test_console_origin_requires_https(monkeypatch) -> None:
    module, _endpoint, _context, _sync = _load_service(monkeypatch)
    secure = SimpleNamespace(
        build_absolute_uri=lambda _path: "https://netbox.example.test/"
    )
    insecure = SimpleNamespace(
        build_absolute_uri=lambda _path: "http://netbox.example.test/"
    )

    assert module.console_origin(secure) == "https://netbox.example.test"
    with pytest.raises(module.ConsoleResolutionError, match="HTTPS"):
        module.console_origin(insecure)


def test_console_view_never_returns_private_upstream_material() -> None:
    source = VIEW_PATH.read_text(encoding="utf-8")
    safe_response = source.split("def _session_payload", 1)[1].split(
        "@register_model_view", 1
    )[0]

    assert '"websocket_url"' in safe_response
    assert '"expires_at"' in safe_response
    assert '"console_type"' in safe_response
    for forbidden in ("ticket", "websocket_auth", "verify_ssl", "proxmox_host"):
        assert forbidden not in safe_response


def test_console_session_authorizes_before_contacting_the_backend() -> None:
    source = VIEW_PATH.read_text(encoding="utf-8")
    post = source.split("def post(", 1)[1]

    assert post.index("request.user.has_perm") < post.index("requests.post")
    assert post.index('restrict(request.user, "view")') < post.index("requests.post")
    assert post.index("_endpoint_console_permitted") < post.index("requests.post")
    assert "allow_redirects=False" in post
    assert "response.status_code != 201" in post
    assert "response.text" not in post
    assert "str(exc)" not in post


def test_console_tab_is_registered_on_the_core_virtual_machine() -> None:
    source = VIEW_PATH.read_text(encoding="utf-8")

    assert (
        '@register_model_view(VirtualMachine, "proxbox_console", path="console")'
        in source
    )
    assert 'template_name = "netbox_proxbox/vm_console.html"' in source
    assert "permission=permission_open_console()" in source
    assert "def get_required_permission(self) -> str:" in source
    assert "raise PermissionDenied" in source
    assert 'VirtualMachine.objects.restrict(request.user, "view")' in source
