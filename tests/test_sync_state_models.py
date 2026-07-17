"""Behavior tests for typed Proxbox sync-state sidecar models."""

from __future__ import annotations

import importlib
import json
import os
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

try:
    import django
except ModuleNotFoundError:
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - depends on external test services
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from django.apps import apps as django_apps  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.db import IntegrityError, transaction  # noqa: E402
from django.test import TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from dcim.models import Interface, Manufacturer, DeviceType, DeviceRole, Site  # noqa: E402
from ipam.models import IPAddress, VLAN  # noqa: E402
from users.models import ObjectPermission, Token  # noqa: E402
from utilities.testing import create_test_device, create_test_virtualmachine  # noqa: E402
from virtualization.models import (  # noqa: E402
    Cluster,
    ClusterGroup,
    ClusterType,
    VirtualDisk,
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


def _slug(prefix: str, value: int) -> str:
    return f"{prefix}-{value}"


def _model_route(model) -> str:
    return model._meta.model_name


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
                {"proxbox_storage_id": {"storage": "local-lvm"}},
            ),
            (
                ProxboxVMInterfaceSyncState,
                "vm_interface",
                cls.vm_interface,
                {"proxbox_bridge": {"bridge": "vmbr0"}},
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
        parent_models.update({ProxmoxEndpoint, ProxmoxNode, ProxmoxCluster})
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
