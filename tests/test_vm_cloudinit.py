"""Cover the read-side cloud-init reflection model (issue #363)."""

from __future__ import annotations

import json
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

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.db import IntegrityError  # noqa: E402
from django.test import Client, TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from users.models import ObjectPermission, Token  # noqa: E402
from utilities.testing import create_test_virtualmachine  # noqa: E402

from netbox_proxbox.models import ProxmoxVMCloudInit  # noqa: E402


class ProxmoxVMCloudInitModelTest(TestCase):
    """Validate the model surface — uniqueness, defaults, string forms."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.vm = create_test_virtualmachine("cloudinit-vm-1")
        cls.other_vm = create_test_virtualmachine("cloudinit-vm-2")

    def test_creates_with_minimal_payload(self) -> None:
        row = ProxmoxVMCloudInit.objects.create(virtual_machine=self.vm)
        self.assertEqual(row.virtual_machine, self.vm)
        self.assertEqual(row.ciuser, "")
        self.assertEqual(row.sshkeys, "")
        self.assertEqual(row.ipconfig0, "")
        self.assertFalse(row.sshkeys_truncated)
        self.assertIsNotNone(row.last_synced)

    def test_string_repr_uses_parent_vm(self) -> None:
        row = ProxmoxVMCloudInit.objects.create(
            virtual_machine=self.vm, ciuser="ubuntu"
        )
        self.assertIn(str(self.vm), str(row))
        self.assertIn("cloud-init", str(row))

    def test_one_to_one_enforced(self) -> None:
        ProxmoxVMCloudInit.objects.create(virtual_machine=self.vm)
        with self.assertRaises(IntegrityError):
            ProxmoxVMCloudInit.objects.create(virtual_machine=self.vm)

    def test_reverse_relation_on_vm(self) -> None:
        row = ProxmoxVMCloudInit.objects.create(
            virtual_machine=self.vm,
            ciuser="ubuntu",
            ipconfig0="ip=dhcp",
        )
        self.vm.refresh_from_db()
        self.assertEqual(self.vm.proxmox_cloudinit, row)

    def test_cascade_delete_with_vm(self) -> None:
        ProxmoxVMCloudInit.objects.create(virtual_machine=self.other_vm)
        self.assertTrue(
            ProxmoxVMCloudInit.objects.filter(virtual_machine=self.other_vm).exists()
        )
        self.other_vm.delete()
        self.assertFalse(
            ProxmoxVMCloudInit.objects.filter(pk__isnull=False)
            .filter(virtual_machine_id=self.other_vm.pk)
            .exists()
        )

    def test_get_absolute_url(self) -> None:
        row = ProxmoxVMCloudInit.objects.create(virtual_machine=self.vm)
        url = row.get_absolute_url()
        self.assertIn(str(row.pk), url)
        self.assertIn("vm-cloudinit", url)


class ProxmoxVMCloudInitAPITest(TestCase):
    """proxbox-api must be able to POST / PATCH this endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.vm = create_test_virtualmachine("cloudinit-api-vm")
        cls.user = get_user_model().objects.create_user(
            username="proxbox-api", is_staff=True
        )
        cls.token = Token.objects.create(user=cls.user)
        content_type = ContentType.objects.get_for_model(ProxmoxVMCloudInit)
        permission = ObjectPermission.objects.create(
            name="cloudinit-rw",
            actions=["view", "add", "change", "delete"],
        )
        permission.object_types.add(content_type)
        permission.users.add(cls.user)

    def _auth_headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_post_creates_row(self) -> None:
        url = reverse("plugins-api:netbox_proxbox-api:proxmoxvmcloudinit-list")
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "virtual_machine": self.vm.pk,
                    "ciuser": "ubuntu",
                    "sshkeys": "ssh-rsa AAAA test@host\n",
                    "ipconfig0": "ip=dhcp",
                    "sshkeys_truncated": False,
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        row = ProxmoxVMCloudInit.objects.get(virtual_machine=self.vm)
        self.assertEqual(row.ciuser, "ubuntu")
        self.assertEqual(row.ipconfig0, "ip=dhcp")
        self.assertIn("ssh-rsa", row.sshkeys)

    def test_post_intent_encrypts_sshkeys_and_hides_ciphertext(self) -> None:
        """Create-time intent: sshkeys_intent encrypts to sshkeys_enc, never leaks."""
        url = reverse("plugins-api:netbox_proxbox-api:proxmoxvmcloudinit-list")
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "virtual_machine": self.vm.pk,
                    "ciuser": "ubuntu",
                    "is_intent": True,
                    "hostname": "tenant-vm",
                    "search_domain": "tenant.example",
                    "dns_servers": "168.0.96.26,168.0.96.27",
                    "bridge": "vmbr1",
                    "vlan_tag": 111,
                    "gateway": "168.0.98.1",
                    "ip_cidr": "168.0.98.10/25",
                    "ssh_pwauth": True,
                    "enable_agent": True,
                    "nms_credential_id": 901,
                    "sshkeys_intent": "ssh-ed25519 AAAAC3Intent user@host\n",
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        # Ciphertext + the write-only key material must never be serialized out.
        self.assertNotIn("sshkeys_enc", body)
        self.assertNotIn("sshkeys_intent", body)
        self.assertTrue(body["has_sshkeys"])
        self.assertTrue(body["is_intent"])
        self.assertEqual(body["nms_credential_id"], 901)

        row = ProxmoxVMCloudInit.objects.get(virtual_machine=self.vm)
        # Encrypted at rest and decryptable back to the original bundle.
        self.assertTrue(row.sshkeys_enc)
        self.assertNotIn("ssh-ed25519", row.sshkeys_enc)  # stored as ciphertext
        self.assertIn("ssh-ed25519 AAAAC3Intent", row.get_sshkeys())
        self.assertTrue(row.has_sshkeys)
        self.assertEqual(row.hostname, "tenant-vm")
        self.assertEqual(row.vlan_tag, 111)
        self.assertEqual(row.nms_credential_id, 901)
        # The plaintext reflection column stays owned by proxbox-api sync.
        self.assertEqual(row.sshkeys, "")

    def test_list_returns_brief_fields(self) -> None:
        ProxmoxVMCloudInit.objects.create(
            virtual_machine=self.vm, ciuser="root", ipconfig0="ip=dhcp"
        )
        url = reverse("plugins-api:netbox_proxbox-api:proxmoxvmcloudinit-list")
        response = self.client.get(url + "?brief=1", **self._auth_headers())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["count"], 1)
        sample = payload["results"][0]
        for key in ("id", "url", "display", "virtual_machine", "ciuser"):
            self.assertIn(key, sample)


class ProxmoxVMCloudInitTabTest(TestCase):
    """The VM detail tab must hide when there is no cloud-init row."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.vm_with = create_test_virtualmachine("cloudinit-tab-on")
        cls.vm_without = create_test_virtualmachine("cloudinit-tab-off")
        cls.user = get_user_model().objects.create_user(
            username="viewer", is_staff=True, is_superuser=True
        )
        ProxmoxVMCloudInit.objects.create(
            virtual_machine=cls.vm_with,
            ciuser="ubuntu",
            ipconfig0="ip=dhcp",
            sshkeys="ssh-rsa AAAA test@host\n",
        )

    def test_tab_renders_for_vm_with_row(self) -> None:
        client = Client()
        client.force_login(self.user)
        url = reverse(
            "virtualization:virtualmachine_proxmox_cloudinit", args=[self.vm_with.pk]
        )
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ubuntu")
        self.assertContains(response, "ip=dhcp")

    def test_tab_renders_empty_state_when_no_row(self) -> None:
        client = Client()
        client.force_login(self.user)
        url = reverse(
            "virtualization:virtualmachine_proxmox_cloudinit", args=[self.vm_without.pk]
        )
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Proxmox cloud-init record")
