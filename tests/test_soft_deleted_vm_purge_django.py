"""Database-backed safety tests for the human-only soft-deleted VM purge."""

from __future__ import annotations

import os

import pytest

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
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

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
from django.test import Client, TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from extras.models import Tag  # noqa: E402
from virtualization.models import VirtualMachine  # noqa: E402

from netbox_proxbox.constants import (  # noqa: E402
    SOFT_DELETE_TAG_SLUG,
    SOFT_DELETE_VM_STATUS,
)


class SoftDeletedVirtualMachinePurgeTest(TestCase):
    """Exercise the actual NetBox queryset and destructive bulk endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tag = Tag.objects.create(
            name="Proxbox: Soft-deleted VM",
            slug=SOFT_DELETE_TAG_SLUG,
            color="d32f2f",
        )
        cls.marked_qemu = cls._create_vm("marked-qemu", SOFT_DELETE_VM_STATUS)
        cls.marked_qemu.tags.add(cls.tag)
        cls.marked_lxc = cls._create_vm("marked-lxc", SOFT_DELETE_VM_STATUS)
        cls.marked_lxc.tags.add(cls.tag)
        cls.active_with_marker = cls._create_vm("active-with-marker", "active")
        cls.active_with_marker.tags.add(cls.tag)
        cls.unmarked_decommissioned = cls._create_vm(
            "unmarked-decommissioned", SOFT_DELETE_VM_STATUS
        )

    @staticmethod
    def _create_vm(name: str, status: str) -> VirtualMachine:
        return VirtualMachine.objects.create(name=name, status=status)

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_superuser(
            username=f"purge-{self._testMethodName}",
            email="purge@example.invalid",
            password="test-password",
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.list_url = reverse("plugins:netbox_proxbox:soft_deleted_vms")
        self.delete_url = reverse("plugins:netbox_proxbox:soft_deleted_vms_bulk_delete")

    def test_page_lists_only_marked_vms_with_required_status(self) -> None:
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "marked-qemu")
        self.assertContains(response, "marked-lxc")
        self.assertNotContains(response, "active-with-marker")
        self.assertNotContains(response, "unmarked-decommissioned")

    def test_permission_denial_prevents_page_access(self) -> None:
        user = get_user_model().objects.create_user(
            username="purge-without-delete",
            password="test-password",
        )
        client = Client()
        client.force_login(user)

        response = client.get(self.list_url)

        self.assertEqual(response.status_code, 403)

    def test_selected_ids_delete_only_marked_vms(self) -> None:
        confirmation = self.client.post(
            self.delete_url,
            {
                "pk": [
                    str(self.marked_qemu.pk),
                    str(self.active_with_marker.pk),
                ],
            },
        )
        self.assertEqual(confirmation.status_code, 200)

        response = self.client.post(
            self.delete_url,
            {
                "pk": [
                    str(self.marked_qemu.pk),
                    str(self.active_with_marker.pk),
                ],
                "_confirm": "on",
            },
        )

        self.assertIn(response.status_code, (200, 302))
        self.assertFalse(VirtualMachine.objects.filter(pk=self.marked_qemu.pk).exists())
        self.assertTrue(
            VirtualMachine.objects.filter(pk=self.active_with_marker.pk).exists()
        )

    def test_select_all_deletes_only_marked_vms(self) -> None:
        confirmation = self.client.post(
            self.delete_url,
            {"_all": "on"},
        )
        self.assertEqual(confirmation.status_code, 200)

        response = self.client.post(
            self.delete_url,
            {"_all": "on", "_confirm": "on"},
        )

        self.assertIn(response.status_code, (200, 302))
        self.assertFalse(
            VirtualMachine.objects.filter(
                pk__in=(self.marked_qemu.pk, self.marked_lxc.pk)
            ).exists()
        )
        self.assertTrue(
            VirtualMachine.objects.filter(
                pk__in=(self.active_with_marker.pk, self.unmarked_decommissioned.pk)
            ).exists()
        )
