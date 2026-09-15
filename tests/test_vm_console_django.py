"""Real-NetBox contracts for the standalone virtual-machine console."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import Mock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (
    REPO_ROOT.parent / "netbox" / "netbox",
    REPO_ROOT.parents[1] / "nmulticloud-context" / "netbox" / "netbox",
)
_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import django
except ModuleNotFoundError:
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

if not hasattr(django, "__path__"):
    if _REQUIRE_DJANGO:
        raise RuntimeError("A real Django package is required for this test module.")
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

for candidate_path in NETBOX_ROOTS:
    candidate_string = str(candidate_path)
    if candidate_path.exists() and candidate_string not in sys.path:
        sys.path.insert(0, candidate_string)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external test harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}",
        allow_module_level=True,
    )

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.core.exceptions import FieldDoesNotExist  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402
from users.models import ObjectPermission  # noqa: E402
from utilities.testing import create_test_virtualmachine  # noqa: E402

from netbox_proxbox.models import (  # noqa: E402
    ProxboxPluginSettings,
    ProxboxVirtualMachineSyncState,
    ProxmoxEndpoint,
    ProxmoxNode,
)
from netbox_proxbox.services.vm_console import resolve_console_identity  # noqa: E402
from netbox_proxbox.views.vm_console import ProxboxVMConsoleTabView  # noqa: E402


pytestmark = pytest.mark.django_db


@pytest.fixture
def console_inventory():
    vm = create_test_virtualmachine("standalone-console-vm")
    endpoint = ProxmoxEndpoint.objects.create(name="standalone-console-endpoint")
    node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        name="standalone-console-node",
        ip_address="127.0.0.1",
    )
    ProxboxVirtualMachineSyncState.objects.create(
        virtual_machine=vm,
        endpoint=endpoint,
        proxmox_node=node,
        proxmox_node_name=node.name,
        proxmox_endpoint_raw_id=31,
        proxmox_vm_id=1045,
        proxmox_vm_type="qemu",
    )
    return vm, endpoint, node


def _grant(
    user,
    *,
    name: str,
    action: str,
    model: type,
    constraints: dict[str, object] | None = None,
) -> None:
    create_kwargs = {"name": name, "actions": [action]}
    if constraints is not None:
        create_kwargs["constraints"] = constraints
    permission = ObjectPermission.objects.create(**create_kwargs)
    permission.object_types.add(ContentType.objects.get_for_model(model))
    permission.users.add(user)


def test_current_model_state_retires_external_setting_and_declares_permission() -> None:
    with pytest.raises(FieldDoesNotExist):
        ProxboxPluginSettings._meta.get_field("console_url")

    assert (
        "open_console_proxmoxendpoint",
        "Can open Proxbox VM consoles",
    ) in tuple(ProxmoxEndpoint._meta.permissions)


def test_console_identity_uses_real_typed_relationships(console_inventory) -> None:
    vm, endpoint, node = console_inventory

    identity = resolve_console_identity(vm)

    assert identity.virtual_machine_id == vm.pk
    assert identity.endpoint == endpoint
    assert identity.node == node.name
    assert identity.vmid == 1045
    assert identity.vm_type == "qemu"
    assert identity.backend_raw_id == 31


def _console_tab_route(vm) -> str:
    return reverse("virtualization:virtualmachine_proxbox_console", args=[vm.pk])


def test_console_tab_requires_the_console_permission(console_inventory) -> None:
    vm, _endpoint, _node = console_inventory
    user = get_user_model().objects.create_user(username="console-tab-no-permission")
    _grant(
        user,
        name="console-tab-no-permission-vm-view",
        action="view",
        model=type(vm),
    )
    client = Client()
    client.force_login(user)

    response = client.get(_console_tab_route(vm))

    assert response.status_code == 403


def test_console_tab_rejects_permission_for_another_endpoint(
    console_inventory,
) -> None:
    vm, endpoint, _node = console_inventory
    other_endpoint = ProxmoxEndpoint.objects.create(name="other-console-endpoint")
    user = get_user_model().objects.create_user(username="console-tab-other-endpoint")
    _grant(
        user,
        name="console-tab-other-endpoint-vm-view",
        action="view",
        model=type(vm),
    )
    _grant(
        user,
        name="console-tab-other-endpoint-console",
        action="open_console",
        model=type(endpoint),
        constraints={"pk": other_endpoint.pk},
    )
    client = Client()
    client.force_login(user)

    response = client.get(_console_tab_route(vm))

    assert response.status_code == 403


def test_console_tab_accepts_permission_for_the_synchronized_endpoint(
    console_inventory,
) -> None:
    vm, endpoint, _node = console_inventory
    user = get_user_model().objects.create_user(username="console-tab-allowed")
    _grant(
        user,
        name="console-tab-allowed-vm-view",
        action="view",
        model=type(vm),
    )
    _grant(
        user,
        name="console-tab-allowed-endpoint-console",
        action="open_console",
        model=type(endpoint),
        constraints={"pk": endpoint.pk},
    )
    client = Client()
    client.force_login(user)

    response = client.get(_console_tab_route(vm))

    assert response.status_code == 200
    assert b"Console" in response.content


@pytest.mark.parametrize(
    ("grant_add_permission", "expected_status"),
    ((False, 403), (True, 200)),
)
def test_console_tab_preserves_inherited_additional_permissions(
    console_inventory,
    grant_add_permission: bool,
    expected_status: int,
) -> None:
    vm, endpoint, _node = console_inventory
    user = get_user_model().objects.create_user(
        username=f"console-tab-additional-{grant_add_permission}"
    )
    _grant(
        user,
        name="console-tab-additional-vm-view",
        action="view",
        model=type(vm),
    )
    _grant(
        user,
        name="console-tab-additional-endpoint-console",
        action="open_console",
        model=type(endpoint),
        constraints={"pk": endpoint.pk},
    )
    if grant_add_permission:
        _grant(
            user,
            name="console-tab-additional-vm-add",
            action="add",
            model=type(vm),
        )
    client = Client()
    client.force_login(user)

    with patch.object(
        ProxboxVMConsoleTabView,
        "additional_permissions",
        ["virtualization.add_virtualmachine"],
    ):
        response = client.get(_console_tab_route(vm))

    assert response.status_code == expected_status


def test_console_tab_enforces_virtual_machine_visibility(console_inventory) -> None:
    vm, endpoint, _node = console_inventory
    user = get_user_model().objects.create_user(username="console-tab-hidden-vm")
    _grant(
        user,
        name="console-tab-hidden-vm-endpoint-console",
        action="open_console",
        model=type(endpoint),
        constraints={"pk": endpoint.pk},
    )
    client = Client()
    client.force_login(user)

    response = client.get(_console_tab_route(vm))

    assert response.status_code == 404


def test_session_view_authorizes_both_objects_and_returns_only_safe_fields(
    console_inventory,
) -> None:
    vm, endpoint, _node = console_inventory
    user = get_user_model().objects.create_user(username="console-operator")
    _grant(
        user,
        name="console-operator-vm-view",
        action="view",
        model=type(vm),
    )
    _grant(
        user,
        name="console-operator-endpoint-console",
        action="open_console",
        model=type(endpoint),
    )
    client = Client()
    client.force_login(user)
    route = reverse(
        "plugins:netbox_proxbox:virtualmachine_console_session", args=[vm.pk]
    )
    backend = SimpleNamespace(
        backend_endpoint_id=31,
        websocket_base="wss://relay.example.test/ws",
        context=SimpleNamespace(
            http_url="https://backend.example.test",
            headers={"X-Proxbox-API-Key": "server-secret"},
            verify_ssl=True,
        ),
    )
    backend_response = Mock(status_code=201)
    backend_response.json.return_value = {
        "stream_token": "abcdefghijklmnopqrstuvwxyz_12345",
        "websocket_path": "/proxmox/console/browser-stream",
        "expires_at": "2026-09-14T13:00:00+00:00",
        "console_type": "novnc",
    }

    with (
        patch(
            "netbox_proxbox.views.vm_console.resolve_console_backend",
            return_value=backend,
        ),
        patch(
            "netbox_proxbox.views.vm_console.requests.post",
            return_value=backend_response,
        ) as backend_post,
    ):
        response = client.post(
            route,
            data='{"console_type":"novnc"}',
            content_type="application/json",
            secure=True,
        )

    assert response.status_code == 200
    assert response.json() == {
        "websocket_url": "wss://relay.example.test/proxmox/console/browser-stream",
        "stream_token": "abcdefghijklmnopqrstuvwxyz_12345",
        "expires_at": "2026-09-14T13:00:00+00:00",
        "console_type": "novnc",
    }
    request_kwargs = backend_post.call_args.kwargs
    assert request_kwargs["allow_redirects"] is False
    assert request_kwargs["headers"]["X-Proxbox-API-Key"] == "server-secret"
    assert request_kwargs["json"] == {
        "endpoint_id": 31,
        "vmid": 1045,
        "node": "standalone-console-node",
        "vm_type": "qemu",
        "console_type": "novnc",
        "origin": "https://testserver",
    }


def test_session_view_denies_before_backend_access(console_inventory) -> None:
    vm, _endpoint, _node = console_inventory
    user = get_user_model().objects.create_user(username="console-denied")
    client = Client()
    client.force_login(user)
    route = reverse(
        "plugins:netbox_proxbox:virtualmachine_console_session", args=[vm.pk]
    )

    with patch("netbox_proxbox.views.vm_console.requests.post") as backend_post:
        response = client.post(
            route,
            data='{"console_type":"novnc"}',
            content_type="application/json",
            secure=True,
        )

    assert response.status_code == 403
    backend_post.assert_not_called()


@pytest.mark.parametrize("status_code", [200, 204, 302])
def test_session_view_rejects_every_non_created_backend_response(
    console_inventory, status_code: int
) -> None:
    vm, endpoint, _node = console_inventory
    user = get_user_model().objects.create_user(
        username=f"console-unexpected-backend-{status_code}"
    )
    _grant(
        user,
        name=f"console-unexpected-backend-{status_code}-vm-view",
        action="view",
        model=type(vm),
    )
    _grant(
        user,
        name=f"console-unexpected-backend-{status_code}-endpoint-console",
        action="open_console",
        model=type(endpoint),
    )
    client = Client()
    client.force_login(user)
    route = reverse(
        "plugins:netbox_proxbox:virtualmachine_console_session", args=[vm.pk]
    )
    backend = SimpleNamespace(
        backend_endpoint_id=31,
        websocket_base="wss://relay.example.test/ws",
        context=SimpleNamespace(
            http_url="https://backend.example.test",
            headers={"X-Proxbox-API-Key": "server-secret"},
            verify_ssl=True,
        ),
    )
    backend_response = Mock(status_code=status_code)
    backend_response.json.side_effect = AssertionError("response body must not be read")

    with (
        patch(
            "netbox_proxbox.views.vm_console.resolve_console_backend",
            return_value=backend,
        ),
        patch(
            "netbox_proxbox.views.vm_console.requests.post",
            return_value=backend_response,
        ),
    ):
        response = client.post(
            route,
            data='{"console_type":"novnc"}',
            content_type="application/json",
            secure=True,
        )

    assert response.status_code == 502
    assert response.json() == {
        "error": "The browser-console service refused the session."
    }
    backend_response.json.assert_not_called()
