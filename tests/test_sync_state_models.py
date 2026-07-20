"""Behavior tests for typed Proxbox sync-state sidecar models."""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = REPO_ROOT.parent / "netbox" / "netbox"

for candidate in (REPO_ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

# When set (as CI does for the NetBox-provisioned job), a missing or broken
# NetBox test harness is a hard error instead of a silent skip, so this suite
# actually gates merges rather than passing vacuously.
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

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - depends on external test services
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from django.apps import apps as django_apps  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.db import IntegrityError, connection, transaction  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.test import TestCase, TransactionTestCase  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.urls import reverse  # noqa: E402
from dcim.models import Device, DeviceRole, DeviceType, Interface, Manufacturer, Site  # noqa: E402
from ipam.models import IPAddress, VLAN  # noqa: E402
from users.models import ObjectPermission, Token  # noqa: E402
from utilities.testing import create_test_device, create_test_virtualmachine  # noqa: E402
from virtualization.models import (  # noqa: E402
    Cluster,
    ClusterGroup,
    ClusterType,
    VirtualDisk,
    VirtualMachine,
    VMInterface,
)

from netbox_proxbox.filtersets import ProxboxVirtualMachineSyncStateFilterSet  # noqa: E402
from netbox_proxbox.models import (  # noqa: E402
    ProxboxClusterGroupSyncState,
    ProxboxClusterSyncState,
    ProxboxClusterTypeSyncState,
    ProxboxDeviceRoleSyncState,
    ProxboxDeviceSyncState,
    ProxboxDeviceTypeSyncState,
    ProxboxIPAddressSyncState,
    ProxboxInterfaceSyncState,
    ProxboxManufacturerSyncState,
    ProxboxSiteSyncState,
    ProxboxVirtualDiskSyncState,
    ProxboxVirtualMachineSyncState,
    ProxboxVLANSyncState,
    ProxboxVMInterfaceSyncState,
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxmoxStorage,
)


SYNC_STATE_MODELS = (
    ProxboxVirtualMachineSyncState,
    ProxboxDeviceSyncState,
    ProxboxClusterSyncState,
    ProxboxIPAddressSyncState,
    ProxboxInterfaceSyncState,
    ProxboxVLANSyncState,
    ProxboxClusterGroupSyncState,
    ProxboxVirtualDiskSyncState,
    ProxboxVMInterfaceSyncState,
    ProxboxDeviceRoleSyncState,
    ProxboxDeviceTypeSyncState,
    ProxboxManufacturerSyncState,
    ProxboxSiteSyncState,
    ProxboxClusterTypeSyncState,
)

MIGRATION_0064 = ("netbox_proxbox", "0064_proxmoxvmcloudinit_intent")
MIGRATION_0065 = ("netbox_proxbox", "0065_proxbox_sync_state_models")
MIGRATION_0066 = ("netbox_proxbox", "0066_backfill_proxbox_sync_state")
MIGRATION_0067 = ("netbox_proxbox", "0067_sync_state_relation_fks")
MIGRATION_0068 = ("netbox_proxbox", "0068_sync_state_relation_fk_data")
MIGRATION_0069 = ("netbox_proxbox", "0069_sync_state_relation_fk_cleanup")


def _slug(prefix: str, value: int) -> str:
    return f"{prefix}-{value}"


def _model_route(model) -> str:
    return model._meta.model_name


def _backfill_module():
    return importlib.import_module(
        "netbox_proxbox.migrations.0066_backfill_proxbox_sync_state"
    )


def _set_custom_field_data(obj, data) -> None:
    obj.custom_field_data = data
    obj.save(update_fields=["custom_field_data"])


def _netbox_version_tuple() -> tuple[int, int]:
    candidates = []
    for module_name in ("netbox.release", "netbox"):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        candidates.extend(
            (
                getattr(module, "VERSION", ""),
                getattr(module, "__version__", ""),
            )
        )

    for candidate in candidates:
        if isinstance(candidate, (tuple, list)) and len(candidate) >= 2:
            try:
                return int(candidate[0]), int(candidate[1])
            except (TypeError, ValueError):
                continue
        match = re.match(r"^(\d+)\.(\d+)", str(candidate))
        if match:
            return int(match.group(1)), int(match.group(2))
    return (4, 6)


def _auth_headers(token: Token) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Token {token.key}"}


def _create_api_token(
    username: str,
    sidecar_models: tuple[type, ...],
    parent_models: set[type],
) -> Token:
    user = get_user_model().objects.create_user(username=username, is_staff=True)
    token = Token.objects.create(user=user)
    permission = ObjectPermission.objects.create(
        name=f"{username}-sync-state-rw",
        actions=["view", "add", "change", "delete"],
    )
    for model in sidecar_models:
        permission.object_types.add(ContentType.objects.get_for_model(model))
    permission.users.add(user)

    parent_permission = ObjectPermission.objects.create(
        name=f"{username}-sync-state-parent-view",
        actions=["view"],
    )
    for model in parent_models:
        parent_permission.object_types.add(ContentType.objects.get_for_model(model))
    parent_permission.users.add(user)
    return token


class _SyncStateFixturesMixin:
    """Create the NetBox core objects needed by all sync-state tests."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.vm = create_test_virtualmachine("sync-state-vm")
        cls.vm_for_api = create_test_virtualmachine("sync-state-api-vm")
        cls.vm_nomatch = create_test_virtualmachine("sync-state-nomatch-vm")
        cls.device = create_test_device("sync-state-device")
        cls.device_for_api = create_test_device("sync-state-api-device")
        cls.interface = Interface.objects.create(device=cls.device, name="eth-sync")
        cls.ip_address = IPAddress.objects.create(address="192.0.2.213/24")
        cls.vlan = VLAN.objects.create(name="sync-state-vlan", vid=213)
        cls.vm_interface = VMInterface.objects.create(
            virtual_machine=cls.vm,
            name="net213",
            enabled=True,
        )
        cls.virtual_disk = VirtualDisk.objects.create(
            virtual_machine=cls.vm,
            name="scsi213",
            size=1024,
        )
        cls.cluster_type = ClusterType.objects.create(
            name="sync-state-cluster-type",
            slug="sync-state-cluster-type",
        )
        cls.cluster_group = ClusterGroup.objects.create(
            name="sync-state-cluster-group",
            slug="sync-state-cluster-group",
        )
        cls.cluster = Cluster.objects.create(
            name="sync-state-cluster",
            type=cls.cluster_type,
            group=cls.cluster_group,
        )
        cls.vm.cluster = cls.cluster
        cls.vm.save()
        cls.vm_for_api.cluster = cls.cluster
        cls.vm_for_api.save()
        cls.endpoint = ProxmoxEndpoint.objects.create(name="sync-state-endpoint")
        cls.proxmox_cluster = ProxmoxCluster.objects.create(
            endpoint=cls.endpoint,
            netbox_cluster=cls.cluster,
            name="pve-sync",
            cluster_id="213",
        )
        cls.storage = ProxmoxStorage.objects.create(
            cluster=cls.cluster,
            name="sync-state-storage",
        )
        cls.proxmox_node = ProxmoxNode.objects.create(
            endpoint=cls.endpoint,
            proxmox_cluster=cls.proxmox_cluster,
            netbox_device=cls.device,
            name="pve-node-sync",
            ip_address="192.0.2.10",
        )
        cls.manufacturer = Manufacturer.objects.create(
            name="sync-state-maker",
            slug="sync-state-maker",
        )
        cls.device_type = DeviceType.objects.create(
            manufacturer=cls.manufacturer,
            model="sync-state-type",
            slug="sync-state-type",
        )
        cls.device_role = DeviceRole.objects.create(
            name="sync-state-role",
            slug="sync-state-role",
        )
        cls.site = Site.objects.create(name="sync-state-site", slug="sync-state-site")

    @classmethod
    def model_cases(cls):
        return (
            (
                ProxboxVirtualMachineSyncState,
                "virtual_machine",
                cls.vm,
                {
                    "endpoint": cls.endpoint,
                    "proxmox_node": cls.proxmox_node,
                    "proxmox_cluster": cls.proxmox_cluster,
                    "proxmox_node_name": "pve-node-sync",
                    "proxmox_cluster_name": "pve-sync",
                    "proxmox_vm_id": 213,
                },
            ),
            (
                ProxboxDeviceSyncState,
                "device",
                cls.device,
                {
                    "endpoint": cls.endpoint,
                    "proxmox_node": cls.proxmox_node,
                    "proxmox_cluster": cls.proxmox_cluster,
                    "proxmox_node_name": "pve-node-sync",
                    "proxmox_cluster_name": "pve-sync",
                    "hardware_chassis_serial": "ABC213",
                },
            ),
            (
                ProxboxClusterSyncState,
                "cluster",
                cls.cluster,
                {
                    "proxmox_cluster": cls.proxmox_cluster,
                    "proxmox_cluster_name": "pve-sync",
                    "proxmox_cluster_raw_id": 213,
                },
            ),
            (
                ProxboxIPAddressSyncState,
                "ip_address",
                cls.ip_address,
                {"proxmox_interface": "net0", "proxmox_mac": "52:54:00:00:02:13"},
            ),
            (
                ProxboxInterfaceSyncState,
                "interface",
                cls.interface,
                {"nic_speed_gbps": 10, "nic_duplex": "full", "nic_link": True},
            ),
            (ProxboxVLANSyncState, "vlan", cls.vlan, {"proxmox_vlan_id": 213}),
            (
                ProxboxClusterGroupSyncState,
                "cluster_group",
                cls.cluster_group,
                {"proxmox_cluster_name": "pve-sync"},
            ),
            (
                ProxboxVirtualDiskSyncState,
                "virtual_disk",
                cls.virtual_disk,
                {
                    "proxbox_storage": cls.storage,
                    "proxbox_storage_raw_id": cls.storage.pk,
                },
            ),
            (
                ProxboxVMInterfaceSyncState,
                "vm_interface",
                cls.vm_interface,
                {
                    "proxbox_bridge": cls.interface,
                    "proxbox_bridge_raw_id": cls.interface.pk,
                },
            ),
            (ProxboxDeviceRoleSyncState, "device_role", cls.device_role, {}),
            (ProxboxDeviceTypeSyncState, "device_type", cls.device_type, {}),
            (ProxboxManufacturerSyncState, "manufacturer", cls.manufacturer, {}),
            (ProxboxSiteSyncState, "site", cls.site, {}),
            (ProxboxClusterTypeSyncState, "cluster_type", cls.cluster_type, {}),
        )


class ProxboxSyncStateModelTest(_SyncStateFixturesMixin, TestCase):
    """Validate model creation, one-to-one uniqueness, and nullable FKs."""

    def test_models_create_with_one_to_one_parent(self) -> None:
        for model, parent_field, parent, defaults in self.model_cases():
            with self.subTest(model=model.__name__):
                row = model.objects.create(**{parent_field: parent}, **defaults)
                self.assertEqual(getattr(row, parent_field), parent)
                self.assertIn("Proxbox sync state", str(row))
                self.assertEqual(parent.proxbox_sync_state, row)
                self.assertEqual(row.get_absolute_url(), parent.get_absolute_url())

    def test_one_to_one_uniqueness_is_enforced(self) -> None:
        for model, parent_field, parent, defaults in self.model_cases():
            with self.subTest(model=model.__name__):
                model.objects.create(**{parent_field: parent}, **defaults)
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        model.objects.create(**{parent_field: parent}, **defaults)

    def test_resolved_fk_fields_can_be_null(self) -> None:
        vm_row = ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=self.vm,
            proxmox_node_name="unresolved-node",
            proxmox_cluster_name="unresolved-cluster",
            proxmox_endpoint_raw_id=99999,
        )
        self.assertIsNone(vm_row.endpoint)
        self.assertIsNone(vm_row.proxmox_node)
        self.assertIsNone(vm_row.proxmox_cluster)
        self.assertEqual(vm_row.proxmox_node_name, "unresolved-node")
        self.assertEqual(vm_row.proxmox_endpoint_raw_id, 99999)

    def test_model_clean_rejects_cross_parent_node_and_cluster_relations(self) -> None:
        other_device = create_test_device("sync-state-model-other-device")
        other_node = ProxmoxNode.objects.create(
            endpoint=self.endpoint,
            proxmox_cluster=self.proxmox_cluster,
            netbox_device=other_device,
            name="pve-node-model-other",
            ip_address="192.0.2.88",
        )
        device_state = ProxboxDeviceSyncState(
            device=self.device_for_api,
            endpoint=self.endpoint,
            proxmox_node=other_node,
            proxmox_cluster=self.proxmox_cluster,
        )
        with self.assertRaises(ValidationError) as device_error:
            device_state.full_clean()
        self.assertIn("proxmox_node", device_error.exception.message_dict)

        other_cluster = Cluster.objects.create(
            name="sync-state-model-other-cluster",
            type=self.cluster_type,
            group=self.cluster_group,
        )
        other_proxmox_cluster = ProxmoxCluster.objects.create(
            endpoint=self.endpoint,
            netbox_cluster=other_cluster,
            name="pve-model-other-cluster",
            cluster_id="model-other",
        )
        cluster_state = ProxboxClusterSyncState(
            cluster=self.cluster,
            proxmox_cluster=other_proxmox_cluster,
        )
        with self.assertRaises(ValidationError) as cluster_error:
            cluster_state.full_clean()
        self.assertIn("proxmox_cluster", cluster_error.exception.message_dict)


class ProxboxSyncStateAPITest(_SyncStateFixturesMixin, TestCase):
    """Validate API list/detail and representative serializer write round trips."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.user = get_user_model().objects.create_user(
            username="sync-state-api",
            is_staff=True,
        )
        cls.token = Token.objects.create(user=cls.user)
        permission = ObjectPermission.objects.create(
            name="sync-state-rw",
            actions=["view", "add", "change", "delete"],
        )
        for model in SYNC_STATE_MODELS:
            permission.object_types.add(ContentType.objects.get_for_model(model))
        permission.users.add(cls.user)
        parent_permission = ObjectPermission.objects.create(
            name="sync-state-parent-view",
            actions=["view"],
        )
        parent_models = {
            parent.__class__ for _model, _field, parent, _data in cls.model_cases()
        }
        parent_models.update(
            {ProxmoxEndpoint, ProxmoxNode, ProxmoxCluster, ProxmoxStorage}
        )
        for model in parent_models:
            parent_permission.object_types.add(ContentType.objects.get_for_model(model))
        parent_permission.users.add(cls.user)
        cls.sidecar_only_user = get_user_model().objects.create_user(
            username="sync-state-sidecar-only",
            is_staff=True,
        )
        cls.sidecar_only_token = Token.objects.create(user=cls.sidecar_only_user)
        sidecar_only_permission = ObjectPermission.objects.create(
            name="sync-state-sidecar-only",
            actions=["view", "add", "change"],
        )
        for model in (ProxboxVirtualMachineSyncState, ProxboxDeviceSyncState):
            sidecar_only_permission.object_types.add(
                ContentType.objects.get_for_model(model)
            )
        sidecar_only_permission.users.add(cls.sidecar_only_user)
        for model, parent_field, parent, defaults in cls.model_cases():
            model.objects.create(**{parent_field: parent}, **defaults)

    def _auth_headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def _token_headers(self, token: Token) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Token {token.key}"}

    def _create_relation_triplet(
        self,
        prefix: str,
        index: int,
        *,
        netbox_cluster: Cluster | None = None,
        netbox_device: Device | None = None,
    ) -> tuple[ProxmoxEndpoint, ProxmoxCluster, ProxmoxNode]:
        endpoint = ProxmoxEndpoint.objects.create(
            name=f"sync-state-api-nplus-{prefix}-endpoint-{index}",
        )
        proxmox_cluster = ProxmoxCluster.objects.create(
            endpoint=endpoint,
            netbox_cluster=netbox_cluster,
            name=f"sync-state-api-nplus-{prefix}-cluster-{index}",
            cluster_id=f"{prefix}-{index}",
        )
        proxmox_node = ProxmoxNode.objects.create(
            endpoint=endpoint,
            proxmox_cluster=proxmox_cluster,
            netbox_device=netbox_device,
            name=f"sync-state-api-nplus-{prefix}-node-{index}",
            ip_address=f"192.0.2.{100 + index}",
        )
        return endpoint, proxmox_cluster, proxmox_node

    def test_api_list_and_detail_for_each_sync_state_model(self) -> None:
        for model in SYNC_STATE_MODELS:
            with self.subTest(model=model.__name__):
                route = _model_route(model)
                list_url = reverse(f"plugins-api:netbox_proxbox-api:{route}-list")
                list_response = self.client.get(list_url, **self._auth_headers())
                self.assertEqual(list_response.status_code, 200, list_response.content)
                self.assertGreaterEqual(list_response.json()["count"], 1)
                row = model.objects.first()
                detail_url = reverse(
                    f"plugins-api:netbox_proxbox-api:{route}-detail",
                    args=[row.pk],
                )
                detail_response = self.client.get(detail_url, **self._auth_headers())
                self.assertEqual(
                    detail_response.status_code,
                    200,
                    detail_response.content,
                )
                self.assertEqual(detail_response.json()["id"], row.pk)

    def test_vm_sync_state_serializer_round_trip(self) -> None:
        url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-list"
        )
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "virtual_machine": {"id": self.vm_for_api.pk},
                    "endpoint": {"id": self.endpoint.pk},
                    "proxmox_node": {"id": self.proxmox_node.pk},
                    "proxmox_node_name": "pve-node-sync",
                    "proxmox_cluster": {"id": self.proxmox_cluster.pk},
                    "proxmox_cluster_name": "pve-sync",
                    "proxmox_endpoint_raw_id": self.endpoint.pk,
                    "proxmox_vm_id": 9001,
                    "proxmox_vm_type": "qemu",
                    "proxmox_start_at_boot": True,
                    "proxmox_status": "running",
                    "last_run_id": "run-api",
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        row = ProxboxVirtualMachineSyncState.objects.get(
            virtual_machine=self.vm_for_api
        )
        self.assertEqual(row.proxmox_vm_id, 9001)
        self.assertEqual(row.endpoint, self.endpoint)
        self.assertEqual(row.proxmox_node, self.proxmox_node)
        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-detail",
            args=[row.pk],
        )
        patch_response = self.client.patch(
            detail_url,
            data=json.dumps({"proxmox_status": "stopped"}),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        row.refresh_from_db()
        self.assertEqual(row.proxmox_status, "stopped")

    def test_vm_sync_state_etag_advances_and_rejects_stale_if_match(self) -> None:
        row = ProxboxVirtualMachineSyncState.objects.get(virtual_machine=self.vm)
        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-detail",
            args=[row.pk],
        )
        get_response = self.client.get(detail_url, **self._auth_headers())
        self.assertEqual(get_response.status_code, 200, get_response.content)
        etag = get_response.headers.get("ETag")
        if _netbox_version_tuple() < (4, 6):
            self.assertIsNone(etag)
            patch_response = self.client.patch(
                detail_url,
                data=json.dumps({"proxmox_status": "paused"}),
                content_type="application/json",
                **self._auth_headers(),
            )
            self.assertEqual(patch_response.status_code, 200, patch_response.content)
            self.assertIsNone(patch_response.headers.get("ETag"))
            return

        self.assertIsNotNone(etag)

        patch_response = self.client.patch(
            detail_url,
            data=json.dumps({"proxmox_status": "paused"}),
            content_type="application/json",
            HTTP_IF_MATCH=etag,
            **self._auth_headers(),
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        new_etag = patch_response.headers.get("ETag")
        self.assertIsNotNone(new_etag)
        self.assertNotEqual(etag, new_etag)

        stale_response = self.client.patch(
            detail_url,
            data=json.dumps({"proxmox_status": "running"}),
            content_type="application/json",
            HTTP_IF_MATCH=etag,
            **self._auth_headers(),
        )
        self.assertEqual(stale_response.status_code, 412, stale_response.content)

    def test_api_lists_endpoint_relations_without_n_plus_one_queries(self) -> None:
        for index in range(5):
            vm = create_test_virtualmachine(f"sync-state-api-nplus-vm-{index}")
            vm.cluster = self.cluster
            vm.save()
            vm_endpoint, vm_cluster, vm_node = self._create_relation_triplet(
                "vm",
                index,
                netbox_cluster=self.cluster,
            )
            ProxboxVirtualMachineSyncState.objects.create(
                virtual_machine=vm,
                endpoint=vm_endpoint,
                proxmox_node=vm_node,
                proxmox_cluster=vm_cluster,
                proxmox_vm_id=9200 + index,
            )
            device = create_test_device(f"sync-state-api-nplus-device-{index}")
            device_endpoint, device_cluster, device_node = (
                self._create_relation_triplet(
                    "device",
                    index,
                    netbox_cluster=self.cluster,
                    netbox_device=device,
                )
            )
            ProxboxDeviceSyncState.objects.create(
                device=device,
                endpoint=device_endpoint,
                proxmox_node=device_node,
                proxmox_cluster=device_cluster,
                proxmox_vmid=str(9300 + index),
            )
            cluster = Cluster.objects.create(
                name=f"sync-state-api-nplus-cluster-{index}",
                type=self.cluster_type,
                group=self.cluster_group,
            )
            cluster_endpoint, cluster_relation, _cluster_node = (
                self._create_relation_triplet(
                    "cluster",
                    index,
                    netbox_cluster=cluster,
                )
            )
            ProxboxClusterSyncState.objects.create(
                cluster=cluster,
                proxmox_cluster=cluster_relation,
                proxmox_cluster_name=f"pve-sync-{cluster_endpoint.pk}",
            )

        relation_table_limits = {
            ProxboxVirtualMachineSyncState: (
                "netbox_proxbox_proxmoxendpoint",
                "netbox_proxbox_proxmoxnode",
                "netbox_proxbox_proxmoxcluster",
            ),
            ProxboxDeviceSyncState: (
                "netbox_proxbox_proxmoxendpoint",
                "netbox_proxbox_proxmoxnode",
                "netbox_proxbox_proxmoxcluster",
            ),
            ProxboxClusterSyncState: ("netbox_proxbox_proxmoxcluster",),
        }

        for model, relation_tables in relation_table_limits.items():
            with self.subTest(model=model.__name__):
                url = reverse(
                    f"plugins-api:netbox_proxbox-api:{_model_route(model)}-list"
                )
                with CaptureQueriesContext(connection) as captured:
                    response = self.client.get(url, **self._auth_headers())
                self.assertEqual(response.status_code, 200, response.content)
                self.assertGreaterEqual(response.json()["count"], 6)
                self.assertLessEqual(
                    len(captured),
                    50,
                    "\n".join(query["sql"] for query in captured.captured_queries),
                )
                for table_name in relation_tables:
                    relation_queries = [
                        query["sql"]
                        for query in captured.captured_queries
                        if table_name in query["sql"].lower()
                    ]
                    self.assertLessEqual(
                        len(relation_queries),
                        4,
                        "\n".join(relation_queries),
                    )
                    self.assertFalse(
                        any(
                            "LIMIT 1" in sql.upper() and " IN " not in sql.upper()
                            for sql in relation_queries
                        ),
                        "\n".join(relation_queries),
                    )

    def test_api_rejects_duplicate_parent_writes_without_500(self) -> None:
        occupied_vm = create_test_virtualmachine("sync-state-duplicate-api-vm")
        reparent_source = create_test_virtualmachine("sync-state-reparent-api-vm")
        ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=occupied_vm,
            proxmox_vm_id=9400,
        )
        reparent_row = ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=reparent_source,
            proxmox_vm_id=9401,
        )
        list_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-list"
        )

        duplicate_response = self.client.post(
            list_url,
            data=json.dumps(
                {
                    "virtual_machine": {"id": occupied_vm.pk},
                    "proxmox_vm_id": 9402,
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(duplicate_response.status_code, 409)

        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-detail",
            args=[reparent_row.pk],
        )
        reparent_response = self.client.patch(
            detail_url,
            data=json.dumps({"virtual_machine": {"id": occupied_vm.pk}}),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(reparent_response.status_code, 409)
        reparent_row.refresh_from_db()
        self.assertEqual(reparent_row.virtual_machine, reparent_source)

    def test_api_maps_duplicate_parent_integrity_error_to_conflict(self) -> None:
        from netbox_proxbox.api.serializers.sync_state import (
            ProxboxSyncStateSerializerMixin,
        )

        occupied_vm = create_test_virtualmachine("sync-state-duplicate-db-api-vm")
        ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=occupied_vm,
            proxmox_vm_id=9450,
        )
        list_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-list"
        )

        with patch.object(
            ProxboxSyncStateSerializerMixin,
            "_validate_parent_uniqueness",
            return_value=None,
        ):
            response = self.client.post(
                list_url,
                data=json.dumps(
                    {
                        "virtual_machine": {"id": occupied_vm.pk},
                        "proxmox_vm_id": 9451,
                    }
                ),
                content_type="application/json",
                **self._auth_headers(),
            )
        self.assertEqual(response.status_code, 409, response.content)

    def test_api_enforces_relation_coherence_and_parent_immutability(self) -> None:
        other_endpoint = ProxmoxEndpoint.objects.create(name="sync-state-other")
        other_cluster = ProxmoxCluster.objects.create(
            endpoint=other_endpoint,
            name="pve-other",
            cluster_id="999",
        )
        other_node = ProxmoxNode.objects.create(
            endpoint=other_endpoint,
            proxmox_cluster=other_cluster,
            name="pve-other-node",
            ip_address="192.0.2.99",
        )
        list_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-list"
        )

        mismatched_node_vm = create_test_virtualmachine("sync-state-mismatched-node-vm")
        mismatched_node_response = self.client.post(
            list_url,
            data=json.dumps(
                {
                    "virtual_machine": {"id": mismatched_node_vm.pk},
                    "endpoint": {"id": self.endpoint.pk},
                    "proxmox_node": {"id": other_node.pk},
                    "proxmox_vm_id": 9500,
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(mismatched_node_response.status_code, 400)

        mismatched_cluster_vm = create_test_virtualmachine(
            "sync-state-mismatched-cluster-vm"
        )
        mismatched_cluster_response = self.client.post(
            list_url,
            data=json.dumps(
                {
                    "virtual_machine": {"id": mismatched_cluster_vm.pk},
                    "endpoint": {"id": self.endpoint.pk},
                    "proxmox_cluster": {"id": other_cluster.pk},
                    "proxmox_vm_id": 9501,
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(mismatched_cluster_response.status_code, 400)

        coherent_vm = create_test_virtualmachine("sync-state-coherent-vm")
        coherent_response = self.client.post(
            list_url,
            data=json.dumps(
                {
                    "virtual_machine": {"id": coherent_vm.pk},
                    "proxmox_node": {"id": self.proxmox_node.pk},
                    "proxmox_vm_id": 9502,
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(coherent_response.status_code, 201, coherent_response.content)
        coherent_row = ProxboxVirtualMachineSyncState.objects.get(
            virtual_machine=coherent_vm
        )
        self.assertEqual(coherent_row.endpoint, self.endpoint)
        self.assertEqual(coherent_row.proxmox_cluster, self.proxmox_cluster)

        immutable_source = create_test_virtualmachine("sync-state-immutable-source")
        immutable_target = create_test_virtualmachine("sync-state-immutable-target")
        immutable_row = ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=immutable_source,
            proxmox_vm_id=9503,
        )
        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-detail",
            args=[immutable_row.pk],
        )
        immutable_response = self.client.patch(
            detail_url,
            data=json.dumps({"virtual_machine": {"id": immutable_target.pk}}),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(immutable_response.status_code, 400)
        immutable_row.refresh_from_db()
        self.assertEqual(immutable_row.virtual_machine, immutable_source)

    def test_api_rejects_cross_parent_node_and_cluster_relations(self) -> None:
        other_device = create_test_device("sync-state-api-other-device")
        other_node = ProxmoxNode.objects.create(
            endpoint=self.endpoint,
            proxmox_cluster=self.proxmox_cluster,
            netbox_device=other_device,
            name="pve-node-api-other",
            ip_address="192.0.2.89",
        )
        device_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxdevicesyncstate-list"
        )
        device_response = self.client.post(
            device_url,
            data=json.dumps(
                {
                    "device": {"id": self.device_for_api.pk},
                    "endpoint": {"id": self.endpoint.pk},
                    "proxmox_node": {"id": other_node.pk},
                    "proxmox_cluster": {"id": self.proxmox_cluster.pk},
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(device_response.status_code, 400, device_response.content)
        self.assertIn("proxmox_node", device_response.json())
        self.assertFalse(
            ProxboxDeviceSyncState.objects.filter(device=self.device_for_api).exists()
        )

        target_cluster = Cluster.objects.create(
            name="sync-state-api-target-cluster",
            type=self.cluster_type,
            group=self.cluster_group,
        )
        other_netbox_cluster = Cluster.objects.create(
            name="sync-state-api-other-cluster",
            type=self.cluster_type,
            group=self.cluster_group,
        )
        other_proxmox_cluster = ProxmoxCluster.objects.create(
            endpoint=self.endpoint,
            netbox_cluster=other_netbox_cluster,
            name="pve-api-other-cluster",
            cluster_id="api-other",
        )
        cluster_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxclustersyncstate-list"
        )
        cluster_response = self.client.post(
            cluster_url,
            data=json.dumps(
                {
                    "cluster": {"id": target_cluster.pk},
                    "proxmox_cluster": {"id": other_proxmox_cluster.pk},
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(cluster_response.status_code, 400, cluster_response.content)
        self.assertIn("proxmox_cluster", cluster_response.json())
        self.assertFalse(
            ProxboxClusterSyncState.objects.filter(cluster=target_cluster).exists()
        )

    def test_api_hides_sidecar_when_parent_is_not_visible(self) -> None:
        headers = self._token_headers(self.sidecar_only_token)
        list_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-list"
        )
        list_response = self.client.get(list_url, **headers)
        self.assertEqual(list_response.status_code, 200, list_response.content)
        self.assertEqual(list_response.json()["count"], 0)

        row = ProxboxVirtualMachineSyncState.objects.get(virtual_machine=self.vm)
        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-detail",
            args=[row.pk],
        )
        detail_response = self.client.get(detail_url, **headers)
        self.assertEqual(detail_response.status_code, 404, detail_response.content)

        device_list_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxdevicesyncstate-list"
        )
        device_list_response = self.client.get(device_list_url, **headers)
        self.assertEqual(
            device_list_response.status_code,
            200,
            device_list_response.content,
        )
        self.assertEqual(device_list_response.json()["count"], 0)

    def test_api_masks_hidden_nested_endpoint_node_and_cluster_relations(self) -> None:
        token = _create_api_token(
            "sync-state-hidden-nested-relations",
            (
                ProxboxVirtualMachineSyncState,
                ProxboxDeviceSyncState,
                ProxboxClusterSyncState,
            ),
            {VirtualMachine, Device, Cluster},
        )
        headers = _auth_headers(token)

        vm_row = ProxboxVirtualMachineSyncState.objects.get(virtual_machine=self.vm)
        vm_detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-detail",
            args=[vm_row.pk],
        )
        vm_response = self.client.get(vm_detail_url, **headers)
        self.assertEqual(vm_response.status_code, 200, vm_response.content)
        vm_data = vm_response.json()
        self.assertEqual(vm_data["virtual_machine"]["id"], self.vm.pk)
        self.assertIsNone(vm_data["endpoint"])
        self.assertIsNone(vm_data["proxmox_node"])
        self.assertIsNone(vm_data["proxmox_cluster"])

        device_row = ProxboxDeviceSyncState.objects.get(device=self.device)
        device_detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxdevicesyncstate-detail",
            args=[device_row.pk],
        )
        device_response = self.client.get(device_detail_url, **headers)
        self.assertEqual(device_response.status_code, 200, device_response.content)
        device_data = device_response.json()
        self.assertEqual(device_data["device"]["id"], self.device.pk)
        self.assertIsNone(device_data["endpoint"])
        self.assertIsNone(device_data["proxmox_node"])
        self.assertIsNone(device_data["proxmox_cluster"])

        cluster_row = ProxboxClusterSyncState.objects.get(cluster=self.cluster)
        cluster_detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxclustersyncstate-detail",
            args=[cluster_row.pk],
        )
        cluster_response = self.client.get(cluster_detail_url, **headers)
        self.assertEqual(cluster_response.status_code, 200, cluster_response.content)
        cluster_data = cluster_response.json()
        self.assertEqual(cluster_data["cluster"]["id"], self.cluster.pk)
        self.assertIsNone(cluster_data["proxmox_cluster"])

    def test_api_rejects_create_with_hidden_parent(self) -> None:
        url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-list"
        )
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "virtual_machine": {"id": self.vm_for_api.pk},
                    "proxmox_vm_id": 9100,
                }
            ),
            content_type="application/json",
            **self._token_headers(self.sidecar_only_token),
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(
            ProxboxVirtualMachineSyncState.objects.filter(
                virtual_machine=self.vm_for_api,
            ).exists()
        )

    def test_api_rejects_patch_to_hidden_parent(self) -> None:
        limited_user = get_user_model().objects.create_user(
            username="sync-state-limited-parent",
            is_staff=True,
        )
        limited_token = Token.objects.create(user=limited_user)
        sidecar_permission = ObjectPermission.objects.create(
            name="sync-state-limited-sidecar",
            actions=["view", "add", "change"],
        )
        sidecar_permission.object_types.add(
            ContentType.objects.get_for_model(ProxboxVirtualMachineSyncState)
        )
        sidecar_permission.users.add(limited_user)
        parent_permission = ObjectPermission.objects.create(
            name="sync-state-limited-parent-view",
            actions=["view"],
            constraints={"pk": self.vm_for_api.pk},
        )
        parent_permission.object_types.add(
            ContentType.objects.get_for_model(type(self.vm))
        )
        parent_permission.users.add(limited_user)
        row = ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=self.vm_for_api,
            proxmox_vm_id=9101,
        )

        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualmachinesyncstate-detail",
            args=[row.pk],
        )
        response = self.client.patch(
            detail_url,
            data=json.dumps({"virtual_machine": {"id": self.vm.pk}}),
            content_type="application/json",
            **self._token_headers(limited_token),
        )
        self.assertEqual(response.status_code, 400, response.content)
        row.refresh_from_db()
        self.assertEqual(row.virtual_machine, self.vm_for_api)

    def test_api_rejects_and_hides_hidden_storage_relation(self) -> None:
        token = _create_api_token(
            "sync-state-hidden-storage",
            (ProxboxVirtualDiskSyncState,),
            {VirtualDisk},
        )
        hidden_storage = ProxmoxStorage.objects.create(
            cluster=self.cluster,
            name="sync-state-hidden-storage",
        )
        attach_disk = VirtualDisk.objects.create(
            virtual_machine=self.vm,
            name="scsi-hidden-storage-attach",
            size=1024,
        )
        patch_disk = VirtualDisk.objects.create(
            virtual_machine=self.vm,
            name="scsi-hidden-storage-patch",
            size=1024,
        )
        disclosed_disk = VirtualDisk.objects.create(
            virtual_machine=self.vm,
            name="scsi-hidden-storage-disclose",
            size=1024,
        )
        patch_row = ProxboxVirtualDiskSyncState.objects.create(
            virtual_disk=patch_disk,
        )
        hidden_row = ProxboxVirtualDiskSyncState.objects.create(
            virtual_disk=disclosed_disk,
            proxbox_storage=hidden_storage,
            proxbox_storage_raw_id=hidden_storage.pk,
        )
        headers = _auth_headers(token)
        list_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualdisksyncstate-list"
        )

        create_response = self.client.post(
            list_url,
            data=json.dumps(
                {
                    "virtual_disk": {"id": attach_disk.pk},
                    "proxbox_storage": {"id": hidden_storage.pk},
                }
            ),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(create_response.status_code, 400, create_response.content)
        self.assertFalse(
            ProxboxVirtualDiskSyncState.objects.filter(
                virtual_disk=attach_disk,
            ).exists()
        )

        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualdisksyncstate-detail",
            args=[patch_row.pk],
        )
        patch_response = self.client.patch(
            detail_url,
            data=json.dumps({"proxbox_storage": {"id": hidden_storage.pk}}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(patch_response.status_code, 400, patch_response.content)
        patch_row.refresh_from_db()
        self.assertIsNone(patch_row.proxbox_storage)

        hidden_detail_url = reverse(
            "plugins-api:netbox_proxbox-api:proxboxvirtualdisksyncstate-detail",
            args=[hidden_row.pk],
        )
        detail_response = self.client.get(hidden_detail_url, **headers)
        self.assertEqual(detail_response.status_code, 404, detail_response.content)
        list_response = self.client.get(list_url, **headers)
        self.assertEqual(list_response.status_code, 200, list_response.content)
        self.assertNotIn(str(hidden_storage.pk), list_response.content.decode())

    def test_filterset_basic_filter(self) -> None:
        filtered = ProxboxVirtualMachineSyncStateFilterSet(
            data={"proxmox_vm_id": "213"},
            queryset=ProxboxVirtualMachineSyncState.objects.all(),
        ).qs
        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.get().virtual_machine, self.vm)


class ProxboxSyncStateBackfillTest(_SyncStateFixturesMixin, TestCase):
    """Validate zero-loss custom_field_data backfill behavior."""

    def test_backfill_resolves_references_and_preserves_fallbacks(self) -> None:
        self.vm.custom_field_data = {
            "proxmox_vm_id": 213,
            "proxmox_vm_type": "qemu",
            "proxmox_start_at_boot": True,
            "proxmox_qemu_agent": False,
            "proxmox_node": "pve-node-sync",
            "proxmox_cluster": "pve-sync",
            "proxmox_status": "running",
            "proxmox_uptime": 3600,
            "proxmox_link": "https://pve.example.invalid/#v1",
            "proxmox_last_updated": "2026-07-17T18:00:00Z",
            "proxbox_last_run_id": "run-213",
            "proxmox_endpoint_id": self.endpoint.pk,
        }
        self.vm.save()
        self.device.custom_field_data = {
            "proxmox_node": "pve-node-sync",
            "proxmox_cluster": "pve-sync",
            "proxmox_vmid": "node-213",
            "hardware_chassis_serial": "SERIAL213",
            "hardware_chassis_manufacturer": "NMC",
            "hardware_chassis_product": "Cloud Node",
            "proxmox_last_updated": "2026-07-17T18:05:00Z",
            "proxbox_last_run_id": "run-device",
        }
        self.device.save()
        self.vm_nomatch.custom_field_data = {
            "proxmox_vm_id": 999,
            "proxmox_node": "missing-node",
            "proxmox_cluster": "missing-cluster",
            "proxmox_endpoint_id": 99999,
        }
        self.vm_nomatch.save()

        migration = importlib.import_module(
            "netbox_proxbox.migrations.0066_backfill_proxbox_sync_state"
        )
        migration.backfill_proxbox_sync_state(django_apps, None)

        vm_state = ProxboxVirtualMachineSyncState.objects.get(virtual_machine=self.vm)
        self.assertEqual(vm_state.proxmox_vm_id, 213)
        self.assertEqual(vm_state.proxmox_vm_type, "qemu")
        self.assertTrue(vm_state.proxmox_start_at_boot)
        self.assertFalse(vm_state.proxmox_qemu_agent)
        self.assertEqual(vm_state.endpoint, self.endpoint)
        self.assertEqual(vm_state.proxmox_node, self.proxmox_node)
        self.assertEqual(vm_state.proxmox_cluster, self.proxmox_cluster)
        self.assertEqual(vm_state.proxmox_node_name, "pve-node-sync")
        self.assertEqual(vm_state.proxmox_cluster_name, "pve-sync")
        self.assertEqual(vm_state.last_run_id, "run-213")
        self.assertIsNotNone(vm_state.last_updated)
        self.assertIsNotNone(vm_state.proxmox_last_updated)

        device_state = ProxboxDeviceSyncState.objects.get(device=self.device)
        self.assertEqual(device_state.endpoint, self.endpoint)
        self.assertEqual(device_state.proxmox_node, self.proxmox_node)
        self.assertEqual(device_state.proxmox_cluster, self.proxmox_cluster)
        self.assertEqual(device_state.hardware_chassis_serial, "SERIAL213")
        self.assertEqual(device_state.last_run_id, "run-device")

        nomatch = ProxboxVirtualMachineSyncState.objects.get(
            virtual_machine=self.vm_nomatch
        )
        self.assertIsNone(nomatch.endpoint)
        self.assertIsNone(nomatch.proxmox_node)
        self.assertIsNone(nomatch.proxmox_cluster)
        self.assertEqual(nomatch.proxmox_node_name, "missing-node")
        self.assertEqual(nomatch.proxmox_cluster_name, "missing-cluster")
        self.assertEqual(nomatch.proxmox_endpoint_raw_id, 99999)

        # Idempotent: a second run updates the same rows instead of duplicating.
        migration.backfill_proxbox_sync_state(django_apps, None)
        self.assertEqual(
            ProxboxVirtualMachineSyncState.objects.filter(
                virtual_machine=self.vm
            ).count(),
            1,
        )

    def test_backfill_preserves_sparse_preexisting_sidecar_values(self) -> None:
        ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=self.vm,
            endpoint=self.endpoint,
            proxmox_node=self.proxmox_node,
            proxmox_cluster=self.proxmox_cluster,
            proxmox_node_name="pve-node-sync",
            proxmox_cluster_name="pve-sync",
            proxmox_vm_id=8800,
            proxmox_vm_type="qemu",
            proxmox_status="api-populated",
            proxmox_os="debian",
            proxmox_uptime=3600,
            last_run_id="api-run",
        )
        self.vm.custom_field_data = {
            "proxmox_status": "reflected-running",
        }
        self.vm.save()

        migration = _backfill_module()
        migration.backfill_proxbox_sync_state(django_apps, None)
        migration.backfill_proxbox_sync_state(django_apps, None)

        state = ProxboxVirtualMachineSyncState.objects.get(virtual_machine=self.vm)
        self.assertEqual(state.proxmox_status, "reflected-running")
        self.assertEqual(state.proxmox_vm_id, 8800)
        self.assertEqual(state.proxmox_vm_type, "qemu")
        self.assertEqual(state.proxmox_os, "debian")
        self.assertEqual(state.proxmox_uptime, 3600)
        self.assertEqual(state.last_run_id, "api-run")
        self.assertEqual(state.endpoint, self.endpoint)
        self.assertEqual(state.proxmox_node, self.proxmox_node)
        self.assertEqual(state.proxmox_cluster, self.proxmox_cluster)
        self.assertEqual(
            ProxboxVirtualMachineSyncState.objects.filter(
                virtual_machine=self.vm,
            ).count(),
            1,
        )

    def test_backfill_keeps_backend_endpoint_id_raw_without_fk_resolution(self) -> None:
        wrong_plugin_endpoint = ProxmoxEndpoint.objects.create(
            name="sync-state-wrong-plugin-endpoint"
        )
        vm = create_test_virtualmachine("sync-state-backend-endpoint-id")
        vm.cluster = None
        vm.custom_field_data = {
            "proxmox_vm_id": 501,
            "proxmox_endpoint_id": wrong_plugin_endpoint.pk,
        }
        vm.save()

        migration = importlib.import_module(
            "netbox_proxbox.migrations.0066_backfill_proxbox_sync_state"
        )
        migration.backfill_proxbox_sync_state(django_apps, None)

        state = ProxboxVirtualMachineSyncState.objects.get(virtual_machine=vm)
        self.assertIsNone(state.endpoint)
        self.assertEqual(state.proxmox_endpoint_raw_id, wrong_plugin_endpoint.pk)

    def test_backfill_leaves_duplicate_node_names_unresolved_without_endpoint(
        self,
    ) -> None:
        second_endpoint = ProxmoxEndpoint.objects.create(
            name="sync-state-second-endpoint"
        )
        ProxmoxNode.objects.create(
            endpoint=self.endpoint,
            name="duplicate-node",
            ip_address="192.0.2.31",
        )
        ProxmoxNode.objects.create(
            endpoint=second_endpoint,
            name="duplicate-node",
            ip_address="192.0.2.32",
        )
        vm = create_test_virtualmachine("sync-state-duplicate-node-vm")
        vm.cluster = None
        vm.custom_field_data = {
            "proxmox_vm_id": 502,
            "proxmox_node": "duplicate-node",
        }
        vm.save()

        migration = importlib.import_module(
            "netbox_proxbox.migrations.0066_backfill_proxbox_sync_state"
        )
        migration.backfill_proxbox_sync_state(django_apps, None)

        state = ProxboxVirtualMachineSyncState.objects.get(virtual_machine=vm)
        self.assertIsNone(state.endpoint)
        self.assertIsNone(state.proxmox_node)
        self.assertEqual(state.proxmox_node_name, "duplicate-node")

    def test_backfill_skips_non_mapping_payloads_and_coerces_ints_safely(
        self,
    ) -> None:
        scalar_vm = create_test_virtualmachine("sync-state-scalar-cfd")
        _set_custom_field_data(scalar_vm, "proxmox_vm_id")
        list_vm = create_test_virtualmachine("sync-state-list-cfd")
        _set_custom_field_data(list_vm, ["proxmox_vm_id"])
        coercion_vm = create_test_virtualmachine("sync-state-int-coercion")
        _set_custom_field_data(
            coercion_vm,
            {
                "proxmox_vm_id": True,
                "proxmox_uptime": 100.9,
                "proxmox_migration_duration": "42",
            },
        )

        migration = _backfill_module()
        migration.backfill_proxbox_sync_state(django_apps, None)

        self.assertFalse(
            ProxboxVirtualMachineSyncState.objects.filter(
                virtual_machine=scalar_vm,
            ).exists()
        )
        self.assertFalse(
            ProxboxVirtualMachineSyncState.objects.filter(
                virtual_machine=list_vm,
            ).exists()
        )
        state = ProxboxVirtualMachineSyncState.objects.get(
            virtual_machine=coercion_vm,
        )
        self.assertIsNone(state.proxmox_vm_id)
        self.assertIsNone(state.proxmox_uptime)
        self.assertEqual(state.proxmox_migration_duration, 42)

    def test_backfill_sanitizes_bad_values_without_aborting(self) -> None:
        self.vm.custom_field_data = {
            "proxmox_vm_id": 503,
            "proxmox_status": "running",
        }
        self.vm.save()
        bad_vm = create_test_virtualmachine("sync-state-bad-values-vm")
        bad_vm.cluster = None
        bad_vm.custom_field_data = {
            "proxmox_vm_id": 2**31,
            "proxmox_os": "x" * 300,
            "proxmox_link": "not-a-url",
            "proxmox_last_updated": "not-a-date",
            "proxmox_storage_ids": {"storage": "local-lvm"},
        }
        bad_vm.save()

        migration = importlib.import_module(
            "netbox_proxbox.migrations.0066_backfill_proxbox_sync_state"
        )
        migration.backfill_proxbox_sync_state(django_apps, None)

        good_state = ProxboxVirtualMachineSyncState.objects.get(virtual_machine=self.vm)
        self.assertEqual(good_state.proxmox_vm_id, 503)
        self.assertEqual(good_state.proxmox_status, "running")

        bad_state = ProxboxVirtualMachineSyncState.objects.get(virtual_machine=bad_vm)
        self.assertIsNone(bad_state.proxmox_vm_id)
        self.assertEqual(len(bad_state.proxmox_os), 255)
        self.assertEqual(bad_state.proxmox_link, "")
        self.assertIsNone(bad_state.proxmox_last_updated)
        self.assertEqual(bad_state.proxmox_storage_ids, '{"storage": "local-lvm"}')

    def test_backfill_raises_after_structural_row_creation_failures(self) -> None:
        self.vm.custom_field_data = {
            "proxmox_vm_id": 504,
            "proxmox_status": "running",
        }
        self.vm.save()
        bad_vm = create_test_virtualmachine("sync-state-row-failure-vm")
        bad_vm.cluster = None
        bad_vm.custom_field_data = {
            "proxmox_vm_id": 505,
            "proxmox_status": "running",
        }
        bad_vm.save()

        migration = importlib.import_module(
            "netbox_proxbox.migrations.0066_backfill_proxbox_sync_state"
        )
        manager = ProxboxVirtualMachineSyncState.objects
        original_update_or_create = manager.update_or_create
        original_get_or_create = manager.get_or_create

        def update_or_create_side_effect(*args, **kwargs):
            if kwargs.get("virtual_machine") == bad_vm:
                raise IntegrityError("forced row creation failure")
            return original_update_or_create(*args, **kwargs)

        def get_or_create_side_effect(*args, **kwargs):
            if kwargs.get("virtual_machine") == bad_vm:
                raise IntegrityError("forced row creation failure")
            return original_get_or_create(*args, **kwargs)

        with (
            patch.object(
                manager,
                "update_or_create",
                side_effect=update_or_create_side_effect,
            ),
            patch.object(
                manager,
                "get_or_create",
                side_effect=get_or_create_side_effect,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                rf"virtual_machine_id={bad_vm.pk!r}",
            ):
                migration.backfill_proxbox_sync_state(django_apps, None)

        self.assertTrue(
            ProxboxVirtualMachineSyncState.objects.filter(
                virtual_machine=self.vm,
            ).exists()
        )
        self.assertFalse(
            ProxboxVirtualMachineSyncState.objects.filter(
                virtual_machine=bad_vm,
            ).exists()
        )

    def test_reverse_backfill_is_non_destructive_for_api_created_rows(self) -> None:
        row = ProxboxVirtualMachineSyncState.objects.create(
            virtual_machine=self.vm,
            proxmox_status="api-created",
        )

        migration = importlib.import_module(
            "netbox_proxbox.migrations.0066_backfill_proxbox_sync_state"
        )
        migration.reverse_backfill_proxbox_sync_state(django_apps, None)

        self.assertTrue(
            ProxboxVirtualMachineSyncState.objects.filter(
                pk=row.pk,
                proxmox_status="api-created",
            ).exists()
        )


class ProxboxSyncStateHistoricalMigrationTest(TransactionTestCase):
    """Exercise sync-state migrations through historical app registries."""

    def _migrate_to(self, target: tuple[str, str]):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        executor = MigrationExecutor(connection)
        return executor.loader.project_state([target]).apps

    def _seed_sync_state_sources(self) -> dict[str, int]:
        cluster_type = ClusterType.objects.create(
            name="migration-sync-state-cluster-type",
            slug="migration-sync-state-cluster-type",
        )
        cluster_group = ClusterGroup.objects.create(
            name="migration-sync-state-cluster-group",
            slug="migration-sync-state-cluster-group",
        )
        cluster = Cluster.objects.create(
            name="migration-sync-state-cluster",
            type=cluster_type,
            group=cluster_group,
        )
        endpoint = ProxmoxEndpoint.objects.create(name="migration-sync-state-endpoint")
        proxmox_cluster = ProxmoxCluster.objects.create(
            endpoint=endpoint,
            netbox_cluster=cluster,
            name="migration-pve",
            cluster_id="6600",
        )
        device = create_test_device("migration-sync-state-device")
        proxmox_node = ProxmoxNode.objects.create(
            endpoint=endpoint,
            proxmox_cluster=proxmox_cluster,
            netbox_device=device,
            name="migration-node",
            ip_address="192.0.2.66",
        )
        storage = ProxmoxStorage.objects.create(
            cluster=cluster,
            name="migration-sync-state-storage",
        )
        vm = create_test_virtualmachine("migration-sync-state-vm")
        vm.cluster = cluster
        vm.save()
        bridge = Interface.objects.create(device=device, name="migration-vmbr0")
        ip_address = IPAddress.objects.create(address="192.0.2.66/24")
        vlan = VLAN.objects.create(name="migration-sync-state-vlan", vid=660)
        virtual_disk = VirtualDisk.objects.create(
            virtual_machine=vm,
            name="migration-scsi0",
            size=1024,
        )
        vm_interface = VMInterface.objects.create(
            virtual_machine=vm,
            name="migration-net0",
            enabled=True,
        )
        manufacturer = Manufacturer.objects.create(
            name="migration-sync-state-maker",
            slug="migration-sync-state-maker",
        )
        device_type = DeviceType.objects.create(
            manufacturer=manufacturer,
            model="migration-sync-state-type",
            slug="migration-sync-state-type",
        )
        device_role = DeviceRole.objects.create(
            name="migration-sync-state-role",
            slug="migration-sync-state-role",
        )
        site = Site.objects.create(
            name="migration-sync-state-site",
            slug="migration-sync-state-site",
        )

        _set_custom_field_data(
            vm,
            {
                "proxmox_vm_id": 6601,
                "proxmox_node": "migration-node",
                "proxmox_cluster": "migration-pve",
                "proxmox_status": "running",
                "proxbox_last_run_id": "migration-vm-run",
            },
        )
        _set_custom_field_data(
            device,
            {
                "proxmox_node": "migration-node",
                "proxmox_cluster": "migration-pve",
                "hardware_chassis_serial": "MIG6600",
            },
        )
        _set_custom_field_data(
            cluster,
            {
                "proxmox_cluster_name": "migration-pve",
                "proxmox_cluster_status": "online",
                "proxmox_cluster_id": 6600,
            },
        )
        _set_custom_field_data(
            ip_address,
            {
                "proxmox_interface": "eth0",
                "proxmox_mac": "52:54:00:00:66:00",
                "proxmox_ip_addresses": "192.0.2.66",
            },
        )
        _set_custom_field_data(
            bridge,
            {
                "nic_speed_gbps": 25,
                "nic_duplex": "full",
                "nic_link": True,
            },
        )
        _set_custom_field_data(vlan, {"proxmox_vlan_id": 660})
        _set_custom_field_data(
            cluster_group,
            {
                "proxmox_cluster_name": "migration-pve",
                "proxmox_cluster_status": "online",
            },
        )
        _set_custom_field_data(
            virtual_disk,
            {
                "proxbox_storage_id": {"id": storage.pk},
                "proxmox_last_updated": "2026-07-17T18:20:00Z",
            },
        )
        _set_custom_field_data(
            vm_interface,
            {
                "proxbox_bridge": {"id": bridge.pk},
                "proxmox_last_updated": "2026-07-17T18:25:00Z",
            },
        )
        for obj in (device_role, device_type, manufacturer, site, cluster_type):
            _set_custom_field_data(
                obj,
                {"proxmox_last_updated": "2026-07-17T18:30:00Z"},
            )

        return {
            "vm": vm.pk,
            "device": device.pk,
            "cluster": cluster.pk,
            "ip_address": ip_address.pk,
            "interface": bridge.pk,
            "vlan": vlan.pk,
            "cluster_group": cluster_group.pk,
            "virtual_disk": virtual_disk.pk,
            "vm_interface": vm_interface.pk,
            "device_role": device_role.pk,
            "device_type": device_type.pk,
            "manufacturer": manufacturer.pk,
            "site": site.pk,
            "cluster_type": cluster_type.pk,
            "storage": storage.pk,
            "bridge": bridge.pk,
            "endpoint": endpoint.pk,
            "proxmox_node": proxmox_node.pk,
            "proxmox_cluster": proxmox_cluster.pk,
        }

    def _seed_relation_edge_case_sources(self, ids: dict[str, int]) -> dict:
        vm = VirtualMachine.objects.get(pk=ids["vm"])
        overflow_storage_raw = {"id": "999999999999999999999999"}
        unresolved_storage_raw = {"id": 987654321}
        named_bridge_raw = {"name": "vmbr0"}

        overflow_disk = VirtualDisk.objects.create(
            virtual_machine=vm,
            name="migration-overflow-scsi0",
            size=1024,
        )
        _set_custom_field_data(
            overflow_disk,
            {"proxbox_storage_id": overflow_storage_raw},
        )
        unresolved_disk = VirtualDisk.objects.create(
            virtual_machine=vm,
            name="migration-unresolved-scsi0",
            size=1024,
        )
        _set_custom_field_data(
            unresolved_disk,
            {"proxbox_storage_id": unresolved_storage_raw},
        )
        named_bridge_interface = VMInterface.objects.create(
            virtual_machine=vm,
            name="migration-named-net0",
            enabled=True,
        )
        _set_custom_field_data(
            named_bridge_interface,
            {"proxbox_bridge": named_bridge_raw},
        )
        return {
            "overflow_disk": overflow_disk.pk,
            "overflow_storage_raw": overflow_storage_raw,
            "unresolved_disk": unresolved_disk.pk,
            "unresolved_storage_raw": unresolved_storage_raw,
            "named_bridge_interface": named_bridge_interface.pk,
            "named_bridge_raw": named_bridge_raw,
        }

    def _expected_sidecar_rows(self, ids: dict[str, int]):
        return (
            ("ProxboxVirtualMachineSyncState", "virtual_machine_id", ids["vm"]),
            ("ProxboxDeviceSyncState", "device_id", ids["device"]),
            ("ProxboxClusterSyncState", "cluster_id", ids["cluster"]),
            ("ProxboxIPAddressSyncState", "ip_address_id", ids["ip_address"]),
            ("ProxboxInterfaceSyncState", "interface_id", ids["interface"]),
            ("ProxboxVLANSyncState", "vlan_id", ids["vlan"]),
            (
                "ProxboxClusterGroupSyncState",
                "cluster_group_id",
                ids["cluster_group"],
            ),
            ("ProxboxVirtualDiskSyncState", "virtual_disk_id", ids["virtual_disk"]),
            (
                "ProxboxVMInterfaceSyncState",
                "vm_interface_id",
                ids["vm_interface"],
            ),
            ("ProxboxDeviceRoleSyncState", "device_role_id", ids["device_role"]),
            ("ProxboxDeviceTypeSyncState", "device_type_id", ids["device_type"]),
            ("ProxboxManufacturerSyncState", "manufacturer_id", ids["manufacturer"]),
            ("ProxboxSiteSyncState", "site_id", ids["site"]),
            ("ProxboxClusterTypeSyncState", "cluster_type_id", ids["cluster_type"]),
        )

    def _sidecar_counts(self, apps) -> dict[str, int]:
        return {
            model.__name__: apps.get_model(
                "netbox_proxbox",
                model.__name__,
            ).objects.count()
            for model in SYNC_STATE_MODELS
        }

    def _assert_all_sidecars_exist(self, apps, ids: dict[str, int]) -> None:
        for model_name, parent_field, parent_id in self._expected_sidecar_rows(ids):
            with self.subTest(model=model_name):
                Model = apps.get_model("netbox_proxbox", model_name)
                self.assertEqual(
                    Model.objects.filter(**{parent_field: parent_id}).count(),
                    1,
                )

    def _assert_0066_backfill_values(self, apps, ids: dict[str, int]) -> None:
        VMState = apps.get_model("netbox_proxbox", "ProxboxVirtualMachineSyncState")
        vm_state = VMState.objects.get(virtual_machine_id=ids["vm"])
        self.assertEqual(vm_state.proxmox_vm_id, 6601)
        self.assertEqual(vm_state.endpoint_id, ids["endpoint"])
        self.assertEqual(vm_state.proxmox_node_id, ids["proxmox_node"])
        self.assertEqual(vm_state.proxmox_cluster_id, ids["proxmox_cluster"])

        InterfaceState = apps.get_model("netbox_proxbox", "ProxboxInterfaceSyncState")
        interface_state = InterfaceState.objects.get(interface_id=ids["interface"])
        self.assertEqual(interface_state.nic_speed_gbps, 25)
        self.assertEqual(interface_state.nic_duplex, "full")
        self.assertTrue(interface_state.nic_link)

        VLANState = apps.get_model("netbox_proxbox", "ProxboxVLANSyncState")
        self.assertEqual(
            VLANState.objects.get(vlan_id=ids["vlan"]).proxmox_vlan_id, 660
        )

    def _assert_0066_relation_payloads(self, apps, ids: dict[str, int]) -> None:
        DiskState = apps.get_model("netbox_proxbox", "ProxboxVirtualDiskSyncState")
        disk_state = DiskState.objects.get(virtual_disk_id=ids["virtual_disk"])
        self.assertEqual(disk_state.proxbox_storage_id, {"id": ids["storage"]})

        VMInterfaceState = apps.get_model(
            "netbox_proxbox",
            "ProxboxVMInterfaceSyncState",
        )
        interface_state = VMInterfaceState.objects.get(
            vm_interface_id=ids["vm_interface"],
        )
        self.assertEqual(interface_state.proxbox_bridge, {"id": ids["bridge"]})

    def _assert_0066_relation_schema(self, apps) -> None:
        DiskState = apps.get_model("netbox_proxbox", "ProxboxVirtualDiskSyncState")
        disk_fields = {field.name: field for field in DiskState._meta.fields}
        self.assertEqual(
            disk_fields["proxbox_storage_id"].get_internal_type(),
            "JSONField",
        )
        self.assertNotIn("proxbox_storage", disk_fields)
        self.assertNotIn("proxbox_storage_raw_id", disk_fields)

        VMInterfaceState = apps.get_model(
            "netbox_proxbox",
            "ProxboxVMInterfaceSyncState",
        )
        interface_fields = {
            field.name: field for field in VMInterfaceState._meta.fields
        }
        self.assertEqual(
            interface_fields["proxbox_bridge"].get_internal_type(),
            "JSONField",
        )
        self.assertNotIn("proxbox_bridge_raw_id", interface_fields)

    def _assert_0067_relation_schema(self, apps) -> None:
        DiskState = apps.get_model("netbox_proxbox", "ProxboxVirtualDiskSyncState")
        disk_fields = {field.name: field for field in DiskState._meta.fields}
        self.assertEqual(
            disk_fields["proxbox_storage_id"].get_internal_type(),
            "JSONField",
        )
        self.assertEqual(
            disk_fields["proxbox_storage_fk"].get_internal_type(),
            "ForeignKey",
        )
        self.assertIn("proxbox_storage_raw_id", disk_fields)
        self.assertIn("proxbox_storage_raw_value", disk_fields)
        self.assertNotIn("proxbox_storage", disk_fields)

        VMInterfaceState = apps.get_model(
            "netbox_proxbox",
            "ProxboxVMInterfaceSyncState",
        )
        interface_fields = {
            field.name: field for field in VMInterfaceState._meta.fields
        }
        self.assertEqual(
            interface_fields["proxbox_bridge"].get_internal_type(),
            "JSONField",
        )
        self.assertEqual(
            interface_fields["proxbox_bridge_fk"].get_internal_type(),
            "ForeignKey",
        )
        self.assertIn("proxbox_bridge_raw_id", interface_fields)
        self.assertIn("proxbox_bridge_raw_value", interface_fields)

    def _assert_0068_relation_payloads(self, apps, ids: dict[str, int]) -> None:
        DiskState = apps.get_model("netbox_proxbox", "ProxboxVirtualDiskSyncState")
        disk_state = DiskState.objects.get(virtual_disk_id=ids["virtual_disk"])
        self.assertEqual(disk_state.proxbox_storage_id, {"id": ids["storage"]})
        self.assertEqual(disk_state.proxbox_storage_fk_id, ids["storage"])
        self.assertIsNone(disk_state.proxbox_storage_raw_id)
        self.assertEqual(disk_state.proxbox_storage_raw_value, "")

        VMInterfaceState = apps.get_model(
            "netbox_proxbox",
            "ProxboxVMInterfaceSyncState",
        )
        interface_state = VMInterfaceState.objects.get(
            vm_interface_id=ids["vm_interface"],
        )
        self.assertEqual(interface_state.proxbox_bridge, {"id": ids["bridge"]})
        self.assertEqual(interface_state.proxbox_bridge_fk_id, ids["bridge"])
        self.assertIsNone(interface_state.proxbox_bridge_raw_id)
        self.assertEqual(interface_state.proxbox_bridge_raw_value, "")

    def _assert_0069_relation_payloads(self, apps, ids: dict[str, int]) -> None:
        DiskState = apps.get_model("netbox_proxbox", "ProxboxVirtualDiskSyncState")
        disk_fields = {field.name: field for field in DiskState._meta.fields}
        self.assertNotIn("proxbox_storage_id", disk_fields)
        self.assertNotIn("proxbox_storage_fk", disk_fields)
        self.assertIn("proxbox_storage", disk_fields)
        disk_state = DiskState.objects.get(virtual_disk_id=ids["virtual_disk"])
        self.assertEqual(disk_state.proxbox_storage_id, ids["storage"])
        self.assertIsNone(disk_state.proxbox_storage_raw_id)
        self.assertEqual(disk_state.proxbox_storage_raw_value, "")

        VMInterfaceState = apps.get_model(
            "netbox_proxbox",
            "ProxboxVMInterfaceSyncState",
        )
        interface_fields = {
            field.name: field for field in VMInterfaceState._meta.fields
        }
        self.assertNotIn("proxbox_bridge_fk", interface_fields)
        self.assertIn("proxbox_bridge", interface_fields)
        interface_state = VMInterfaceState.objects.get(
            vm_interface_id=ids["vm_interface"],
        )
        self.assertEqual(interface_state.proxbox_bridge_id, ids["bridge"])
        self.assertIsNone(interface_state.proxbox_bridge_raw_id)
        self.assertEqual(interface_state.proxbox_bridge_raw_value, "")

    def _assert_0068_relation_edge_cases(self, apps, edge_ids: dict) -> None:
        DiskState = apps.get_model("netbox_proxbox", "ProxboxVirtualDiskSyncState")
        overflow_disk = DiskState.objects.get(
            virtual_disk_id=edge_ids["overflow_disk"],
        )
        self.assertIsNone(overflow_disk.proxbox_storage_fk_id)
        self.assertIsNone(overflow_disk.proxbox_storage_raw_id)
        self.assertEqual(
            json.loads(overflow_disk.proxbox_storage_raw_value),
            edge_ids["overflow_storage_raw"],
        )

        unresolved_disk = DiskState.objects.get(
            virtual_disk_id=edge_ids["unresolved_disk"],
        )
        self.assertIsNone(unresolved_disk.proxbox_storage_fk_id)
        self.assertEqual(
            unresolved_disk.proxbox_storage_raw_id,
            edge_ids["unresolved_storage_raw"]["id"],
        )
        self.assertEqual(unresolved_disk.proxbox_storage_raw_value, "")

        VMInterfaceState = apps.get_model(
            "netbox_proxbox",
            "ProxboxVMInterfaceSyncState",
        )
        named_bridge = VMInterfaceState.objects.get(
            vm_interface_id=edge_ids["named_bridge_interface"],
        )
        self.assertIsNone(named_bridge.proxbox_bridge_fk_id)
        self.assertIsNone(named_bridge.proxbox_bridge_raw_id)
        self.assertEqual(
            json.loads(named_bridge.proxbox_bridge_raw_value),
            edge_ids["named_bridge_raw"],
        )

    def _assert_0069_relation_edge_cases(self, apps, edge_ids: dict) -> None:
        DiskState = apps.get_model("netbox_proxbox", "ProxboxVirtualDiskSyncState")
        overflow_disk = DiskState.objects.get(
            virtual_disk_id=edge_ids["overflow_disk"],
        )
        self.assertIsNone(overflow_disk.proxbox_storage_id)
        self.assertIsNone(overflow_disk.proxbox_storage_raw_id)
        self.assertEqual(
            json.loads(overflow_disk.proxbox_storage_raw_value),
            edge_ids["overflow_storage_raw"],
        )

        unresolved_disk = DiskState.objects.get(
            virtual_disk_id=edge_ids["unresolved_disk"],
        )
        self.assertIsNone(unresolved_disk.proxbox_storage_id)
        self.assertEqual(
            unresolved_disk.proxbox_storage_raw_id,
            edge_ids["unresolved_storage_raw"]["id"],
        )
        self.assertEqual(unresolved_disk.proxbox_storage_raw_value, "")

        VMInterfaceState = apps.get_model(
            "netbox_proxbox",
            "ProxboxVMInterfaceSyncState",
        )
        named_bridge = VMInterfaceState.objects.get(
            vm_interface_id=edge_ids["named_bridge_interface"],
        )
        self.assertIsNone(named_bridge.proxbox_bridge_id)
        self.assertIsNone(named_bridge.proxbox_bridge_raw_id)
        self.assertEqual(
            json.loads(named_bridge.proxbox_bridge_raw_value),
            edge_ids["named_bridge_raw"],
        )

    def test_migration_executor_backfills_and_reapplies_historical_state(self) -> None:
        ids = self._seed_sync_state_sources()
        try:
            self._migrate_to(MIGRATION_0064)
            apps_0065 = self._migrate_to(MIGRATION_0065)
            self._assert_0066_relation_schema(apps_0065)

            apps_0066 = self._migrate_to(MIGRATION_0066)
            self._assert_all_sidecars_exist(apps_0066, ids)
            self._assert_0066_backfill_values(apps_0066, ids)
            self._assert_0066_relation_payloads(apps_0066, ids)
            counts_after_0066 = self._sidecar_counts(apps_0066)

            apps_0065_after_reverse = self._migrate_to(MIGRATION_0065)
            self.assertEqual(
                self._sidecar_counts(apps_0065_after_reverse),
                counts_after_0066,
            )

            apps_0066_after_reapply = self._migrate_to(MIGRATION_0066)
            self.assertEqual(
                self._sidecar_counts(apps_0066_after_reapply),
                counts_after_0066,
            )
            self._assert_0066_relation_payloads(apps_0066_after_reapply, ids)

            apps_0067 = self._migrate_to(MIGRATION_0067)
            self._assert_all_sidecars_exist(apps_0067, ids)
            self._assert_0067_relation_schema(apps_0067)
            self._assert_0066_relation_payloads(apps_0067, ids)

            apps_0068 = self._migrate_to(MIGRATION_0068)
            self._assert_all_sidecars_exist(apps_0068, ids)
            self._assert_0068_relation_payloads(apps_0068, ids)

            apps_0069 = self._migrate_to(MIGRATION_0069)
            self._assert_all_sidecars_exist(apps_0069, ids)
            self._assert_0069_relation_payloads(apps_0069, ids)

            apps_0066_after_reverse = self._migrate_to(MIGRATION_0066)
            self._assert_0066_relation_schema(apps_0066_after_reverse)

            apps_0069_after_reapply = self._migrate_to(MIGRATION_0069)
            self._assert_all_sidecars_exist(apps_0069_after_reapply, ids)
            self._assert_0069_relation_payloads(apps_0069_after_reapply, ids)
        finally:
            self._migrate_to(MIGRATION_0069)

    def test_relation_fk_reverse_preserves_api_written_values(self) -> None:
        ids = self._seed_sync_state_sources()
        try:
            self._migrate_to(MIGRATION_0064)
            apps_0069 = self._migrate_to(MIGRATION_0069)
            alternate_storage = ProxmoxStorage.objects.create(
                cluster=self.cluster,
                name="sync-state-api-patched-storage",
            )
            alternate_bridge = Interface.objects.create(
                device=self.device,
                name="migration-patched-bridge",
            )
            cleared_disk = VirtualDisk.objects.create(
                virtual_machine=self.vm,
                name="migration-cleared-scsi0",
                size=1024,
            )
            cleared_vm_interface = VMInterface.objects.create(
                virtual_machine=self.vm,
                name="migration-cleared-net0",
                enabled=True,
            )
            DiskState = apps_0069.get_model(
                "netbox_proxbox",
                "ProxboxVirtualDiskSyncState",
            )
            disk_state = DiskState.objects.get(virtual_disk_id=ids["virtual_disk"])
            disk_state.proxbox_storage_id = alternate_storage.pk
            disk_state.proxbox_storage_raw_id = 987654
            disk_state.save(update_fields=("proxbox_storage", "proxbox_storage_raw_id"))
            cleared_disk_state = DiskState.objects.create(
                virtual_disk_id=cleared_disk.pk,
                proxbox_storage_id=None,
                proxbox_storage_raw_id=ids["storage"],
            )

            VMInterfaceState = apps_0069.get_model(
                "netbox_proxbox",
                "ProxboxVMInterfaceSyncState",
            )
            interface_state = VMInterfaceState.objects.get(
                vm_interface_id=ids["vm_interface"],
            )
            interface_state.proxbox_bridge_id = alternate_bridge.pk
            interface_state.proxbox_bridge_raw_id = ids["bridge"]
            interface_state.save(
                update_fields=("proxbox_bridge", "proxbox_bridge_raw_id")
            )
            cleared_interface_state = VMInterfaceState.objects.create(
                vm_interface_id=cleared_vm_interface.pk,
                proxbox_bridge_id=None,
                proxbox_bridge_raw_id=ids["bridge"],
            )

            apps_0066 = self._migrate_to(MIGRATION_0066)
            DiskState0066 = apps_0066.get_model(
                "netbox_proxbox",
                "ProxboxVirtualDiskSyncState",
            )
            restored_disk = DiskState0066.objects.get(
                virtual_disk_id=ids["virtual_disk"],
            )
            self.assertEqual(restored_disk.proxbox_storage_id, alternate_storage.pk)
            restored_cleared_disk = DiskState0066.objects.get(
                virtual_disk_id=cleared_disk_state.virtual_disk_id,
            )
            self.assertIsNone(restored_cleared_disk.proxbox_storage_id)

            VMInterfaceState0066 = apps_0066.get_model(
                "netbox_proxbox",
                "ProxboxVMInterfaceSyncState",
            )
            restored_interface = VMInterfaceState0066.objects.get(
                vm_interface_id=ids["vm_interface"],
            )
            self.assertEqual(restored_interface.proxbox_bridge, alternate_bridge.pk)
            restored_cleared_interface = VMInterfaceState0066.objects.get(
                vm_interface_id=cleared_interface_state.vm_interface_id,
            )
            self.assertIsNone(restored_cleared_interface.proxbox_bridge)
        finally:
            self._migrate_to(MIGRATION_0069)

    def test_relation_fk_data_migration_can_rerun_after_mid_failure(self) -> None:
        ids = self._seed_sync_state_sources()
        try:
            self._migrate_to(MIGRATION_0064)
            self._migrate_to(MIGRATION_0067)
            migration_0068 = importlib.import_module(
                "netbox_proxbox.migrations.0068_sync_state_relation_fk_data"
            )
            original_save = migration_0068._save_relation_conversion
            call_count = 0

            def fail_after_first_save(obj, updates):
                nonlocal call_count
                call_count += 1
                original_save(obj, updates)
                if call_count == 1:
                    raise RuntimeError("forced mid-0068 failure")

            with patch.object(
                migration_0068,
                "_save_relation_conversion",
                side_effect=fail_after_first_save,
            ):
                with self.assertRaisesRegex(RuntimeError, "forced mid-0068 failure"):
                    self._migrate_to(MIGRATION_0068)

            apps_0068 = self._migrate_to(MIGRATION_0068)
            self._assert_0068_relation_payloads(apps_0068, ids)
            apps_0069 = self._migrate_to(MIGRATION_0069)
            self._assert_0069_relation_payloads(apps_0069, ids)
        finally:
            self._migrate_to(MIGRATION_0069)

    def test_relation_fk_data_migration_preserves_invalid_relation_payloads(
        self,
    ) -> None:
        ids = self._seed_sync_state_sources()
        edge_ids = self._seed_relation_edge_case_sources(ids)
        try:
            self._migrate_to(MIGRATION_0064)
            self._migrate_to(MIGRATION_0067)
            with self.assertLogs(
                "netbox_proxbox.migrations.0068_sync_state_relation_fk_data",
                level="WARNING",
            ) as captured:
                apps_0068 = self._migrate_to(MIGRATION_0068)
            self._assert_0068_relation_payloads(apps_0068, ids)
            self._assert_0068_relation_edge_cases(apps_0068, edge_ids)
            log_output = "\n".join(captured.output)
            self.assertIn("out-of-range", log_output)
            self.assertIn(str(edge_ids["overflow_disk"]), log_output)
            self.assertIn(edge_ids["overflow_storage_raw"]["id"], log_output)
            self.assertIn("non-integral", log_output)
            self.assertIn("vmbr0", log_output)

            apps_0069 = self._migrate_to(MIGRATION_0069)
            self._assert_0069_relation_payloads(apps_0069, ids)
            self._assert_0069_relation_edge_cases(apps_0069, edge_ids)

            apps_0066 = self._migrate_to(MIGRATION_0066)
            DiskState0066 = apps_0066.get_model(
                "netbox_proxbox",
                "ProxboxVirtualDiskSyncState",
            )
            restored_overflow = DiskState0066.objects.get(
                virtual_disk_id=edge_ids["overflow_disk"],
            )
            self.assertEqual(
                restored_overflow.proxbox_storage_id,
                edge_ids["overflow_storage_raw"],
            )
            restored_unresolved = DiskState0066.objects.get(
                virtual_disk_id=edge_ids["unresolved_disk"],
            )
            self.assertEqual(
                restored_unresolved.proxbox_storage_id,
                edge_ids["unresolved_storage_raw"]["id"],
            )

            VMInterfaceState0066 = apps_0066.get_model(
                "netbox_proxbox",
                "ProxboxVMInterfaceSyncState",
            )
            restored_bridge = VMInterfaceState0066.objects.get(
                vm_interface_id=edge_ids["named_bridge_interface"],
            )
            self.assertEqual(
                restored_bridge.proxbox_bridge, edge_ids["named_bridge_raw"]
            )

            apps_0069_reapply = self._migrate_to(MIGRATION_0069)
            self._assert_0069_relation_payloads(apps_0069_reapply, ids)
            self._assert_0069_relation_edge_cases(apps_0069_reapply, edge_ids)
        finally:
            self._migrate_to(MIGRATION_0069)

    def test_relation_fk_data_migration_uses_targeted_relation_lookups(self) -> None:
        ids = self._seed_sync_state_sources()
        cluster = Cluster.objects.get(pk=ids["cluster"])
        device = Device.objects.get(pk=ids["device"])
        for index in range(5):
            ProxmoxStorage.objects.create(
                cluster=cluster,
                name=f"migration-unreferenced-storage-{index}",
            )
            Interface.objects.create(
                device=device,
                name=f"migration-unreferenced-iface-{index}",
            )

        try:
            self._migrate_to(MIGRATION_0064)
            self._migrate_to(MIGRATION_0067)
            with CaptureQueriesContext(connection) as captured:
                apps_0068 = self._migrate_to(MIGRATION_0068)
            self._assert_0068_relation_payloads(apps_0068, ids)

            select_queries = [
                query["sql"]
                for query in captured.captured_queries
                if query["sql"].lstrip().upper().startswith("SELECT")
            ]
            storage_selects = [
                sql
                for sql in select_queries
                if "netbox_proxbox_proxmoxstorage" in sql.lower()
            ]
            interface_selects = [
                sql for sql in select_queries if "dcim_interface" in sql.lower()
            ]
            self.assertTrue(
                any(" IN " in sql.upper() for sql in storage_selects),
                "\n".join(storage_selects),
            )
            self.assertTrue(
                any(" IN " in sql.upper() for sql in interface_selects),
                "\n".join(interface_selects),
            )
            self.assertFalse(
                any(" WHERE " not in sql.upper() for sql in storage_selects),
                "\n".join(storage_selects),
            )
            self.assertFalse(
                any(" WHERE " not in sql.upper() for sql in interface_selects),
                "\n".join(interface_selects),
            )
        finally:
            self._migrate_to(MIGRATION_0069)
