"""Model tests for the netbox-packer scaffold."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


PACKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKER_ROOT.parent
NETBOX_ROOTS = (
    Path("/opt/netbox/netbox"),
    REPO_ROOT.parent / "netbox" / "netbox",
)

for candidate in reversed((PACKER_ROOT, REPO_ROOT, *NETBOX_ROOTS)):
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
        f"NetBox test environment is not available: {exc}",
        allow_module_level=True,
    )

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.db import IntegrityError, transaction  # noqa: E402
from django.test import TestCase  # noqa: E402
from tenancy.models import Tenant  # noqa: E402
from virtualization.models import Cluster, ClusterType  # noqa: E402

from netbox_packer.choices import (  # noqa: E402
    PackerBuildStatusChoices,
    PackerBuilderTypeChoices,
    PackerOSFamilyChoices,
    PackerProvisionerRecipeChoices,
)
from netbox_packer.models import (  # noqa: E402
    PackerImageBuild,
    PackerImageDefinition,
    PackerPluginSettings,
)
from netbox_proxbox.models import ProxmoxEndpoint  # noqa: E402


class PackerModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.endpoint = ProxmoxEndpoint.objects.create(name="pve-packer")
        cls.cluster_type = ClusterType.objects.create(name="Proxmox", slug="proxmox")
        cls.cluster = Cluster.objects.create(name="pve-cluster", type=cls.cluster_type)
        cls.user = get_user_model().objects.create_user(username="packer-builder")

    def _create_definition(
        self,
        *,
        name: str = "Ubuntu 24.04 base",
        slug: str = "ubuntu-2404-base",
    ) -> PackerImageDefinition:
        return PackerImageDefinition.objects.create(
            name=name,
            slug=slug,
            builder_type=PackerBuilderTypeChoices.PROXMOX_CLONE,
            proxmox_endpoint=self.endpoint,
            target_cluster=self.cluster,
            target_node="pve01",
            source_template_vmid=9000,
            default_storage="local-lvm",
            default_bridge="vmbr0",
            os_family=PackerOSFamilyChoices.UBUNTU,
            os_release="24.04",
            default_ciuser="ubuntu",
            provisioner_recipe=PackerProvisionerRecipeChoices.UBUNTU_BASE,
            default_variables={"bridge": "vmbr0", "cores": 2},
        )

    def _create_build(self) -> PackerImageBuild:
        definition = self._create_definition()
        return PackerImageBuild.objects.create(
            definition=definition,
            proxmox_endpoint=self.endpoint,
            target_node="pve01",
            output_vmid=9100,
            output_name="ubuntu-2404-base-20260517",
            image_version="2026.05.17",
            created_by=self.user,
        )

    def test_create_all_models(self) -> None:
        definition = self._create_definition()
        build = PackerImageBuild.objects.create(
            definition=definition,
            status=PackerBuildStatusChoices.PENDING,
            backend_build_id="build-123",
            proxmox_endpoint=self.endpoint,
            target_node="pve01",
            output_vmid=9101,
            output_name="ubuntu-2404-base-20260517",
            image_version="2026.05.17",
            created_by=self.user,
            backend_response={"accepted": True},
        )
        settings = PackerPluginSettings.objects.create(image_factory_enabled=True)

        self.assertEqual(str(definition), "Ubuntu 24.04 base")
        self.assertEqual(build.status, PackerBuildStatusChoices.PENDING)
        self.assertEqual(settings.singleton_key, "default")

    def test_definition_slug_uniqueness(self) -> None:
        self._create_definition()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._create_definition(name="Ubuntu duplicate", slug="ubuntu-2404-base")

    def test_definition_allowed_tenants_round_trip(self) -> None:
        definition = self._create_definition()
        tenants = [
            Tenant.objects.create(name="Tenant A", slug="tenant-a"),
            Tenant.objects.create(name="Tenant B", slug="tenant-b"),
        ]
        definition.allowed_tenants.add(*tenants)

        self.assertEqual(
            set(definition.allowed_tenants.values_list("slug", flat=True)),
            {"tenant-a", "tenant-b"},
        )

    def test_proxmox_clone_requires_target_cluster(self) -> None:
        definition = PackerImageDefinition(
            name="Clusterless clone",
            slug="clusterless-clone",
            builder_type=PackerBuilderTypeChoices.PROXMOX_CLONE,
            proxmox_endpoint=self.endpoint,
            target_node="pve01",
            source_template_vmid=9000,
            default_storage="local-lvm",
            os_family=PackerOSFamilyChoices.UBUNTU,
            os_release="24.04",
            provisioner_recipe=PackerProvisionerRecipeChoices.UBUNTU_BASE,
        )

        with self.assertRaises(ValidationError):
            definition.full_clean()

    def test_status_transition_completed(self) -> None:
        build = self._create_build()
        for status in (
            PackerBuildStatusChoices.RUNNING,
            PackerBuildStatusChoices.COMPLETED,
        ):
            build.status = status
            build.save(update_fields=["status"])
            build.refresh_from_db()
            self.assertEqual(build.status, status)

    def test_status_transition_failed(self) -> None:
        build = self._create_build()
        for status in (
            PackerBuildStatusChoices.RUNNING,
            PackerBuildStatusChoices.FAILED,
        ):
            build.status = status
            build.save(update_fields=["status"])
            build.refresh_from_db()
            self.assertEqual(build.status, status)

    def test_status_transition_cancelled(self) -> None:
        build = self._create_build()
        build.status = PackerBuildStatusChoices.CANCELLED
        build.save(update_fields=["status"])
        build.refresh_from_db()

        self.assertEqual(build.status, PackerBuildStatusChoices.CANCELLED)

    def test_plugin_settings_get_solo_returns_same_row(self) -> None:
        first = PackerPluginSettings.get_solo()
        second = PackerPluginSettings.get_solo()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PackerPluginSettings.objects.count(), 1)
