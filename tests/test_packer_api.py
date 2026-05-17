"""API tests for the netbox-packer scaffold."""

from __future__ import annotations

import json
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
from users.models import ObjectPermission, Token  # noqa: E402
from virtualization.models import Cluster, ClusterType  # noqa: E402

from netbox_packer.choices import (  # noqa: E402
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


class PackerAPITest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.endpoint = ProxmoxEndpoint.objects.create(name="pve-api")
        cls.cluster_type = ClusterType.objects.create(name="Proxmox", slug="proxmox")
        cls.cluster = Cluster.objects.create(
            name="pve-api-cluster", type=cls.cluster_type
        )
        cls.user = get_user_model().objects.create_user(
            username="packer-api",
            is_staff=True,
        )
        cls.token = Token.objects.create(user=cls.user)

        cls.definition = PackerImageDefinition.objects.create(
            name="Debian 13 base",
            slug="debian-13-base",
            builder_type=PackerBuilderTypeChoices.PROXMOX_CLONE,
            proxmox_endpoint=cls.endpoint,
            target_cluster=cls.cluster,
            target_node="pve01",
            source_template_vmid=9001,
            default_storage="local-lvm",
            default_bridge="vmbr0",
            os_family=PackerOSFamilyChoices.DEBIAN,
            os_release="13",
            default_ciuser="debian",
            provisioner_recipe=PackerProvisionerRecipeChoices.DEBIAN_BASE,
            default_variables={"bridge": "vmbr0"},
        )
        cls.build = PackerImageBuild.objects.create(
            definition=cls.definition,
            proxmox_endpoint=cls.endpoint,
            target_node="pve01",
            output_vmid=9200,
            output_name="debian-13-base-20260517",
            image_version="2026.05.17",
            created_by=cls.user,
        )
        cls.settings = PackerPluginSettings.get_solo()

        for model in (PackerImageDefinition, PackerImageBuild, PackerPluginSettings):
            cls._grant(model, ["view"])
        cls._grant(PackerImageDefinition, ["add"])

    @classmethod
    def _grant(cls, model: type, actions: list[str]) -> None:
        content_type = ContentType.objects.get_for_model(model)
        permission = ObjectPermission.objects.create(
            name=f"packer-{model._meta.model_name}-{'-'.join(actions)}",
            actions=actions,
        )
        permission.object_types.add(content_type)
        permission.users.add(cls.user)

    def _headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_definition_list_and_retrieve(self) -> None:
        list_url = reverse("plugins-api:netbox_packer-api:packerimagedefinition-list")
        detail_url = reverse(
            "plugins-api:netbox_packer-api:packerimagedefinition-detail",
            args=[self.definition.pk],
        )

        response = self.client.get(list_url, **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 1)

        response = self.client.get(detail_url, **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["slug"], "debian-13-base")

    def test_build_list_and_retrieve(self) -> None:
        list_url = reverse("plugins-api:netbox_packer-api:packerimagebuild-list")
        detail_url = reverse(
            "plugins-api:netbox_packer-api:packerimagebuild-detail",
            args=[self.build.pk],
        )

        response = self.client.get(list_url, **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 1)

        response = self.client.get(detail_url, **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["output_vmid"], 9200)

    def test_settings_list_and_retrieve(self) -> None:
        list_url = reverse("plugins-api:netbox_packer-api:packerpluginsettings-list")
        detail_url = reverse(
            "plugins-api:netbox_packer-api:packerpluginsettings-detail",
            args=[self.settings.pk],
        )

        response = self.client.get(list_url, **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 1)

        response = self.client.get(detail_url, **self._headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["singleton_key"], "default")

    def test_default_variables_reject_unknown_keys(self) -> None:
        url = reverse("plugins-api:netbox_packer-api:packerimagedefinition-list")
        payload = {
            "name": "Invalid variables",
            "slug": "invalid-variables",
            "builder_type": PackerBuilderTypeChoices.PROXMOX_CLONE,
            "proxmox_endpoint": self.endpoint.pk,
            "target_cluster": self.cluster.pk,
            "target_node": "pve01",
            "source_template_vmid": 9002,
            "default_storage": "local-lvm",
            "default_bridge": "vmbr0",
            "os_family": PackerOSFamilyChoices.UBUNTU,
            "os_release": "24.04",
            "default_ciuser": "ubuntu",
            "provisioner_recipe": PackerProvisionerRecipeChoices.UBUNTU_BASE,
            "default_variables": {"bridge": "vmbr0", "unknown_key": "nope"},
        }

        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **self._headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("default_variables", response.json())
