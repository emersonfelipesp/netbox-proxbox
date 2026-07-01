"""Contracts for the ProxmoxEndpoint Templates-tab create-instance action.

These tests deliberately avoid bootstrapping Django/NetBox. Structural checks
use AST/source contracts; behavior checks import the new view under the local
stubs and exercise only pure helpers or early-exit paths that never provision.
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.conftest import load_plugin_module

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "proxmox_create_instance.py"
TAB_VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "proxmox_templates_tab.py"
TEMPLATE_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "templates"
    / "netbox_proxbox"
    / "proxmoxendpoint_templates.html"
)
VIEWS_INIT_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "__init__.py"

QEMU_KEYS = {
    "endpoint_id",
    "template_vmid",
    "new_vmid",
    "new_name",
    "target_node",
    "cloud_init",
    "start_after_provision",
    "storage",
    "memory_mb",
    "cores",
    "full_clone",
}
LXC_KEYS = {
    "endpoint_id",
    "hostname",
    "ostemplate",
    "target_node",
    "rootfs_storage",
    "rootfs_size_gb",
    "memory_mb",
    "cores",
    "password",
    "start_after_provision",
}


@pytest.fixture(scope="module")
def view_src() -> str:
    return VIEW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def view_ast() -> ast.Module:
    return ast.parse(VIEW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def template_src() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def _find_assign(class_node: ast.ClassDef, target: str) -> ast.AST | None:
    for node in class_node.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target:
                    return node.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == target:
                return node.value
    return None


def _stub_create_view_imports(monkeypatch):
    requests_mod = types.ModuleType("requests")
    requests_exceptions = types.ModuleType("requests.exceptions")

    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    requests_exceptions.RequestException = RequestException
    requests_exceptions.Timeout = Timeout
    requests_mod.exceptions = requests_exceptions
    requests_mod.post = lambda *a, **kw: None
    requests_mod.get = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "requests", requests_mod)
    monkeypatch.setitem(sys.modules, "requests.exceptions", requests_exceptions)

    endpoint_errors_mod = types.ModuleType("netbox_proxbox.services._endpoint_errors")
    endpoint_errors_mod.translate_request_exception = lambda exc: str(exc)
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services._endpoint_errors",
        endpoint_errors_mod,
    )

    backend_context_mod = types.ModuleType("netbox_proxbox.services.backend_context")
    backend_context_mod.get_fastapi_request_context = lambda endpoint_id=None: None
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.backend_context",
        backend_context_mod,
    )

    individual_sync_mod = types.ModuleType("netbox_proxbox.services.individual_sync")
    individual_sync_mod.sync_individual = lambda *a, **kw: ({}, 200)
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.individual_sync", individual_sync_mod
    )

    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg._endpoint_errors = endpoint_errors_mod
    services_pkg.backend_context = backend_context_mod
    services_pkg.individual_sync = individual_sync_mod
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)

    backend_sync_mod = types.ModuleType("netbox_proxbox.views.backend_sync")
    backend_sync_mod.resolve_backend_endpoint_id = lambda *a, **kw: (7, None)
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.views.backend_sync", backend_sync_mod
    )


def _load_create_view(monkeypatch):
    _stub_create_view_imports(monkeypatch)
    return load_plugin_module(
        "netbox_proxbox.views.proxmox_create_instance",
        monkeypatch=monkeypatch,
    )


def _response(status_code: int, payload: dict | None = None, text: str = ""):
    body = payload or {}

    def json_func():
        return body

    return SimpleNamespace(status_code=status_code, json=json_func, text=text)


# ---------- View structure and wiring ----------


def test_create_view_class_exists_and_uses_expected_mixins(view_ast):
    cls = _find_class(view_ast, "ProxmoxEndpointCreateInstanceView")
    base_names = {
        b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
        for b in cls.bases
    }
    assert "TokenConditionalLoginRequiredMixin" in base_names
    assert "ContentTypePermissionRequiredMixin" in base_names
    assert "View" in base_names


def test_create_view_is_registered_post_only_and_permission_gated(view_src, view_ast):
    assert (
        '@register_model_view(ProxmoxEndpoint, "create_instance", path="create-instance")'
        in view_src
    )
    cls = _find_class(view_ast, "ProxmoxEndpointCreateInstanceView")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert {"get_required_permission", "post"} <= methods
    assert "permission_run_proxmox_action()" in view_src
    http_methods = _find_assign(cls, "http_method_names")
    assert isinstance(http_methods, ast.List)
    assert [e.value for e in http_methods.elts] == ["post"]


def test_create_view_public_all(view_ast):
    module_all = None
    for node in view_ast.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            module_all = node.value
    assert module_all is not None
    elts = {e.value for e in module_all.elts if isinstance(e, ast.Constant)}
    assert "ProxmoxEndpointCreateInstanceView" in elts


def test_create_view_wired_into_views_package():
    init_src = VIEWS_INIT_PATH.read_text(encoding="utf-8")
    assert (
        "from .proxmox_create_instance import ProxmoxEndpointCreateInstanceView"
        in init_src
    )


def test_templates_tab_context_exposes_write_gate_and_create_url():
    tab_src = TAB_VIEW_PATH.read_text(encoding="utf-8")
    assert (
        'context["allow_writes"] = bool(getattr(instance, "allow_writes", False))'
        in tab_src
    )
    assert "proxmoxendpoint_create_instance" in tab_src


# ---------- Source contracts ----------


def test_create_view_uses_direct_proxbox_api_boundary(view_src):
    assert "get_fastapi_request_context" in view_src
    assert "resolve_backend_endpoint_id" in view_src
    assert "/cloud/vm/provision" in view_src
    assert "/cloud/lxc/provision" in view_src
    assert "nms-backend" not in view_src.lower()


def test_create_view_enforces_write_gate_before_backend_resolution(view_src):
    precheck_index = view_src.index("endpoint_allows_instance_create(endpoint)")
    backend_index = view_src.index("get_fastapi_request_context()")
    assert precheck_index < backend_index
    assert "writes_disabled_for_endpoint" in view_src


def test_create_view_has_required_headers_timeout_syncback_and_no_disk_field(view_src):
    assert "X-Proxbox-Actor" in view_src
    assert "Idempotency-Key" in view_src
    assert "_PROVISION_TIMEOUT_S = 90" in view_src
    assert "sync_individual(" in view_src
    assert '"sync/individual/vm"' in view_src
    assert "custom_field_data__proxmox_vm_id" in view_src
    assert '"disk_gb"' not in view_src


def test_create_view_validates_expected_contract_fields(view_src):
    for helper in (
        "build_qemu_provision_payload",
        "build_lxc_provision_payload",
        "build_cloud_init_payload",
        "validate_create_instance_payload",
        "is_vmid_collision_response",
    ):
        assert f"def {helper}" in view_src
    assert "rootfs_size_gb" in view_src
    assert "cloud_init.network" in view_src
    assert "ssh_keys" in view_src
    assert "_MAX_REQUEST_BYTES" in view_src


# ---------- Helper behavior ----------


def test_allow_writes_precheck_behavior(monkeypatch):
    module = _load_create_view(monkeypatch)
    calls: list[str] = []
    endpoint = SimpleNamespace(pk=1, allow_writes=False)
    monkeypatch.setattr(module, "get_object_or_404", lambda *a, **kw: endpoint)
    monkeypatch.setattr(
        module,
        "get_fastapi_request_context",
        lambda *a, **kw: calls.append("backend"),
    )

    request = SimpleNamespace(
        user=SimpleNamespace(username="ops"),
        body=b'{"kind":"qemu","source":100,"name":"vm-1","target_node":"pve-a"}',
    )
    response = module.ProxmoxEndpointCreateInstanceView().post(request, pk=1)

    assert response.status_code == 403
    assert response.payload["reason"] == "writes_disabled_for_endpoint"
    assert calls == []


def test_qemu_payload_builder_only_uses_allowed_keys_and_linked_clone_default(
    monkeypatch,
):
    module = _load_create_view(monkeypatch)
    payload = module.build_qemu_provision_payload(
        endpoint_id=7,
        template_vmid=100,
        new_vmid=200,
        new_name="vm-new",
        target_node="pve-a",
    )
    assert set(payload) == QEMU_KEYS
    assert payload["endpoint_id"] == 7
    assert payload["template_vmid"] == 100
    assert payload["new_vmid"] == 200
    assert payload["cloud_init"] == {}
    assert payload["full_clone"] is False
    assert "disk_gb" not in payload


def test_lxc_payload_builder_only_uses_allowed_keys(monkeypatch):
    module = _load_create_view(monkeypatch)
    payload = module.build_lxc_provision_payload(
        endpoint_id=7,
        hostname="ct-new",
        ostemplate="local:vztmpl/debian.tar.zst",
        target_node="pve-a",
    )
    assert set(payload) == LXC_KEYS
    assert payload["rootfs_storage"] == "local-lvm"
    assert payload["rootfs_size_gb"] == 8
    assert "new_vmid" not in payload
    assert "network" not in payload


def test_cloud_init_builder_validates_network_and_ssh_keys(monkeypatch):
    module = _load_create_view(monkeypatch)
    payload = module.build_cloud_init_payload(
        {
            "user": "ubuntu",
            "ssh_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest"],
            "network": {"ip": "192.0.2.10", "cidr": 24, "gw": "192.0.2.1"},
            "search_domain": "example.test",
            "dns_servers": ["1.1.1.1", "8.8.8.8"],
        }
    )
    assert payload == {
        "user": "ubuntu",
        "ssh_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest"],
        "network": {"ip": "192.0.2.10", "cidr": 24, "gw": "192.0.2.1"},
        "search_domain": "example.test",
        "dns_servers": ["1.1.1.1", "8.8.8.8"],
    }


def test_validate_payloads_reject_unknown_fields(monkeypatch):
    module = _load_create_view(monkeypatch)
    with pytest.raises(module.CreateInstanceValidationError) as exc:
        module.validate_create_instance_payload(
            {
                "kind": "lxc",
                "source": "local:vztmpl/debian.tar.zst",
                "hostname": "ct-new",
                "target_node": "pve-a",
                "bridge": "vmbr0",
            }
        )
    assert exc.value.reason == "unknown_fields"


def test_vmid_retry_increments_on_collision(monkeypatch):
    module = _load_create_view(monkeypatch)
    calls: list[int] = []
    responses = [
        _response(409, {"detail": "VMID 200 already exists"}),
        _response(200, {"new_vmid": 201, "status": "started"}),
    ]

    def fake_post(url, json=None, headers=None, verify=None, timeout=None):
        calls.append(json["new_vmid"])
        return responses.pop(0)

    monkeypatch.setattr(module.requests, "post", fake_post)
    response, chosen = module._post_qemu_with_vmid_retry(
        url="https://backend/cloud/vm/provision",
        payload={"new_vmid": 200},
        headers={"X-Proxbox-Actor": "ops", "Idempotency-Key": "first"},
        verify_ssl=False,
        timeout=90,
        base_vmid=200,
        max_attempts=20,
    )

    assert response.status_code == 200
    assert chosen == 201
    assert calls == [200, 201]


def test_provision_headers_include_actor_and_idempotency_key(monkeypatch):
    module = _load_create_view(monkeypatch)
    headers = module.build_provision_headers({"X-Proxbox-API-Key": "secret"}, "ops")
    assert headers["X-Proxbox-API-Key"] == "secret"
    assert headers["X-Proxbox-Actor"] == "ops"
    assert headers["Content-Type"] == "application/json"
    assert headers["Idempotency-Key"]

    fallback = module.build_provision_headers({}, "")
    assert fallback["X-Proxbox-Actor"] == "netbox"


def test_backend_403_reason_is_surfaced_verbatim(monkeypatch):
    module = _load_create_view(monkeypatch)
    response = module._backend_error_response(
        _response(
            403,
            {
                "reason": "writes_disabled_for_endpoint",
                "detail": "Writes disabled on endpoint 7.",
                "endpoint_id": 7,
            },
        )
    )
    assert response.status_code == 403
    assert response.payload["success"] is False
    assert response.payload["reason"] == "writes_disabled_for_endpoint"
    assert response.payload["detail"] == "Writes disabled on endpoint 7."
    assert response.payload["endpoint_id"] == 7


# ---------- Template contracts ----------


def test_template_has_actions_column_in_all_three_tables(template_src):
    assert (
        template_src.count('class="text-end noprint">{% trans "Actions" %}</th>') == 3
    )
    assert template_src.count('class="text-end noprint"') >= 6


def test_template_create_buttons_have_required_data_attributes(template_src):
    assert 'data-create-kind="qemu"' in template_src
    assert 'data-create-kind="lxc"' in template_src
    assert 'data-create-source="{{ t.vmid }}"' in template_src
    assert 'data-create-source="{{ t.volid }}"' in template_src
    assert 'data-create-node="{{ t.node }}"' in template_src
    assert 'data-create-node=""' in template_src
    assert 'data-create-name="{{ t.name }}"' in template_src
    assert 'data-create-url="{{ create_instance_url }}"' in template_src


def test_template_disables_create_button_with_working_tooltip(template_src):
    assert "{% if allow_writes %}" in template_src
    assert "Enable write access on this endpoint to create instances." in template_src
    assert 'data-bs-toggle="tooltip"' in template_src
    assert 'style="pointer-events: none;"' in template_src
    assert "disabled" in template_src


def test_template_contains_modal_wizard_steps_and_csrf(template_src):
    assert "{% block modals %}" in template_src
    assert "proxbox-create-instance-modal" in template_src
    for step in ("1", "2", "3", "4"):
        assert f'data-step="{step}"' in template_src
    assert "data-qemu-step" in template_src
    assert "data-lxc-only" in template_src
    assert "{% csrf_token %}" in template_src


def test_template_fetch_posts_json_with_csrf_and_no_unsafe_js(template_src):
    assert "fetch(root.dataset.createUrl" in template_src
    assert "method: 'POST'" in template_src
    assert "'Content-Type': 'application/json'" in template_src
    assert "'X-CSRFToken': csrfToken()" in template_src
    assert "credentials: 'same-origin'" in template_src
    assert "JSON.stringify(payload)" in template_src
    assert "innerHTML" not in template_src
    assert "eval(" not in template_src
    assert "new Function" not in template_src
    assert "dangerouslySetInnerHTML" not in template_src
