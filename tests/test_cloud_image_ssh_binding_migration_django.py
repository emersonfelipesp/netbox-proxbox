"""Real-Django coverage for the Cloud Image SSH binding migration."""

from __future__ import annotations

import pytest

# Never set NETBOX_PROXBOX_REQUIRE_DJANGO here: the real-Django workflow
# supplies it through its environment, and setting it during collection leaks
# into the mocked suite and turns every later real-Django module's skip into a
# collection error.
django = pytest.importorskip("django")
if not hasattr(django, "__path__"):
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

from django.apps.registry import Apps  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import TransactionTestCase  # noqa: E402


class CloudImageSSHBindingMigrationTest(TransactionTestCase):
    """Apply, cleanly reverse, and reapply the release endpoint fields."""

    before = ("netbox_proxbox", "0106_device_sync_scope_and_netbox_token_approval")
    after = ("netbox_proxbox", "0107_v0_0_30_release")

    def _migrate(self, target: tuple[str, str]) -> Apps:
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        targets = [
            node
            for node in executor.loader.graph.leaf_nodes()
            if node[0] != "netbox_proxbox"
        ] + [target]
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self) -> None:
        # Restore the real plugin leaf, not this migration: a later migration
        # would otherwise leave the shared test database below the leaf.
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        plugin_leaves = tuple(executor.loader.graph.leaf_nodes("netbox_proxbox"))
        self.assertEqual(len(plugin_leaves), 1)
        self._migrate(plugin_leaves[0])
        super().tearDown()

    def test_additive_fields_apply_reverse_and_reapply(self) -> None:
        before_apps = self._migrate(self.before)
        BeforeEndpoint = before_apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        self.assertNotIn(
            "cloud_image_ssh_target_node",
            {field.name for field in BeforeEndpoint._meta.get_fields()},
        )

        after_apps = self._migrate(self.after)
        AfterEndpoint = after_apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        endpoint = AfterEndpoint.objects.create(
            name="cloud-image-migration",
            cloud_image_ssh_target_node="pve-node-2",
            cloud_image_ssh_identity_file="/srv/proxbox/ssh/image-builder",
            cloud_image_ssh_binding_fingerprint="f" * 64,
        )
        endpoint.refresh_from_db()
        self.assertEqual(endpoint.cloud_image_ssh_target_node, "pve-node-2")
        self.assertEqual(
            endpoint.cloud_image_ssh_identity_file,
            "/srv/proxbox/ssh/image-builder",
        )
        self.assertEqual(endpoint.cloud_image_ssh_binding_fingerprint, "f" * 64)

        reversed_apps = self._migrate(self.before)
        ReversedEndpoint = reversed_apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        reversed_fields = {field.name for field in ReversedEndpoint._meta.get_fields()}
        self.assertNotIn("cloud_image_ssh_target_node", reversed_fields)
        self.assertNotIn("cloud_image_ssh_identity_file", reversed_fields)
        self.assertNotIn("cloud_image_ssh_binding_fingerprint", reversed_fields)
        retained_default = ReversedEndpoint.objects.create(
            name="cloud-image-migration-after-reverse"
        )

        reapplied_apps = self._migrate(self.after)
        ReappliedEndpoint = reapplied_apps.get_model(
            "netbox_proxbox", "ProxmoxEndpoint"
        )
        reapplied_fields = {
            field.name for field in ReappliedEndpoint._meta.get_fields()
        }
        self.assertIn("cloud_image_ssh_target_node", reapplied_fields)
        self.assertIn("cloud_image_ssh_identity_file", reapplied_fields)
        self.assertIn("cloud_image_ssh_binding_fingerprint", reapplied_fields)
        reset = ReappliedEndpoint.objects.get(pk=endpoint.pk)
        self.assertEqual(reset.cloud_image_ssh_target_node, "")
        self.assertEqual(reset.cloud_image_ssh_identity_file, "")
        self.assertEqual(reset.cloud_image_ssh_binding_fingerprint, "")
        defaulted = ReappliedEndpoint.objects.get(pk=retained_default.pk)
        self.assertEqual(defaulted.cloud_image_ssh_target_node, "")
        self.assertEqual(defaulted.cloud_image_ssh_identity_file, "")
        self.assertEqual(defaulted.cloud_image_ssh_binding_fingerprint, "")
