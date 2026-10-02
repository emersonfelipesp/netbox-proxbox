"""Real Django form and API behavior for node Device name templates."""

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

_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

try:
    import django

    django.setup()
except Exception as exc:  # pragma: no cover - depends on external test services
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from django.db import connection  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402

from tests.django_support import ForwardOnlyMigrationTestCase  # noqa: E402
from tests.test_proxmox_endpoint_allowed_tenants import _require_harness  # noqa: E402

pytestmark = pytest.mark.django_db


class NodeDeviceNameTemplateMigrationTest(ForwardOnlyMigrationTestCase):
    """Prove 0103 forward, state-only rollback, and idempotent reapply."""

    migrate_from = ("netbox_proxbox", "0102_vm_cloudinit_openbao_references")
    migration_floor = migrate_from
    migrate_to = (
        "netbox_proxbox",
        "0103_custom_fields_request_delay_help_text",
    )

    @staticmethod
    def _columns(table: str) -> set[str]:
        with connection.cursor() as cursor:
            return {
                description.name
                for description in connection.introspection.get_table_description(
                    cursor, table
                )
            }

    def test_forward_rollback_and_reapply_preserve_additive_columns(self) -> None:
        try:
            apps_before = self._migrate_to(self.migrate_from)
            SettingsBefore = apps_before.get_model(
                "netbox_proxbox", "ProxboxPluginSettings"
            )
            EndpointBefore = apps_before.get_model("netbox_proxbox", "ProxmoxEndpoint")
            self.assertNotIn(
                "node_device_name_template",
                {field.name for field in SettingsBefore._meta.get_fields()},
            )
            self.assertNotIn(
                "node_device_name_template",
                {field.name for field in EndpointBefore._meta.get_fields()},
            )
            self.assertNotIn(
                "sync_job_timeout",
                {field.name for field in SettingsBefore._meta.get_fields()},
            )

            apps_after = self._migrate_to(self.migrate_to)
            SettingsAfter = apps_after.get_model(
                "netbox_proxbox", "ProxboxPluginSettings"
            )
            EndpointAfter = apps_after.get_model("netbox_proxbox", "ProxmoxEndpoint")
            settings_table = SettingsAfter._meta.db_table
            endpoint_table = EndpointAfter._meta.db_table
            self.assertIn("node_device_name_template", self._columns(settings_table))
            self.assertIn("node_device_name_template", self._columns(endpoint_table))
            self.assertIn("sync_job_timeout", self._columns(settings_table))

            apps_rollback = self._migrate_to(self.migrate_from)
            SettingsRollback = apps_rollback.get_model(
                "netbox_proxbox", "ProxboxPluginSettings"
            )
            EndpointRollback = apps_rollback.get_model(
                "netbox_proxbox", "ProxmoxEndpoint"
            )
            self.assertNotIn(
                "node_device_name_template",
                {field.name for field in SettingsRollback._meta.get_fields()},
            )
            self.assertNotIn(
                "node_device_name_template",
                {field.name for field in EndpointRollback._meta.get_fields()},
            )
            self.assertNotIn(
                "sync_job_timeout",
                {field.name for field in SettingsRollback._meta.get_fields()},
            )
            self.assertIn("node_device_name_template", self._columns(settings_table))
            self.assertIn("node_device_name_template", self._columns(endpoint_table))
            self.assertIn("sync_job_timeout", self._columns(settings_table))

            apps_reapplied = self._migrate_to(self.migrate_to)
            self.assertIn(
                "node_device_name_template",
                {
                    field.name
                    for field in apps_reapplied.get_model(
                        "netbox_proxbox", "ProxboxPluginSettings"
                    )._meta.get_fields()
                },
            )
            self.assertIn(
                "sync_job_timeout",
                {
                    field.name
                    for field in apps_reapplied.get_model(
                        "netbox_proxbox", "ProxboxPluginSettings"
                    )._meta.get_fields()
                },
            )
            self.assertEqual(
                MigrationExecutor(connection).loader.graph.leaf_nodes("netbox_proxbox"),
                [self.migrate_to],
            )
        finally:
            self._restore_current_leaf()


@pytest.fixture
def naming_models(pytestconfig, request):
    _require_harness(pytestconfig)
    request.getfixturevalue("db")
    from netbox_proxbox.models import (
        ProxboxPluginSettings,
        ProxmoxCluster,
        ProxmoxEndpoint,
        ProxmoxNode,
    )

    return ProxboxPluginSettings, ProxmoxCluster, ProxmoxEndpoint, ProxmoxNode


def _endpoint(Endpoint, *, name: str, template: str = ""):
    return Endpoint.objects.create(
        name=name,
        domain="pve.example.test",
        username="root@pam",
        node_device_name_template=template,
        enabled=False,
    )


def test_settings_form_rejects_overlength_real_cluster(naming_models) -> None:
    from netbox_proxbox.forms.proxmox import ProxmoxEndpointSettingsForm

    _, Cluster, Endpoint, Node = naming_models
    endpoint = _endpoint(Endpoint, name="pve")
    cluster = Cluster.objects.create(endpoint=endpoint, name="c" * 60)
    Node.objects.create(
        endpoint=endpoint,
        proxmox_cluster=cluster,
        name="node1",
        ip_address=".".join(("192", "0", "2", "10")),
    )

    form = ProxmoxEndpointSettingsForm(
        data={"node_device_name_template": "{node}.{cluster}"},
        instance=endpoint,
    )

    assert not form.is_valid()
    assert "66 characters" in str(form.errors["node_device_name_template"])


def test_endpoint_api_create_rejects_inherited_template_for_submitted_name(
    naming_models,
) -> None:
    from netbox_proxbox.api.serializers.endpoints import ProxmoxEndpointSerializer

    Settings, _, _, _ = naming_models
    settings = Settings.get_solo()
    settings.node_device_name_template = "{node}.{endpoint}"
    settings.save(update_fields=["node_device_name_template"])

    serializer = ProxmoxEndpointSerializer(
        data={
            "name": "e" * 60,
            "domain": "pve.example.test",
            "mode": "cluster",
            "node_device_name_template": "",
        }
    )

    assert not serializer.is_valid()
    assert "node_device_name_template" in serializer.errors


def test_endpoint_api_rename_rejects_inherited_template_without_inventory(
    naming_models,
) -> None:
    from netbox_proxbox.api.serializers.endpoints import ProxmoxEndpointSerializer

    Settings, _, Endpoint, _ = naming_models
    settings = Settings.get_solo()
    settings.node_device_name_template = "{node}.{endpoint}"
    settings.save(update_fields=["node_device_name_template"])
    endpoint = _endpoint(Endpoint, name="short")

    serializer = ProxmoxEndpointSerializer(
        endpoint,
        data={"name": "e" * 60},
        partial=True,
    )

    assert not serializer.is_valid()
    assert "node_device_name_template" in serializer.errors


def test_global_api_rejects_inheriting_endpoint_without_inventory(
    naming_models,
) -> None:
    from netbox_proxbox.api.serializers.settings import (
        ProxboxPluginSettingsSerializer,
    )

    Settings, _, Endpoint, _ = naming_models
    settings = Settings.get_solo()
    _endpoint(Endpoint, name="e" * 60)

    serializer = ProxboxPluginSettingsSerializer(
        settings,
        data={"node_device_name_template": "{node}.{endpoint}"},
        partial=True,
    )

    assert not serializer.is_valid()
    assert "node_device_name_template" in serializer.errors
