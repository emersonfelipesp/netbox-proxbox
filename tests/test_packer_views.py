"""UI tests for the netbox-packer PHASE3 surface."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKER_ROOT = REPO_ROOT / "netbox_packer"
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
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.test import TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from users.models import ObjectPermission  # noqa: E402
from virtualization.models import Cluster, ClusterType  # noqa: E402

from core.models import Job  # noqa: E402
from netbox_packer.choices import (  # noqa: E402
    PackerBuilderTypeChoices,
    PackerOSFamilyChoices,
    PackerProvisionerRecipeChoices,
)
from netbox_packer.filtersets import (  # noqa: E402
    PackerImageBuildFilterSet,
    PackerImageDefinitionFilterSet,
)
from netbox_packer.models import PackerImageBuild, PackerImageDefinition  # noqa: E402
from netbox_proxbox.models import ProxmoxEndpoint  # noqa: E402


class PackerViewTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.endpoint = ProxmoxEndpoint.objects.create(name="pve-ui")
        cls.cluster_type = ClusterType.objects.create(name="Proxmox", slug="proxmox")
        cls.cluster = Cluster.objects.create(
            name="pve-ui-cluster", type=cls.cluster_type
        )
        cls.view_user = get_user_model().objects.create_user(
            username="packer-view",
            is_staff=True,
        )
        cls.edit_user = get_user_model().objects.create_user(
            username="packer-edit",
            is_staff=True,
        )
        cls.build_user = get_user_model().objects.create_user(
            username="packer-build",
            is_staff=True,
        )

        cls.definition = PackerImageDefinition.objects.create(
            name="Ubuntu 24.04 base",
            slug="ubuntu-2404-base",
            description="Jammy successor image definition",
            builder_type=PackerBuilderTypeChoices.PROXMOX_CLONE,
            proxmox_endpoint=cls.endpoint,
            target_cluster=cls.cluster,
            target_node="pve01",
            source_template_vmid=9000,
            default_storage="local-lvm",
            default_bridge="vmbr0",
            os_family=PackerOSFamilyChoices.UBUNTU,
            os_release="24.04",
            default_ciuser="ubuntu",
            provisioner_recipe=PackerProvisionerRecipeChoices.UBUNTU_BASE,
            default_variables={"bridge": "vmbr0"},
        )
        cls.build = PackerImageBuild.objects.create(
            definition=cls.definition,
            proxmox_endpoint=cls.endpoint,
            target_node="pve01",
            output_vmid=9100,
            output_name="ubuntu-2404-base-20260517",
            image_version="2026.05.17",
            created_by=cls.build_user,
        )

        cls._grant(cls.view_user, PackerImageDefinition, ["view"])
        cls._grant(cls.edit_user, PackerImageDefinition, ["view", "add", "change"])
        cls._grant(cls.build_user, PackerImageDefinition, ["view"])
        cls._grant(cls.build_user, PackerImageBuild, ["add"])
        cls._grant(cls.build_user, Job, ["add"])

    @classmethod
    def _grant(cls, user, model: type, actions: list[str]) -> None:
        content_type = ContentType.objects.get_for_model(model)
        permission = ObjectPermission.objects.create(
            name=f"packer-ui-{user.username}-{model._meta.model_name}-{'-'.join(actions)}",
            actions=actions,
        )
        permission.object_types.add(content_type)
        permission.users.add(user)

    def test_anonymous_user_redirected_from_list_views(self) -> None:
        for view_name in (
            "plugins:netbox_packer:packerimagedefinition_list",
            "plugins:netbox_packer:packerimagebuild_list",
        ):
            response = self.client.get(reverse(view_name))
            self.assertEqual(response.status_code, 302, response.content)
            self.assertIn("/login/", response["Location"])

    def test_view_permission_can_list_and_view_but_not_edit(self) -> None:
        self.client.force_login(self.view_user)

        list_response = self.client.get(
            reverse("plugins:netbox_packer:packerimagedefinition_list")
        )
        self.assertEqual(list_response.status_code, 200, list_response.content)

        detail_response = self.client.get(
            reverse(
                "plugins:netbox_packer:packerimagedefinition",
                args=[self.definition.pk],
            )
        )
        self.assertEqual(detail_response.status_code, 200, detail_response.content)

        edit_response = self.client.get(
            reverse(
                "plugins:netbox_packer:packerimagedefinition_edit",
                args=[self.definition.pk],
            )
        )
        self.assertEqual(edit_response.status_code, 403, edit_response.content)

    def test_add_and_change_permission_can_edit(self) -> None:
        self.client.force_login(self.edit_user)
        response = self.client.post(
            reverse(
                "plugins:netbox_packer:packerimagedefinition_edit",
                args=[self.definition.pk],
            ),
            data={
                "name": "Ubuntu 24.04 golden",
                "slug": self.definition.slug,
                "description": self.definition.description,
                "enabled": "on",
                "builder_type": PackerBuilderTypeChoices.PROXMOX_CLONE,
                "proxmox_endpoint": self.endpoint.pk,
                "target_cluster": self.cluster.pk,
                "target_node": self.definition.target_node,
                "source_template_vmid": self.definition.source_template_vmid,
                "default_storage": self.definition.default_storage,
                "default_bridge": self.definition.default_bridge,
                "os_family": PackerOSFamilyChoices.UBUNTU,
                "os_release": self.definition.os_release,
                "default_ciuser": self.definition.default_ciuser,
                "provisioner_recipe": PackerProvisionerRecipeChoices.UBUNTU_BASE,
                "default_variables": "{}",
                "allowed_tenants": [],
                "tags": [],
                "_update": "Save",
            },
        )

        self.assertEqual(response.status_code, 302, response.content)
        self.definition.refresh_from_db()
        self.assertEqual(self.definition.name, "Ubuntu 24.04 golden")

    def test_build_post_returns_202_without_creating_build(self) -> None:
        self.client.force_login(self.build_user)
        before = PackerImageBuild.objects.count()

        response = self.client.post(
            reverse(
                "plugins:netbox_packer:packerimagedefinition_build",
                args=[self.definition.pk],
            ),
            data={
                "output_vmid": "9300",
                "output_name": "ubuntu-2404-base-20260517",
                "image_version": "2026.05.17",
                "dry_run": "",
                "force": "",
            },
        )

        self.assertEqual(response.status_code, 202, response.content)
        self.assertIn(b"Build queueing wired in PHASE4", response.content)
        self.assertEqual(PackerImageBuild.objects.count(), before)

    def test_filterset_search_hits_definition_and_build_text(self) -> None:
        by_name = PackerImageDefinitionFilterSet(
            data={"q": "Ubuntu 24.04"},
            queryset=PackerImageDefinition.objects.all(),
        )
        self.assertIn(self.definition, by_name.qs)

        by_description = PackerImageDefinitionFilterSet(
            data={"q": "successor"},
            queryset=PackerImageDefinition.objects.all(),
        )
        self.assertIn(self.definition, by_description.qs)

        by_output_name = PackerImageBuildFilterSet(
            data={"q": "20260517"},
            queryset=PackerImageBuild.objects.all(),
        )
        self.assertIn(self.build, by_output_name.qs)
