"""Source contracts for explicit netbox-packer endpoint authorization."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_proxmox_endpoint_has_default_off_packer_template_authorization() -> None:
    source = _read("netbox_proxbox/models/proxmox_endpoint.py")
    assert "allow_packer_template_builds = models.BooleanField(" in source
    field = source.split("allow_packer_template_builds = models.BooleanField(", 1)[1]
    assert "default=False" in field.split(")\n", 1)[0]
    assert "packer_template_builds_backend_authorized = models.BooleanField(" in source
    confirmed = source.split(
        "packer_template_builds_backend_authorized = models.BooleanField(", 1
    )[1]
    assert "default=False" in confirmed.split(")\n", 1)[0]
    assert "editable=False" in confirmed.split(")\n", 1)[0]


def test_packer_authorization_is_wired_through_form_and_api() -> None:
    form = _read("netbox_proxbox/forms/proxmox.py")
    serializer = _read("netbox_proxbox/api/serializers/endpoints.py")
    assert '"allow_packer_template_builds"' in form
    assert '"allow_packer_template_builds"' in serializer
    detail_template = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint.html"
    )
    assert "object.packer_template_builds_backend_authorized" in detail_template
    assert "Authorized — revoke before deletion" in detail_template


def test_additive_default_off_migration_exists() -> None:
    migrations = list((REPO_ROOT / "netbox_proxbox" / "migrations").glob("*.py"))
    needle = '"allow_packer_template_builds",\n            models.BooleanField('
    matches = [
        path.read_text(encoding="utf-8")
        for path in migrations
        if needle in path.read_text(encoding="utf-8")
    ]
    assert len(matches) == 1
    assert "add_field_idempotent(" in matches[0]
    assert '"proxmoxendpoint"' in matches[0]
    assert "default=False" in matches[0]


def _load_authorization_module(monkeypatch, *, backend_id: int = 701):
    backend_context = ModuleType("netbox_proxbox.services.backend_context")
    backend_context.get_fastapi_request_context = lambda: SimpleNamespace(
        http_url="https://proxbox-api.example.test/",
        headers={"Authorization": "redacted"},
        verify_ssl=True,
    )
    backend_sync = ModuleType("netbox_proxbox.views.backend_sync")
    backend_sync.resolve_backend_endpoint_id = lambda endpoint, **kwargs: (
        backend_id,
        None,
    )
    proxbox_access = ModuleType("netbox_proxbox.views.proxbox_access")
    proxbox_access.permission_run_proxmox_action = lambda: "core.run_proxmox_action"
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_context", backend_context
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.backend_sync", backend_sync)
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.views.proxbox_access", proxbox_access
    )

    path = REPO_ROOT / "netbox_proxbox" / "api" / "template_build_authorization.py"
    spec = importlib.util.spec_from_file_location(
        "_test_template_build_authorization", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("has_permission", "enabled", "allow_writes", "allow_narrow", "detail"),
    [
        (False, True, True, True, "core.run_proxmox_action"),
        (True, False, True, True, "disabled"),
        (True, True, False, True, "Proxmox-side writes"),
        (True, True, True, False, "explicitly allow"),
    ],
)
def test_template_build_authorization_truth_table_fails_closed(
    monkeypatch,
    has_permission,
    enabled,
    allow_writes,
    allow_narrow,
    detail,
) -> None:
    module = _load_authorization_module(monkeypatch)
    user = SimpleNamespace(has_perm=lambda permission: has_permission)
    endpoint = SimpleNamespace(
        enabled=enabled,
        allow_writes=allow_writes,
        allow_packer_template_builds=allow_narrow,
    )

    with pytest.raises(module.TemplateBuildAuthorizationError) as raised:
        module.require_template_build_authorization(user, endpoint)

    assert raised.value.status_code == 403
    assert detail in raised.value.detail


def test_template_build_uses_divergent_backend_identity_after_all_gates(
    monkeypatch,
) -> None:
    module = _load_authorization_module(monkeypatch, backend_id=701)
    endpoint = SimpleNamespace(
        pk=17,
        enabled=True,
        allow_writes=True,
        allow_packer_template_builds=True,
    )
    user = SimpleNamespace(has_perm=lambda permission: True)

    module.require_template_build_authorization(user, endpoint)

    assert module.resolve_authorized_backend_endpoint_id(endpoint) == 701
    assert endpoint.pk != 701


def test_rest_actions_gate_before_resolving_and_send_resolved_backend_id() -> None:
    source = _read("netbox_proxbox/api/views.py")
    helper = source.split("def _template_build_payload(", 1)[1].split(
        "def perform_destroy", 1
    )[0]
    assert helper.index("require_template_build_authorization") < helper.index(
        "resolve_authorized_backend_endpoint_id"
    )
    assert 'payload["endpoint_id"] = backend_endpoint_id' in helper
    for action_name in ("build_pve_template", "cloud_image_build_pipeline"):
        action = source.split(f"def {action_name}(", 1)[1].split("\n    @", 1)[0]
        assert "self._template_build_payload(request, endpoint)" in action
