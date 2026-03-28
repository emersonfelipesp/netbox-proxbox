from __future__ import annotations

import os
import sys
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

from netbox_proxbox.choices import (
    ProxmoxBackupFormatChoices,
    ProxmoxBackupSubtypeChoices,
    ProxmoxModeChoices,
    SyncStatusChoices,
    SyncTypeChoices,
)
from netbox_proxbox.models import (
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxmoxEndpoint,
    SyncProcess,
    VMBackup,
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


class SyncProcessAPITest(APIViewTestCases.APIViewTestCase):
    model = SyncProcess
    brief_fields = ["display", "id", "name", "status", "url"]
    bulk_update_data = {"status": SyncStatusChoices.COMPLETED}

    @classmethod
    def setUpTestData(cls):
        for idx in range(3):
            SyncProcess.objects.create(
                name=f"sync-{idx}",
                sync_type=SyncTypeChoices.ALL,
                status=SyncStatusChoices.NOT_STARTED,
            )

        cls.create_data = [
            {
                "name": "sync-3",
                "sync_type": SyncTypeChoices.VIRTUAL_MACHINES,
                "status": SyncStatusChoices.NOT_STARTED,
            },
            {
                "name": "sync-4",
                "sync_type": SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS,
                "status": SyncStatusChoices.SYNCING,
            },
            {
                "name": "sync-5",
                "sync_type": SyncTypeChoices.DEVICES,
                "status": SyncStatusChoices.FAILED,
            },
        ]


class VMBackupAPITest(APIViewTestCases.APIViewTestCase):
    model = VMBackup
    brief_fields = ["creation_time", "display", "id", "storage", "url"]
    bulk_update_data = {"encrypted": True}
    validation_excluded_fields = ["virtual_machine"]

    @classmethod
    def setUpTestData(cls):
        cls.virtual_machines = [
            create_test_virtualmachine(f"vm-{idx}") for idx in range(6)
        ]

        for idx in range(3):
            VMBackup.objects.create(
                storage=f"storage-{idx}",
                virtual_machine=cls.virtual_machines[idx],
                subtype=ProxmoxBackupSubtypeChoices.BACKUP_SUBTYPE_QEMU,
                format=ProxmoxBackupFormatChoices.BACKUP_FORMAT_TZST,
                vmid=100 + idx,
                encrypted=False,
            )

        cls.create_data = [
            {
                "storage": "storage-3",
                "virtual_machine": {"id": cls.virtual_machines[3].pk},
                "subtype": ProxmoxBackupSubtypeChoices.BACKUP_SUBTYPE_QEMU,
                "format": ProxmoxBackupFormatChoices.BACKUP_FORMAT_TZST,
                "vmid": 103,
                "encrypted": False,
            },
            {
                "storage": "storage-4",
                "virtual_machine": {"id": cls.virtual_machines[4].pk},
                "subtype": ProxmoxBackupSubtypeChoices.BACKUP_SUBTYPE_LXC,
                "format": ProxmoxBackupFormatChoices.BACKUP_FORMAT_TGZ,
                "vmid": 104,
                "encrypted": True,
            },
            {
                "storage": "storage-5",
                "virtual_machine": {"id": cls.virtual_machines[5].pk},
                "subtype": ProxmoxBackupSubtypeChoices.BACKUP_SUBTYPE_QEMU,
                "format": ProxmoxBackupFormatChoices.BACKUP_FORMAT_RAW,
                "vmid": 105,
                "encrypted": False,
            },
        ]
