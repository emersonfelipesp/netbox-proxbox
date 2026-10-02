"""Real-Django regressions for cluster-scoped virtual-machine bulk deletion."""

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

from django.test import Client, TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from virtualization.models import Cluster, ClusterType, VirtualMachine  # noqa: E402

from tests.django_support import make_user  # noqa: E402


class ClusterScopedVirtualMachineBulkDeleteTest(TestCase):
    """Exercise NetBox's actual core bulk-delete endpoint from a cluster view."""

    @classmethod
    def setUpTestData(cls) -> None:
        cluster_type = ClusterType.objects.create(
            name="Bulk delete", slug="bulk-delete"
        )
        cls.cluster = Cluster.objects.create(
            name="bulk-delete-cluster", type=cluster_type
        )
        cls.other_cluster = Cluster.objects.create(
            name="bulk-delete-other-cluster", type=cluster_type
        )
        cls.selected = [
            VirtualMachine.objects.create(
                name=f"bulk-delete-selected-{index}", cluster=cls.cluster
            )
            for index in range(3)
        ]
        cls.same_cluster_survivor = VirtualMachine.objects.create(
            name="bulk-delete-same-cluster-survivor", cluster=cls.cluster
        )
        cls.other_cluster_survivor = VirtualMachine.objects.create(
            name="bulk-delete-other-cluster-survivor", cluster=cls.other_cluster
        )

    def setUp(self) -> None:
        self.user = make_user(
            username=f"bulk-delete-{self._testMethodName}",
            email="bulk-delete@example.invalid",
            password="test-password",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.delete_url = reverse("virtualization:virtualmachine_bulk_delete")

    def test_selected_cluster_virtual_machines_delete_as_one_request(self) -> None:
        selected_ids = [str(vm.pk) for vm in self.selected]

        confirmation = self.client.post(self.delete_url, {"pk": selected_ids})
        self.assertEqual(confirmation.status_code, 200)

        response = self.client.post(
            self.delete_url,
            {
                "pk": selected_ids,
                "confirm": "on",
                "_confirm": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            VirtualMachine.objects.filter(
                pk__in=[vm.pk for vm in self.selected]
            ).exists()
        )
        self.assertTrue(
            VirtualMachine.objects.filter(pk=self.same_cluster_survivor.pk).exists()
        )
        self.assertTrue(
            VirtualMachine.objects.filter(pk=self.other_cluster_survivor.pk).exists()
        )

    def test_cluster_tab_targets_virtual_machine_bulk_delete(self) -> None:
        response = self.client.get(
            reverse(
                "virtualization:cluster_virtualmachines",
                kwargs={"pk": self.cluster.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'formaction="{self.delete_url}?return_url=',
            html=False,
        )

    def test_vm_bulk_delete_requires_delete_permission(self) -> None:
        view_only_user = make_user(
            username="bulk-delete-view-only", password="test-password"
        )
        client = Client()
        client.force_login(view_only_user)

        response = client.post(
            self.delete_url,
            {
                "pk": [str(self.selected[0].pk)],
                "confirm": "on",
                "_confirm": "on",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(VirtualMachine.objects.filter(pk=self.selected[0].pk).exists())

    def test_parent_cluster_delete_remains_protected_by_virtual_machines(self) -> None:
        cluster_delete_url = reverse("virtualization:cluster_bulk_delete")

        response = self.client.post(
            cluster_delete_url,
            {
                "pk": [str(self.cluster.pk)],
                "confirm": "on",
                "_confirm": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Cluster.objects.filter(pk=self.cluster.pk).exists())
        self.assertContains(response, "dependent objects were found")
