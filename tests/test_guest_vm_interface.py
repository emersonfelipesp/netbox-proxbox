"""Cover guest OS VM interface models and API endpoints."""

from __future__ import annotations

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

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.db import IntegrityError, transaction  # noqa: E402
from django.db.models.query import QuerySet  # noqa: E402
from django.db.models import ProtectedError  # noqa: E402
from django.test import TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from dcim.models import Interface  # noqa: E402
from ipam.models import IPAddress  # noqa: E402
from users.models import ObjectPermission, Token  # noqa: E402
from utilities.testing import (  # noqa: E402
    create_test_device,
    create_test_virtualmachine,
)
from virtualization.models import VMInterface  # noqa: E402

from netbox_proxbox.api.serializers.settings import (  # noqa: E402
    ProxboxPluginSettingsSerializer,
)
from netbox_proxbox.forms.settings import ProxboxPluginSettingsForm  # noqa: E402
from netbox_proxbox.models import (  # noqa: E402
    GuestVMInterface,
    GuestVMInterfaceAddress,
    ProxboxPluginSettings,
)


class GuestVMInterfaceModelTest(TestCase):
    """Validate creation, uniqueness, and IP protect behavior."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.vm = create_test_virtualmachine("guest-if-vm-1")
        cls.core_interface = VMInterface.objects.create(
            virtual_machine=cls.vm,
            name="net0",
            enabled=True,
        )
        cls.ip_address = IPAddress.objects.create(address="192.0.2.50/24")

    def test_creates_guest_interface_with_core_link(self) -> None:
        guest = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            vm_interface=self.core_interface,
            name="ens18",
            mac_address="52:54:00:aa:bb:cc",
            mtu=1500,
        )

        self.assertEqual(str(guest), "ens18")
        self.assertEqual(guest.virtual_machine, self.vm)
        self.assertEqual(guest.vm_interface, self.core_interface)
        self.assertTrue(guest.enabled)
        self.assertIn(str(guest.pk), guest.get_absolute_url())
        self.assertEqual(self.vm.proxbox_guest_interfaces.get(), guest)
        # One-to-one reverse accessor: the core VMInterface maps to exactly one
        # GuestVMInterface.
        self.assertEqual(self.core_interface.guest_interface, guest)

    def test_agent_only_interface_can_omit_core_vm_interface(self) -> None:
        guest = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            name="br0",
        )

        self.assertIsNone(guest.vm_interface)

    def test_core_vm_interface_is_one_to_one(self) -> None:
        GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            vm_interface=self.core_interface,
            name="ens18",
        )
        # A second guest interface cannot claim the same core VMInterface.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GuestVMInterface.objects.create(
                    virtual_machine=self.vm,
                    vm_interface=self.core_interface,
                    name="ens18-dup",
                )

    def test_deleting_core_interface_preserves_guest_interface(self) -> None:
        guest = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            vm_interface=self.core_interface,
            name="ens18",
        )
        self.core_interface.delete()
        guest.refresh_from_db()
        # SET_NULL: the guest OS inventory row survives core-interface churn.
        self.assertIsNone(guest.vm_interface)
        self.assertEqual(guest.virtual_machine, self.vm)

    def test_address_link_rejects_foreign_vm_ip(self) -> None:
        other_vm = create_test_virtualmachine("guest-if-vm-2")
        other_interface = VMInterface.objects.create(
            virtual_machine=other_vm,
            name="net0",
            enabled=True,
        )
        foreign_ip = IPAddress.objects.create(
            address="203.0.113.9/24",
            assigned_object=other_interface,
        )
        guest = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            vm_interface=self.core_interface,
            name="ens18",
        )
        link = GuestVMInterfaceAddress(guest_interface=guest, ip_address=foreign_ip)
        # The IP is assigned to another VM's interface, so the link must not
        # validate (prevents cross-VM PROTECT lock-in and mislinked inventory).
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_address_link_accepts_mapped_interface_ip(self) -> None:
        mapped_ip = IPAddress.objects.create(
            address="192.0.2.77/24",
            assigned_object=self.core_interface,
        )
        guest = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            vm_interface=self.core_interface,
            name="ens18",
        )
        link = GuestVMInterfaceAddress(guest_interface=guest, ip_address=mapped_ip)
        # Same object assigned to the mapped core interface — valid.
        link.full_clean()
        link.save()
        self.assertEqual(link.ip_address, mapped_ip)

    def test_address_link_rejects_non_vminterface_ip(self) -> None:
        device = create_test_device("guest-if-dev-1")
        dcim_interface = Interface.objects.create(device=device, name="eth0")
        dcim_ip = IPAddress.objects.create(
            address="192.0.2.90/24",
            assigned_object=dcim_interface,
        )
        guest = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            vm_interface=self.core_interface,
            name="ens18",
        )
        link = GuestVMInterfaceAddress(guest_interface=guest, ip_address=dcim_ip)
        # An IP owned by a dcim.Interface must not be linkable (and PROTECT-locked).
        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_guest_interface_rejects_foreign_vm_core_interface(self) -> None:
        other_vm = create_test_virtualmachine("guest-if-vm-3")
        other_interface = VMInterface.objects.create(
            virtual_machine=other_vm,
            name="net0",
            enabled=True,
        )
        guest = GuestVMInterface(
            virtual_machine=self.vm,
            vm_interface=other_interface,
            name="ens18",
        )
        with self.assertRaises(ValidationError):
            guest.full_clean()

    def test_fresh_install_defaults_strategy_to_guest_os_model(self) -> None:
        # Migration 0060 makes guest_os_model the universal default even though
        # 0059 briefly preserved legacy_rename for existing installs.
        settings = ProxboxPluginSettings.objects.first()
        self.assertIsNotNone(settings)
        self.assertEqual(settings.vm_interface_sync_strategy, "guest_os_model")

    def test_address_uses_existing_core_ip_and_protects_it(self) -> None:
        guest = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            vm_interface=self.core_interface,
            name="ens19",
        )
        link = GuestVMInterfaceAddress.objects.create(
            guest_interface=guest,
            ip_address=self.ip_address,
        )

        self.assertEqual(link.ip_address, self.ip_address)
        self.assertIn("ens19", str(link))
        self.assertIn(str(self.ip_address), str(link))
        self.assertIn(str(link.pk), link.get_absolute_url())
        with self.assertRaises(ProtectedError):
            self.ip_address.delete()


class GuestVMInterfaceAPITest(TestCase):
    """proxbox-api must be able to CRUD guest interfaces and address links."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.vm = create_test_virtualmachine("guest-if-api-vm")
        cls.core_interface = VMInterface.objects.create(
            virtual_machine=cls.vm,
            name="net0",
            enabled=True,
        )
        cls.ip_address = IPAddress.objects.create(address="198.51.100.50/24")
        cls.user = get_user_model().objects.create_user(
            username="guest-if-api",
            is_staff=True,
        )
        cls.token = Token.objects.create(user=cls.user)
        permission = ObjectPermission.objects.create(
            name="guest-if-rw",
            actions=["view", "add", "change", "delete"],
        )
        permission.object_types.add(ContentType.objects.get_for_model(GuestVMInterface))
        permission.object_types.add(
            ContentType.objects.get_for_model(GuestVMInterfaceAddress)
        )
        permission.users.add(cls.user)

    def _auth_headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    @staticmethod
    def _patch_exists_false_for_model(model):
        original_exists = QuerySet.exists

        def exists(queryset):
            if queryset.model is model:
                return False
            return original_exists(queryset)

        return patch.object(QuerySet, "exists", exists)

    def test_guest_interface_api_crud_round_trip(self) -> None:
        list_url = reverse("plugins-api:netbox_proxbox-api:guestvminterface-list")
        create_response = self.client.post(
            list_url,
            data=json.dumps(
                {
                    "virtual_machine": {"id": self.vm.pk},
                    "vm_interface": {"id": self.core_interface.pk},
                    "name": "ens18",
                    "mac_address": "52:54:00:dd:ee:ff",
                    "enabled": True,
                    "mtu": 1500,
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        guest = GuestVMInterface.objects.get(name="ens18")

        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:guestvminterface-detail",
            args=[guest.pk],
        )
        read_response = self.client.get(detail_url, **self._auth_headers())
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["name"], "ens18")

        patch_response = self.client.patch(
            detail_url,
            data=json.dumps({"enabled": False, "mtu": 9000}),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        guest.refresh_from_db()
        self.assertFalse(guest.enabled)
        self.assertEqual(guest.mtu, 9000)

        delete_response = self.client.delete(detail_url, **self._auth_headers())
        self.assertEqual(delete_response.status_code, 204, delete_response.content)
        self.assertFalse(GuestVMInterface.objects.filter(pk=guest.pk).exists())

    def test_duplicate_core_interface_mapping_returns_400_not_500(self) -> None:
        # vm_interface is one-to-one: the backend can map two guest interfaces
        # sharing a MAC (e.g. a VLAN sub-interface eth0.100 and its parent eth0)
        # to the same core interface. The second write must return a clean 400,
        # not an unhandled IntegrityError (HTTP 500) that could turn a
        # partial-failure stream into a stage abort.
        list_url = reverse("plugins-api:netbox_proxbox-api:guestvminterface-list")
        first = self.client.post(
            list_url,
            data=json.dumps(
                {
                    "virtual_machine": {"id": self.vm.pk},
                    "vm_interface": {"id": self.core_interface.pk},
                    "name": "eth0",
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post(
            list_url,
            data=json.dumps(
                {
                    "virtual_machine": {"id": self.vm.pk},
                    "vm_interface": {"id": self.core_interface.pk},
                    "name": "eth0.100",
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(second.status_code, 400, second.content)
        self.assertIn("vm_interface", second.json())

    def test_duplicate_core_interface_save_race_returns_400_not_500(self) -> None:
        list_url = reverse("plugins-api:netbox_proxbox-api:guestvminterface-list")
        first = self.client.post(
            list_url,
            data=json.dumps(
                {
                    "virtual_machine": {"id": self.vm.pk},
                    "vm_interface": {"id": self.core_interface.pk},
                    "name": "eth1",
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(first.status_code, 201, first.content)

        with self._patch_exists_false_for_model(GuestVMInterface):
            second = self.client.post(
                list_url,
                data=json.dumps(
                    {
                        "virtual_machine": {"id": self.vm.pk},
                        "vm_interface": {"id": self.core_interface.pk},
                        "name": "eth1.100",
                    }
                ),
                content_type="application/json",
                **self._auth_headers(),
            )

        self.assertEqual(second.status_code, 400, second.content)
        self.assertIn("vm_interface", second.json())

    def test_guest_interface_address_api_crud_round_trip(self) -> None:
        guest = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            vm_interface=self.core_interface,
            name="ens19",
        )
        list_url = reverse(
            "plugins-api:netbox_proxbox-api:guestvminterfaceaddress-list"
        )
        create_response = self.client.post(
            list_url,
            data=json.dumps(
                {
                    "guest_interface": {"id": guest.pk},
                    "ip_address": {"id": self.ip_address.pk},
                }
            ),
            content_type="application/json",
            **self._auth_headers(),
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        link = GuestVMInterfaceAddress.objects.get(guest_interface=guest)

        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:guestvminterfaceaddress-detail",
            args=[link.pk],
        )
        read_response = self.client.get(detail_url + "?brief=1", **self._auth_headers())
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["ip_address"]["id"], self.ip_address.pk)

        delete_response = self.client.delete(detail_url, **self._auth_headers())
        self.assertEqual(delete_response.status_code, 204, delete_response.content)
        self.assertFalse(GuestVMInterfaceAddress.objects.filter(pk=link.pk).exists())
        self.assertTrue(IPAddress.objects.filter(pk=self.ip_address.pk).exists())

    def test_guest_interface_address_partial_patch_duplicate_returns_400(
        self,
    ) -> None:
        guest_a = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            vm_interface=self.core_interface,
            name="ens20",
        )
        guest_b = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            name="ens21",
        )
        GuestVMInterfaceAddress.objects.create(
            guest_interface=guest_a,
            ip_address=self.ip_address,
        )
        link_b = GuestVMInterfaceAddress.objects.create(
            guest_interface=guest_b,
            ip_address=self.ip_address,
        )

        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:guestvminterfaceaddress-detail",
            args=[link_b.pk],
        )
        with patch.object(
            GuestVMInterfaceAddress,
            "save",
            side_effect=AssertionError("duplicate partial PATCH reached save"),
        ):
            response = self.client.patch(
                detail_url,
                data=json.dumps({"guest_interface": {"id": guest_a.pk}}),
                content_type="application/json",
                **self._auth_headers(),
            )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("ip_address", response.json())

    def test_guest_interface_address_save_race_returns_400_not_500(self) -> None:
        guest_a = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            vm_interface=self.core_interface,
            name="ens22",
        )
        guest_b = GuestVMInterface.objects.create(
            virtual_machine=self.vm,
            name="ens23",
        )
        GuestVMInterfaceAddress.objects.create(
            guest_interface=guest_a,
            ip_address=self.ip_address,
        )
        link_b = GuestVMInterfaceAddress.objects.create(
            guest_interface=guest_b,
            ip_address=self.ip_address,
        )

        detail_url = reverse(
            "plugins-api:netbox_proxbox-api:guestvminterfaceaddress-detail",
            args=[link_b.pk],
        )
        with self._patch_exists_false_for_model(GuestVMInterfaceAddress):
            response = self.client.patch(
                detail_url,
                data=json.dumps({"guest_interface": {"id": guest_a.pk}}),
                content_type="application/json",
                **self._auth_headers(),
            )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("ip_address", response.json())


class VMInterfaceSyncStrategySettingsTest(TestCase):
    """Settings serializer/form surface the new strategy and deprecated flag."""

    def test_model_default_and_form_help_text(self) -> None:
        settings = ProxboxPluginSettings()
        self.assertEqual(settings.vm_interface_sync_strategy, "guest_os_model")

        form = ProxboxPluginSettingsForm()
        self.assertIn("vm_interface_sync_strategy", form.fields)
        self.assertEqual(
            form.fields["vm_interface_sync_strategy"].initial,
            "guest_os_model",
        )
        self.assertIn("use_guest_agent_interface_name", form.fields)
        self.assertIn(
            "DEPRECATED (used only under the legacy_rename strategy):",
            form.fields["use_guest_agent_interface_name"].help_text,
        )

        serializer = ProxboxPluginSettingsSerializer()
        self.assertIn("vm_interface_sync_strategy", serializer.fields)
        self.assertIn("use_guest_agent_interface_name", serializer.fields)
