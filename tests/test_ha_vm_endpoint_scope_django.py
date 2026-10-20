"""Real-Django regressions for endpoint-scoped per-VM HA reads."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import Mock, patch

import pytest

from tests.netbox_test_paths import netbox_source_roots


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = netbox_source_roots(REPO_ROOT)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

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
from django.test import Client, TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from users.models import ObjectPermission  # noqa: E402
from virtualization.models import Cluster, ClusterType, VirtualMachine  # noqa: E402

from netbox_proxbox.api import ha as api_ha  # noqa: E402
from netbox_proxbox.models import (  # noqa: E402
    ProxboxVirtualMachineSyncState,
    ProxmoxEndpoint,
    ProxmoxNode,
)
from netbox_proxbox.views import vm_ha  # noqa: E402
from tests.django_support import create_legacy_proxmox_cluster  # noqa: E402


class _HAResponse:
    status_code = 200
    ok = True

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def _grant(
    user: object,
    model: type,
    *,
    constraints: dict[str, object] | None = None,
) -> None:
    permission = ObjectPermission.objects.create(
        name=f"HA endpoint scope {model._meta.label} {user.username}",
        actions=["view"],
        constraints=constraints,
    )
    permission.object_types.add(ContentType.objects.get_for_model(model))
    permission.users.add(user)


class HAVMEndpointScopeTests(TestCase):
    """A duplicate VMID never widens a per-VM lookup to another endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cluster_type = ClusterType.objects.create(
            name="HA endpoint scope",
            slug="ha-endpoint-scope",
        )
        cls.endpoint_a = ProxmoxEndpoint.objects.create(
            name="ha-endpoint-a",
            enabled=True,
        )
        cls.endpoint_b = ProxmoxEndpoint.objects.create(
            name="ha-endpoint-b",
            enabled=True,
        )
        cls.shared_netbox_cluster = Cluster.objects.create(
            name="ha-shared-netbox-cluster",
            type=cluster_type,
        )
        cls.reassigned_netbox_cluster = Cluster.objects.create(
            name="ha-reassigned-netbox-cluster",
            type=cluster_type,
        )
        untracked_cluster = Cluster.objects.create(
            name="ha-untracked-netbox-cluster",
            type=cluster_type,
        )
        cls.proxmox_cluster_a = create_legacy_proxmox_cluster(
            endpoint=cls.endpoint_a,
            netbox_cluster=cls.shared_netbox_cluster,
            name="ha-proxmox-cluster-a",
        )
        cls.proxmox_cluster_b = create_legacy_proxmox_cluster(
            endpoint=cls.endpoint_b,
            netbox_cluster=cls.shared_netbox_cluster,
            name="ha-proxmox-cluster-b",
        )
        cls.proxmox_node_a = ProxmoxNode.objects.create(
            endpoint=cls.endpoint_a,
            proxmox_cluster=cls.proxmox_cluster_a,
            name="ha-proxmox-node-a",
            ip_address="192.0.2.11",
        )
        cls.proxmox_node_b = ProxmoxNode.objects.create(
            endpoint=cls.endpoint_b,
            proxmox_cluster=cls.proxmox_cluster_b,
            name="ha-proxmox-node-b",
            ip_address="192.0.2.22",
        )
        cls.vm_a = VirtualMachine.objects.create(
            name="ha-duplicate-vmid-a",
            status="active",
            cluster=cls.shared_netbox_cluster,
        )
        cls.vm_b = VirtualMachine.objects.create(
            name="ha-duplicate-vmid-b",
            status="active",
            cluster=cls.shared_netbox_cluster,
        )
        cls.untracked_vm = VirtualMachine.objects.create(
            name="ha-untracked-vm",
            status="active",
            cluster=untracked_cluster,
        )
        for vm, endpoint, proxmox_cluster, proxmox_node in (
            (
                cls.vm_a,
                cls.endpoint_a,
                cls.proxmox_cluster_a,
                cls.proxmox_node_a,
            ),
            (
                cls.vm_b,
                cls.endpoint_b,
                cls.proxmox_cluster_b,
                cls.proxmox_node_b,
            ),
        ):
            ProxboxVirtualMachineSyncState.objects.create(
                virtual_machine=vm,
                endpoint=endpoint,
                proxmox_cluster=proxmox_cluster,
                proxmox_node=proxmox_node,
                proxmox_vm_id=695,
                proxmox_vm_type="qemu",
            )

        cls.cluster_conflict_vm = VirtualMachine.objects.create(
            name="ha-cluster-conflict-vm",
            status="active",
            cluster=cls.shared_netbox_cluster,
        )
        ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=cls.cluster_conflict_vm,
            endpoint=cls.endpoint_b,
            proxmox_cluster=cls.proxmox_cluster_a,
            proxmox_node=cls.proxmox_node_b,
            proxmox_vm_id=696,
            proxmox_vm_type="qemu",
        )
        cls.node_conflict_vm = VirtualMachine.objects.create(
            name="ha-node-conflict-vm",
            status="active",
            cluster=cls.shared_netbox_cluster,
        )
        ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=cls.node_conflict_vm,
            endpoint=cls.endpoint_b,
            proxmox_cluster=cls.proxmox_cluster_b,
            proxmox_node=cls.proxmox_node_a,
            proxmox_vm_id=697,
            proxmox_vm_type="qemu",
        )

        cls.removed_endpoint = ProxmoxEndpoint.objects.create(
            name="ha-removed-endpoint",
            enabled=True,
        )
        removed_cluster = create_legacy_proxmox_cluster(
            endpoint=cls.removed_endpoint,
            netbox_cluster=cls.shared_netbox_cluster,
            name="ha-removed-proxmox-cluster",
        )
        removed_node = ProxmoxNode.objects.create(
            endpoint=cls.removed_endpoint,
            proxmox_cluster=removed_cluster,
            name="ha-removed-proxmox-node",
            ip_address="192.0.2.33",
        )
        cls.removed_endpoint_vm = VirtualMachine.objects.create(
            name="ha-removed-endpoint-vm",
            status="active",
            cluster=cls.shared_netbox_cluster,
        )
        ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=cls.removed_endpoint_vm,
            endpoint=cls.removed_endpoint,
            proxmox_cluster=removed_cluster,
            proxmox_node=removed_node,
            proxmox_vm_id=698,
            proxmox_vm_type="qemu",
        )

        cls.user = get_user_model().objects.create_user(username="ha-vm-reader")
        _grant(cls.user, VirtualMachine)
        _grant(cls.user, ProxmoxEndpoint)

        cls.endpoint_a_only_user = get_user_model().objects.create_user(
            username="ha-vm-endpoint-a-reader"
        )
        _grant(cls.endpoint_a_only_user, VirtualMachine)
        _grant(
            cls.endpoint_a_only_user,
            ProxmoxEndpoint,
            constraints={"pk": cls.endpoint_a.pk},
        )

        cls.vm_a_only_user = get_user_model().objects.create_user(
            username="ha-vm-a-only-reader"
        )
        _grant(
            cls.vm_a_only_user,
            VirtualMachine,
            constraints={"pk": cls.vm_a.pk},
        )
        _grant(
            cls.vm_a_only_user,
            ProxmoxEndpoint,
            constraints={"pk": cls.endpoint_a.pk},
        )

    def setUp(self) -> None:
        self.ctx = SimpleNamespace(
            http_url="https://backend.example.test",
            headers={"X-Test": "ha-scope"},
            verify_ssl=True,
        )

    def _scope(self, calls: list[list[int]]):
        def resolve(**kwargs: object) -> tuple[dict[str, str], dict[int, int], None]:
            endpoint_ids = list(kwargs.get("endpoint_ids") or [])
            calls.append(endpoint_ids)
            backend_ids = {
                endpoint_id: endpoint_id + 1000 for endpoint_id in endpoint_ids
            }
            return (
                {
                    "source": "database",
                    "proxmox_endpoint_ids": ",".join(
                        str(backend_ids[endpoint_id]) for endpoint_id in endpoint_ids
                    ),
                },
                backend_ids,
                None,
            )

        return resolve

    def _backend_get(self, calls: list[dict[str, object]]):
        def get(url: str, **kwargs: object) -> _HAResponse:
            calls.append({"url": url, **kwargs})
            endpoint_ids = kwargs["params"]["proxmox_endpoint_ids"]
            if endpoint_ids == str(self.endpoint_b.pk + 1000):
                return _HAResponse({"sid": "vm:695", "state": "endpoint-b"})
            return _HAResponse({"sid": "vm:695", "state": "endpoint-a"})

        return get

    def _assert_identity_rejected_without_backend(
        self,
        vm: VirtualMachine,
        *,
        vmid: int,
    ) -> None:
        scope = Mock()
        visibility = Mock()
        backend_get = Mock()
        tab_context = Mock()
        api_context = Mock()
        tab_client = Client()
        tab_client.force_login(self.user)
        api_client = APIClient()
        api_client.force_authenticate(user=self.user)

        with (
            patch.object(vm_ha, "viewable_enabled_endpoint_ids", visibility),
            patch.object(vm_ha, "enabled_backend_endpoint_scope", scope),
            patch.object(vm_ha, "get_fastapi_request_context", tab_context),
            patch.object(vm_ha.requests, "get", backend_get),
            patch.object(api_ha, "viewable_enabled_endpoint_ids", visibility),
            patch.object(api_ha, "enabled_backend_endpoint_scope", scope),
            patch.object(api_ha, "get_fastapi_request_context", api_context),
            patch.object(api_ha.requests, "get", backend_get),
        ):
            tab_response = tab_client.get(
                reverse("virtualization:virtualmachine_proxmox_ha", args=[vm.pk])
            )
            api_response = api_client.get(
                reverse(
                    "plugins-api:netbox_proxbox-api:api-ha-vm-resource",
                    args=[vmid],
                ),
                {"virtual_machine_id": vm.pk},
            )

        self.assertEqual(tab_response.status_code, 200, tab_response.content)
        self.assertIn(
            "identity is missing, disabled, or inconsistent",
            tab_response.context["detail"],
        )
        self.assertEqual(api_response.status_code, 400, api_response.data)
        self.assertIn(
            "identity is missing, disabled, or inconsistent",
            api_response.data["detail"],
        )
        visibility.assert_not_called()
        scope.assert_not_called()
        tab_context.assert_not_called()
        api_context.assert_not_called()
        backend_get.assert_not_called()

    def test_tab_queries_only_the_selected_vms_endpoint(self) -> None:
        scope_calls: list[list[int]] = []
        backend_calls: list[dict[str, object]] = []
        client = Client()
        client.force_login(self.user)

        with (
            patch.object(vm_ha, "get_fastapi_request_context", return_value=self.ctx),
            patch.object(
                vm_ha,
                "enabled_backend_endpoint_scope",
                side_effect=self._scope(scope_calls),
            ),
            patch.object(
                vm_ha.requests,
                "get",
                side_effect=self._backend_get(backend_calls),
            ),
        ):
            response = client.get(
                reverse("virtualization:virtualmachine_proxmox_ha", args=[self.vm_b.pk])
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(scope_calls, [[self.endpoint_b.pk]])
        self.assertEqual(len(backend_calls), 1)
        self.assertEqual(response.context["ha"]["state"], "endpoint-b")

    def test_api_queries_only_the_selected_vms_endpoint(self) -> None:
        scope_calls: list[list[int]] = []
        backend_calls: list[dict[str, object]] = []
        client = APIClient()
        client.force_authenticate(user=self.user)

        with (
            patch.object(api_ha, "get_fastapi_request_context", return_value=self.ctx),
            patch.object(
                api_ha,
                "enabled_backend_endpoint_scope",
                side_effect=self._scope(scope_calls),
            ),
            patch.object(
                api_ha.requests,
                "get",
                side_effect=self._backend_get(backend_calls),
            ),
        ):
            response = client.get(
                reverse(
                    "plugins-api:netbox_proxbox-api:api-ha-vm-resource",
                    args=[695],
                ),
                {"virtual_machine_id": self.vm_b.pk},
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(scope_calls, [[self.endpoint_b.pk]])
        self.assertEqual(len(backend_calls), 1)
        self.assertEqual(response.data["state"], "endpoint-b")

    def test_tab_and_api_keep_typed_endpoint_after_netbox_cluster_reassignment(
        self,
    ) -> None:
        VirtualMachine.objects.filter(pk=self.vm_b.pk).update(
            cluster=self.reassigned_netbox_cluster
        )
        scope_calls: list[list[int]] = []
        backend_calls: list[dict[str, object]] = []
        tab_client = Client()
        tab_client.force_login(self.user)
        api_client = APIClient()
        api_client.force_authenticate(user=self.user)

        with (
            patch.object(vm_ha, "get_fastapi_request_context", return_value=self.ctx),
            patch.object(
                vm_ha,
                "enabled_backend_endpoint_scope",
                side_effect=self._scope(scope_calls),
            ),
            patch.object(
                vm_ha.requests,
                "get",
                side_effect=self._backend_get(backend_calls),
            ),
            patch.object(api_ha, "get_fastapi_request_context", return_value=self.ctx),
            patch.object(
                api_ha,
                "enabled_backend_endpoint_scope",
                side_effect=self._scope(scope_calls),
            ),
            patch.object(
                api_ha.requests,
                "get",
                side_effect=self._backend_get(backend_calls),
            ),
        ):
            tab_response = tab_client.get(
                reverse("virtualization:virtualmachine_proxmox_ha", args=[self.vm_b.pk])
            )
            api_response = api_client.get(
                reverse(
                    "plugins-api:netbox_proxbox-api:api-ha-vm-resource",
                    args=[695],
                ),
                {"virtual_machine_id": self.vm_b.pk},
            )

        self.assertEqual(tab_response.status_code, 200, tab_response.content)
        self.assertEqual(api_response.status_code, 200, api_response.data)
        self.assertEqual(scope_calls, [[self.endpoint_b.pk], [self.endpoint_b.pk]])
        self.assertEqual(len(backend_calls), 2)
        self.assertEqual(tab_response.context["ha"]["state"], "endpoint-b")
        self.assertEqual(api_response.data["state"], "endpoint-b")

    def test_tab_and_api_reject_conflicting_typed_relations_without_backend(
        self,
    ) -> None:
        for vm, vmid in (
            (self.cluster_conflict_vm, 696),
            (self.node_conflict_vm, 697),
        ):
            with self.subTest(vm=vm.name):
                self._assert_identity_rejected_without_backend(vm, vmid=vmid)

    def test_tab_and_api_reject_disabled_typed_endpoint_without_backend(self) -> None:
        ProxmoxEndpoint.objects.filter(pk=self.endpoint_b.pk).update(enabled=False)

        self._assert_identity_rejected_without_backend(self.vm_b, vmid=695)

    def test_tab_and_api_reject_removed_typed_endpoint_without_backend(self) -> None:
        ProxmoxEndpoint.objects.filter(pk=self.removed_endpoint.pk).delete()

        self._assert_identity_rejected_without_backend(
            self.removed_endpoint_vm,
            vmid=698,
        )

    def test_api_rejects_missing_or_inconsistent_vm_identity_without_backend(
        self,
    ) -> None:
        client = APIClient()
        client.force_authenticate(user=self.user)
        scope = Mock()
        backend_get = Mock()
        url = reverse(
            "plugins-api:netbox_proxbox-api:api-ha-vm-resource",
            args=[696],
        )

        with (
            patch.object(api_ha, "enabled_backend_endpoint_scope", scope),
            patch.object(api_ha.requests, "get", backend_get),
        ):
            missing = client.get(url)
            mismatch = client.get(url, {"virtual_machine_id": self.vm_b.pk})

        self.assertEqual(missing.status_code, 400)
        self.assertIn("virtual_machine_id", missing.data["detail"])
        self.assertEqual(mismatch.status_code, 400)
        self.assertIn("does not match", mismatch.data["detail"])
        scope.assert_not_called()
        backend_get.assert_not_called()

    def test_tab_and_api_reject_an_invisible_endpoint_without_backend(self) -> None:
        scope = Mock()
        backend_get = Mock()
        tab_client = Client()
        tab_client.force_login(self.endpoint_a_only_user)
        api_client = APIClient()
        api_client.force_authenticate(user=self.endpoint_a_only_user)

        with (
            patch.object(vm_ha, "enabled_backend_endpoint_scope", scope),
            patch.object(vm_ha.requests, "get", backend_get),
            patch.object(api_ha, "enabled_backend_endpoint_scope", scope),
            patch.object(api_ha.requests, "get", backend_get),
        ):
            tab_response = tab_client.get(
                reverse("virtualization:virtualmachine_proxmox_ha", args=[self.vm_b.pk])
            )
            api_response = api_client.get(
                reverse(
                    "plugins-api:netbox_proxbox-api:api-ha-vm-resource",
                    args=[695],
                ),
                {"virtual_machine_id": self.vm_b.pk},
            )

        self.assertEqual(tab_response.status_code, 200, tab_response.content)
        self.assertIn("not visible", tab_response.context["detail"])
        self.assertEqual(api_response.status_code, 400)
        self.assertIn("not visible", api_response.data["detail"])
        scope.assert_not_called()
        backend_get.assert_not_called()

    def test_api_rejects_malformed_unknown_hidden_and_unresolved_vm(self) -> None:
        url = reverse(
            "plugins-api:netbox_proxbox-api:api-ha-vm-resource",
            args=[695],
        )
        scope = Mock()
        backend_get = Mock()

        client = APIClient()
        client.force_authenticate(user=self.user)
        limited_client = APIClient()
        limited_client.force_authenticate(user=self.vm_a_only_user)
        with (
            patch.object(api_ha, "enabled_backend_endpoint_scope", scope),
            patch.object(api_ha.requests, "get", backend_get),
        ):
            responses = (
                client.get(url, {"virtual_machine_id": "not-an-id"}),
                client.get(url, {"virtual_machine_id": 999999999}),
                limited_client.get(url, {"virtual_machine_id": self.vm_b.pk}),
                client.get(url, {"virtual_machine_id": self.untracked_vm.pk}),
            )

        for response in responses:
            with self.subTest(detail=response.data["detail"]):
                self.assertEqual(response.status_code, 400)
        self.assertIn("positive integer", responses[0].data["detail"])
        self.assertIn("does not exist or is not visible", responses[1].data["detail"])
        self.assertIn("does not exist or is not visible", responses[2].data["detail"])
        self.assertIn(
            "synchronized Proxmox endpoint identity", responses[3].data["detail"]
        )
        scope.assert_not_called()
        backend_get.assert_not_called()

    def test_tab_rejects_unresolved_identity_without_backend(self) -> None:
        client = Client()
        client.force_login(self.user)
        scope = Mock()
        backend_get = Mock()

        with (
            patch.object(vm_ha, "enabled_backend_endpoint_scope", scope),
            patch.object(vm_ha.requests, "get", backend_get),
        ):
            response = client.get(
                reverse(
                    "virtualization:virtualmachine_proxmox_ha",
                    args=[self.untracked_vm.pk],
                )
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("no Proxmox VM ID", response.context["detail"])
        scope.assert_not_called()
        backend_get.assert_not_called()
