"""Tests for test_api_netbox_integration."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

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

from ipam.models import IPAddress
from users.models import Token
from utilities.testing import (
    APIViewTestCases,
    create_test_user,
    create_test_virtualmachine,
)
from virtualization.models import Cluster, ClusterType

from netbox_proxbox.choices import (
    ProxmoxBackupFormatChoices,
    ProxmoxBackupSubtypeChoices,
    ProxmoxModeChoices,
    ProxmoxSnapshotStatusChoices,
    ProxmoxSnapshotSubtypeChoices,
)
from netbox_proxbox.models import (
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxmoxStorage,
    ProxmoxEndpoint,
    VMBackup,
    VMSnapshot,
    VMTaskHistory,
)


class ProxmoxEndpointAPITest(APIViewTestCases.APIViewTestCase):
    model = ProxmoxEndpoint
    brief_fields = ["display", "domain", "id", "name", "port", "url"]
    bulk_update_data = {"verify_ssl": True}
    validation_excluded_fields = ["ip_address"]

    @classmethod
    def setUpTestData(cls):
        cls.ip_addresses = [
            IPAddress.objects.create(address="192.0.2.1/24"),
            IPAddress.objects.create(address="192.0.2.2/24"),
            IPAddress.objects.create(address="192.0.2.3/24"),
            IPAddress.objects.create(address="192.0.2.4/24"),
            IPAddress.objects.create(address="192.0.2.5/24"),
            IPAddress.objects.create(address="192.0.2.6/24"),
        ]

        for idx in range(3):
            ProxmoxEndpoint.objects.create(
                name=f"pve-{idx}",
                ip_address=cls.ip_addresses[idx],
                domain=f"pve-{idx}.example.test",
                port=8006 + idx,
                mode=ProxmoxModeChoices.PROXMOX_MODE_CLUSTER,
                username="root@pam",
                password="secret",
                token_name=f"token-{idx}",
                token_value=f"value-{idx}",
                verify_ssl=False,
            )

        cls.create_data = [
            {
                "name": "pve-3",
                "ip_address": {"id": cls.ip_addresses[3].pk},
                "domain": "pve-3.example.test",
                "port": 8100,
                "mode": ProxmoxModeChoices.PROXMOX_MODE_STANDALONE,
                "username": "root@pam",
                "password": "secret",
                "token_name": "token-3",
                "token_value": "value-3",
                "verify_ssl": True,
            },
            {
                "name": "pve-4",
                "ip_address": {"id": cls.ip_addresses[4].pk},
                "domain": "pve-4.example.test",
                "port": 8101,
                "mode": ProxmoxModeChoices.PROXMOX_MODE_CLUSTER,
                "username": "root@pam",
                "password": "secret",
                "token_name": "token-4",
                "token_value": "value-4",
                "verify_ssl": False,
            },
            {
                "name": "pve-5",
                "ip_address": {"id": cls.ip_addresses[5].pk},
                "domain": "pve-5.example.test",
                "port": 8102,
                "mode": ProxmoxModeChoices.PROXMOX_MODE_CLUSTER,
                "username": "root@pam",
                "password": "secret",
                "token_name": "token-5",
                "token_value": "value-5",
                "verify_ssl": True,
            },
        ]

    def test_secrets_are_write_only_on_read(self):
        self.add_permissions("netbox_proxbox.view_proxmoxendpoint")
        response = self.client.get(
            self._get_detail_url(self._get_queryset().first()), **self.header
        )
        self.assertHttpStatus(response, 200)
        assert "password" not in response.data
        assert "token_value" not in response.data

    def test_create_requires_domain_or_ip_address(self):
        self.add_permissions("netbox_proxbox.add_proxmoxendpoint")
        payload = {
            "name": "pve-no-host",
            "domain": "",
            "port": 8006,
            "mode": ProxmoxModeChoices.PROXMOX_MODE_CLUSTER,
            "username": "root@pam",
            "verify_ssl": False,
        }

        response = self.client.post(
            self._get_list_url(), payload, format="json", **self.header
        )
        self.assertHttpStatus(response, 400)
        assert "domain" in response.data
        assert "ip_address" in response.data


class NetBoxEndpointAPITest(APIViewTestCases.APIViewTestCase):
    model = NetBoxEndpoint
    brief_fields = ["display", "domain", "id", "name", "port", "url"]
    bulk_update_data = {"verify_ssl": False}
    validation_excluded_fields = ["ip_address", "token"]

    @classmethod
    def setUpTestData(cls):
        cls.ip_addresses = [
            IPAddress.objects.create(address="198.51.100.1/24"),
            IPAddress.objects.create(address="198.51.100.2/24"),
            IPAddress.objects.create(address="198.51.100.3/24"),
            IPAddress.objects.create(address="198.51.100.4/24"),
            IPAddress.objects.create(address="198.51.100.5/24"),
            IPAddress.objects.create(address="198.51.100.6/24"),
        ]
        cls.users = [create_test_user(f"token-user-{idx}") for idx in range(6)]
        cls.tokens = [
            Token.objects.create(user=user, version=1, token=("a" * 32) + f"{idx:08d}")
            for idx, user in enumerate(cls.users)
        ]

        for idx in range(3):
            NetBoxEndpoint.objects.create(
                name=f"netbox-{idx}",
                ip_address=cls.ip_addresses[idx],
                domain=f"netbox-{idx}.example.test",
                port=443,
                token=cls.tokens[idx],
                verify_ssl=True,
            )

        cls.create_data = [
            {
                "name": "netbox-3",
                "ip_address": {"id": cls.ip_addresses[3].pk},
                "domain": "netbox-3.example.test",
                "port": 8443,
                "token": {"id": cls.tokens[3].pk},
                "verify_ssl": True,
            },
            {
                "name": "netbox-4",
                "ip_address": {"id": cls.ip_addresses[4].pk},
                "domain": "netbox-4.example.test",
                "port": 9443,
                "token": {"id": cls.tokens[4].pk},
                "verify_ssl": False,
            },
            {
                "name": "netbox-5",
                "ip_address": {"id": cls.ip_addresses[5].pk},
                "domain": "netbox-5.example.test",
                "port": 10443,
                "token": {"id": cls.tokens[5].pk},
                "verify_ssl": True,
            },
        ]

    def test_create_requires_domain_or_ip_address(self):
        self.add_permissions("netbox_proxbox.add_netboxendpoint")
        payload = {
            "name": "netbox-no-host",
            "domain": "",
            "port": 443,
            "token_version": "v2",
            "token_key": "ABCDEF123456",
            "token_secret": "0123456789abcdef0123456789abcdef",
            "verify_ssl": False,
        }

        response = self.client.post(
            self._get_list_url(), payload, format="json", **self.header
        )
        self.assertHttpStatus(response, 400)
        assert "domain" in response.data
        assert "ip_address" in response.data


class FastAPIEndpointAPITest(APIViewTestCases.APIViewTestCase):
    model = FastAPIEndpoint
    brief_fields = ["display", "domain", "id", "name", "port", "url"]
    bulk_update_data = {"use_websocket": True}
    validation_excluded_fields = ["ip_address"]

    @classmethod
    def setUpTestData(cls):
        cls.ip_addresses = [
            IPAddress.objects.create(address="203.0.113.1/24"),
            IPAddress.objects.create(address="203.0.113.2/24"),
            IPAddress.objects.create(address="203.0.113.3/24"),
            IPAddress.objects.create(address="203.0.113.4/24"),
            IPAddress.objects.create(address="203.0.113.5/24"),
            IPAddress.objects.create(address="203.0.113.6/24"),
        ]

        for idx in range(3):
            FastAPIEndpoint.objects.create(
                name=f"proxbox-{idx}",
                ip_address=cls.ip_addresses[idx],
                domain=f"proxbox-{idx}.example.test",
                port=8800 + idx,
                verify_ssl=True,
                token=f"token-{idx}",
                use_websocket=False,
                websocket_domain=f"ws-{idx}.example.test",
                websocket_port=9800 + idx,
                server_side_websocket=False,
            )

        cls.create_data = [
            {
                "name": "proxbox-3",
                "ip_address": {"id": cls.ip_addresses[3].pk},
                "domain": "proxbox-3.example.test",
                "port": 8810,
                "verify_ssl": True,
                "token": "token-3",
                "use_websocket": True,
                "websocket_domain": "ws-3.example.test",
                "websocket_port": 9810,
                "server_side_websocket": False,
            },
            {
                "name": "proxbox-4",
                "ip_address": {"id": cls.ip_addresses[4].pk},
                "domain": "proxbox-4.example.test",
                "port": 8811,
                "verify_ssl": False,
                "token": "token-4",
                "use_websocket": True,
                "websocket_domain": "ws-4.example.test",
                "websocket_port": 9811,
                "server_side_websocket": True,
            },
            {
                "name": "proxbox-5",
                "ip_address": {"id": cls.ip_addresses[5].pk},
                "domain": "proxbox-5.example.test",
                "port": 8812,
                "verify_ssl": True,
                "token": "token-5",
                "use_websocket": False,
                "websocket_domain": "ws-5.example.test",
                "websocket_port": 9812,
                "server_side_websocket": False,
            },
        ]

    def test_create_requires_domain_or_ip_address(self):
        self.add_permissions("netbox_proxbox.add_fastapiendpoint")
        payload = {
            "name": "backend-no-host",
            "domain": "",
            "port": 8800,
            "verify_ssl": False,
            "token": "backend-token",
            "use_websocket": False,
            "websocket_domain": "",
            "websocket_port": 8800,
            "server_side_websocket": False,
        }

        response = self.client.post(
            self._get_list_url(), payload, format="json", **self.header
        )
        self.assertHttpStatus(response, 400)
        assert "domain" in response.data
        assert "ip_address" in response.data


class VMBackupAPITest(APIViewTestCases.APIViewTestCase):
    model = VMBackup
    brief_fields = [
        "creation_time",
        "display",
        "id",
        "proxmox_storage",
        "storage",
        "url",
    ]
    bulk_update_data = {"encrypted": True}
    validation_excluded_fields = ["virtual_machine"]

    @classmethod
    def setUpTestData(cls):
        # Create cluster type and clusters for storage FK
        cluster_type, _ = ClusterType.objects.get_or_create(
            name="Proxmox", defaults={"slug": "proxmox"}
        )
        cls.clusters = [
            Cluster.objects.create(
                name=f"cluster-{idx}",
                type=cluster_type,
            )
            for idx in range(6)
        ]
        cls.virtual_machines = [
            create_test_virtualmachine(f"vm-{idx}") for idx in range(6)
        ]
        cls.storages = [
            ProxmoxStorage.objects.create(
                cluster=cls.clusters[idx], name=f"storage-{idx}"
            )
            for idx in range(6)
        ]
        cls.storages = [
            ProxmoxStorage.objects.create(
                cluster=f"cluster-{idx}", name=f"storage-{idx}"
            )
            for idx in range(6)
        ]

        for idx in range(3):
            VMBackup.objects.create(
                storage=cls.storages[idx],
                virtual_machine=cls.virtual_machines[idx],
                subtype=ProxmoxBackupSubtypeChoices.BACKUP_SUBTYPE_QEMU,
                format=ProxmoxBackupFormatChoices.BACKUP_FORMAT_TZST,
                vmid=100 + idx,
                encrypted=False,
            )

        cls.create_data = [
            {
                "storage": cls.storages[3].pk,
                "virtual_machine": {"id": cls.virtual_machines[3].pk},
                "subtype": ProxmoxBackupSubtypeChoices.BACKUP_SUBTYPE_QEMU,
                "format": ProxmoxBackupFormatChoices.BACKUP_FORMAT_TZST,
                "vmid": 103,
                "encrypted": False,
            },
            {
                "storage": cls.storages[4].pk,
                "virtual_machine": {"id": cls.virtual_machines[4].pk},
                "subtype": ProxmoxBackupSubtypeChoices.BACKUP_SUBTYPE_LXC,
                "format": ProxmoxBackupFormatChoices.BACKUP_FORMAT_TGZ,
                "vmid": 104,
                "encrypted": True,
            },
            {
                "storage": cls.storages[5].pk,
                "virtual_machine": {"id": cls.virtual_machines[5].pk},
                "subtype": ProxmoxBackupSubtypeChoices.BACKUP_SUBTYPE_QEMU,
                "format": ProxmoxBackupFormatChoices.BACKUP_FORMAT_RAW,
                "vmid": 105,
                "encrypted": False,
            },
        ]


class VMSnapshotAPITest(APIViewTestCases.APIViewTestCase):
    model = VMSnapshot
    brief_fields = ["display", "id", "name", "storage", "url"]
    validation_excluded_fields = ["virtual_machine"]

    @classmethod
    def setUpTestData(cls):
        # Create cluster type and clusters for storage FK
        cluster_type, _ = ClusterType.objects.get_or_create(
            name="Proxmox", defaults={"slug": "proxmox"}
        )
        cls.clusters = [
            Cluster.objects.create(
                name=f"snapshot-cluster-{idx}",
                type=cluster_type,
            )
            for idx in range(6)
        ]
        cls.virtual_machines = [
            create_test_virtualmachine(f"snapshot-vm-{idx}") for idx in range(6)
        ]
        cls.storages = [
            ProxmoxStorage.objects.create(
                cluster=cls.clusters[idx], name=f"storage-{idx}"
            )
            for idx in range(6)
        ]
        cls.storages = [
            ProxmoxStorage.objects.create(
                cluster=f"cluster-{idx}", name=f"storage-{idx}"
            )
            for idx in range(6)
        ]

        for idx in range(3):
            VMSnapshot.objects.create(
                storage=cls.storages[idx],
                virtual_machine=cls.virtual_machines[idx],
                name=f"snapshot-{idx}",
                description="Snapshot description",
                vmid=200 + idx,
                node=f"pve0{idx}",
                subtype=ProxmoxSnapshotSubtypeChoices.SNAPSHOT_SUBTYPE_QEMU,
                status=ProxmoxSnapshotStatusChoices.SNAPSHOT_STATUS_ACTIVE,
            )

        cls.create_data = [
            {
                "storage": cls.storages[3].pk,
                "virtual_machine": {"id": cls.virtual_machines[3].pk},
                "name": "snapshot-3",
                "description": "Snapshot description",
                "vmid": 203,
                "node": "pve03",
                "subtype": ProxmoxSnapshotSubtypeChoices.SNAPSHOT_SUBTYPE_QEMU,
                "status": ProxmoxSnapshotStatusChoices.SNAPSHOT_STATUS_ACTIVE,
            },
            {
                "storage": cls.storages[4].pk,
                "virtual_machine": {"id": cls.virtual_machines[4].pk},
                "name": "snapshot-4",
                "description": "Snapshot description",
                "vmid": 204,
                "node": "pve04",
                "subtype": ProxmoxSnapshotSubtypeChoices.SNAPSHOT_SUBTYPE_QEMU,
                "status": ProxmoxSnapshotStatusChoices.SNAPSHOT_STATUS_ACTIVE,
            },
            {
                "storage": cls.storages[5].pk,
                "virtual_machine": {"id": cls.virtual_machines[5].pk},
                "name": "snapshot-5",
                "description": "Snapshot description",
                "vmid": 205,
                "node": "pve05",
                "subtype": ProxmoxSnapshotSubtypeChoices.SNAPSHOT_SUBTYPE_QEMU,
                "status": ProxmoxSnapshotStatusChoices.SNAPSHOT_STATUS_ACTIVE,
            },
        ]


class VMTaskHistoryAPITest(APIViewTestCases.APIViewTestCase):
    model = VMTaskHistory
    brief_fields = ["display", "id", "start_time", "status", "url", "username"]
    validation_excluded_fields = ["virtual_machine"]

    @classmethod
    def setUpTestData(cls):
        cls.virtual_machines = [
            create_test_virtualmachine(f"task-vm-{idx}") for idx in range(6)
        ]

        for idx in range(3):
            VMTaskHistory.objects.create(
                virtual_machine=cls.virtual_machines[idx],
                vm_type="qemu" if idx % 2 == 0 else "lxc",
                upid=f"UPID:pve0{idx}:{idx}",
                node=f"pve0{idx}",
                pid=2000 + idx,
                pstart=datetime(2024, 3, 9, 17, 0, idx, tzinfo=timezone.utc),
                task_id=str(100 + idx),
                task_type="qmstart" if idx % 2 == 0 else "vzstart",
                username="root@pam",
                start_time=datetime(2024, 3, 9, 17, 16, 10 + idx, tzinfo=timezone.utc),
                end_time=datetime(2024, 3, 9, 17, 16, 20 + idx, tzinfo=timezone.utc),
                description=f"VM {100 + idx} - Start",
                status="OK",
                task_state="stopped",
                exitstatus="OK",
            )

        cls.create_data = [
            {
                "virtual_machine": {"id": cls.virtual_machines[3].pk},
                "vm_type": "qemu",
                "upid": "UPID:pve03:3",
                "node": "pve03",
                "pid": 2003,
                "pstart": datetime(2024, 3, 9, 17, 0, 3, tzinfo=timezone.utc),
                "task_id": "103",
                "task_type": "qmstart",
                "username": "root@pam",
                "start_time": datetime(2024, 3, 9, 17, 16, 13, tzinfo=timezone.utc),
                "end_time": datetime(2024, 3, 9, 17, 16, 23, tzinfo=timezone.utc),
                "description": "VM 103 - Start",
                "status": "OK",
                "task_state": "stopped",
                "exitstatus": "OK",
            },
            {
                "virtual_machine": {"id": cls.virtual_machines[4].pk},
                "vm_type": "lxc",
                "upid": "UPID:pve04:4",
                "node": "pve04",
                "pid": 2004,
                "pstart": datetime(2024, 3, 9, 17, 0, 4, tzinfo=timezone.utc),
                "task_id": "104",
                "task_type": "vzcreate",
                "username": "root@pam",
                "start_time": datetime(2024, 3, 9, 17, 16, 14, tzinfo=timezone.utc),
                "end_time": datetime(2024, 3, 9, 17, 16, 24, tzinfo=timezone.utc),
                "description": "CT 104 - Create",
                "status": "OK",
                "task_state": "stopped",
                "exitstatus": "OK",
            },
            {
                "virtual_machine": {"id": cls.virtual_machines[5].pk},
                "vm_type": "qemu",
                "upid": "UPID:pve05:5",
                "node": "pve05",
                "pid": 2005,
                "pstart": datetime(2024, 3, 9, 17, 0, 5, tzinfo=timezone.utc),
                "task_id": "105",
                "task_type": "qmsnapshot",
                "username": "root@pam",
                "start_time": datetime(2024, 3, 9, 17, 16, 15, tzinfo=timezone.utc),
                "end_time": datetime(2024, 3, 9, 17, 16, 25, tzinfo=timezone.utc),
                "description": "VM 105 - Snapshot",
                "status": "OK",
                "task_state": "stopped",
                "exitstatus": "OK",
            },
        ]
