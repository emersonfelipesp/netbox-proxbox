"""Real-NetBox endpoint and native cluster ownership contracts."""
# ruff: noqa: E402

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from threading import Barrier
from unittest.mock import patch

import pytest

from tests.netbox_test_paths import netbox_source_roots


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = netbox_source_roots(REPO_ROOT)
_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    if _REQUIRE_DJANGO:
        raise RuntimeError("A real Django package is required for this test module.")
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

for candidate_path in NETBOX_ROOTS:
    candidate_string = str(candidate_path)
    if candidate_path.exists() and candidate_string not in sys.path:
        sys.path.insert(0, candidate_string)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )


from importlib import import_module  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from django.apps import apps  # noqa: E402
from django.apps.registry import Apps  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.http import HttpResponse  # noqa: E402
from django.db import IntegrityError, connection, transaction  # noqa: E402
from django.test import TestCase, TransactionTestCase, RequestFactory  # noqa: E402
from django.urls import reverse  # noqa: E402
from users.models import ObjectPermission  # noqa: E402
from virtualization.models import Cluster, ClusterType  # noqa: E402
from netbox_proxbox.models import (
    ProxmoxEndpoint,
    ProxmoxCluster,
    ProxboxClusterSyncState,
    ProxboxPluginSettings,
)  # noqa: E402
from netbox_proxbox.api.serializers.endpoints import ProxmoxEndpointSerializer  # noqa: E402
from netbox_proxbox.services.cluster_binding import (
    synchronize_cluster,
    ClusterBindingConflict,
)  # noqa: E402
from netbox_proxbox.services.sync_cluster import _sync_cluster_record  # noqa: E402
from netbox_proxbox.schemas import ClusterSyncResult  # noqa: E402
from netbox_proxbox.template_content import ProxmoxClusterTemplateExtension  # noqa: E402
from tests.django_support import make_api_token, make_user  # noqa: E402


class EndpointClusterBindingTest(TestCase):
    def setUp(self) -> None:
        ProxboxPluginSettings.objects.get_or_create(singleton_key="default")
        self.admin = make_user("cluster-admin", is_superuser=True)
        self.cluster_type = ClusterType.objects.create(name="PVE", slug="pve")
        self.endpoint = ProxmoxEndpoint.objects.create(
            name="Source", domain="source.example.test", enabled=True
        )
        self.values = {
            "name": "real-cluster",
            "mode": "cluster",
            "cluster_type": self.cluster_type,
        }

    def sync(self, **changes) -> tuple[Cluster, ProxmoxCluster, bool]:
        return synchronize_cluster(self.endpoint.pk, self.admin, self.values | changes)

    def test_create_retry_and_preflight_rename_preserve_native_and_tracking_identity(
        self,
    ) -> None:
        core, tracking, created = self.sync()
        self.assertTrue(created)
        repeated, again, created = self.sync()
        self.assertFalse(created)
        self.assertEqual((repeated.pk, again.pk), (core.pk, tracking.pk))
        self.endpoint.refresh_from_db()
        record = SimpleNamespace(
            name="renamed", id="cluster-identity", nodes=2, quorate=1, version=4
        )
        prepared = _sync_cluster_record(
            self.endpoint,
            self.endpoint.pk,
            record,
            [],
            "always",
            "cluster",
            ClusterSyncResult(),
        )
        self.assertEqual(prepared.pk, tracking.pk)
        renamed, again, created = self.sync(name="renamed")
        self.assertEqual((renamed.pk, again.pk), (core.pk, tracking.pk))
        self.assertEqual(renamed.name, "renamed")
        self.assertEqual(
            ProxmoxCluster.objects.filter(endpoint=self.endpoint).count(), 1
        )
        self.assertEqual(
            ProxboxClusterSyncState.objects.get(cluster=core).proxmox_cluster_id,
            tracking.pk,
        )

    def test_orm_one_to_one_and_deletion_preserve_the_other_object(self) -> None:
        core, tracking, _ = self.sync()
        other = ProxmoxEndpoint.objects.create(
            name="Other", domain="other.example.test"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProxmoxEndpoint.objects.filter(pk=other.pk).update(netbox_cluster=core)
        core.delete()
        self.endpoint.refresh_from_db()
        tracking.refresh_from_db()
        self.assertIsNone(self.endpoint.netbox_cluster_id)
        self.assertIsNone(tracking.netbox_cluster_id)
        new_core, _, _ = self.sync()
        self.endpoint.delete()
        self.assertTrue(Cluster.objects.filter(pk=new_core.pk).exists())

    def test_foreign_same_name_is_never_adopted_or_modified(self) -> None:
        other = ProxmoxEndpoint.objects.create(
            name="Other", domain="other.example.test"
        )
        foreign = Cluster.objects.create(name="real-cluster", type=self.cluster_type)
        ProxmoxEndpoint.objects.filter(pk=other.pk).update(netbox_cluster=foreign)
        ProxmoxCluster.objects.bulk_create(
            [
                ProxmoxCluster(
                    endpoint=other, netbox_cluster=foreign, name="foreign-source"
                )
            ]
        )
        try:
            own, _, _ = self.sync()
        except ClusterBindingConflict:
            self.endpoint.refresh_from_db()
            self.assertIsNone(self.endpoint.netbox_cluster_id)
        else:
            self.assertNotEqual(own.pk, foreign.pk)
        foreign.refresh_from_db()
        self.assertEqual(foreign.name, "real-cluster")
        other.refresh_from_db()
        self.assertEqual(other.netbox_cluster_id, foreign.pk)

    def test_sidecar_conflict_rolls_back_rename_and_endpoint_claim(self) -> None:
        core, tracking, _ = self.sync()
        wrong = ProxmoxCluster.objects.create(endpoint=self.endpoint, name="obsolete")
        ProxboxClusterSyncState.objects.filter(cluster=core).update(
            proxmox_cluster=wrong
        )
        with self.assertRaises(ClusterBindingConflict):
            self.sync(name="rolled-back")
        core.refresh_from_db()
        tracking.refresh_from_db()
        self.assertEqual(core.name, "real-cluster")
        self.assertEqual(tracking.name, "real-cluster")

    def test_tracking_save_refuses_conflicting_claim_and_reassignment(self) -> None:
        core, tracking, _ = self.sync()
        other_core = Cluster.objects.create(name="other", type=self.cluster_type)
        tracking.netbox_cluster = other_core
        with self.assertRaises(ValidationError):
            tracking.save()
        other = ProxmoxEndpoint.objects.create(
            name="Other", domain="other.example.test"
        )
        with self.assertRaises(ValidationError):
            ProxmoxCluster.objects.create(
                endpoint=other, netbox_cluster=core, name="foreign"
            )
        self.assertFalse(ProxmoxCluster.objects.filter(endpoint=other).exists())

    def test_migration_backfill_keeps_globally_ambiguous_pairs_unclaimed(self) -> None:
        unique = Cluster.objects.create(name="unique", type=self.cluster_type)
        shared = Cluster.objects.create(name="shared", type=self.cluster_type)
        other = ProxmoxEndpoint.objects.create(
            name="Other", domain="other.example.test"
        )
        third = ProxmoxEndpoint.objects.create(
            name="Third", domain="third.example.test"
        )
        ProxmoxCluster.objects.bulk_create(
            [
                ProxmoxCluster(
                    endpoint=self.endpoint, netbox_cluster=unique, name="unique"
                ),
                ProxmoxCluster(endpoint=other, netbox_cluster=shared, name="other"),
                ProxmoxCluster(endpoint=third, netbox_cluster=shared, name="third"),
            ]
        )
        migration = import_module("netbox_proxbox.migrations.0107_v0_0_30_release")
        migration.backfill_cluster_bindings(
            apps, SimpleNamespace(connection=connection)
        )
        self.endpoint.refresh_from_db()
        other.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual(self.endpoint.netbox_cluster_id, unique.pk)
        self.assertIsNone(other.netbox_cluster_id)
        self.assertIsNone(third.netbox_cluster_id)

    def _grant(self, user, model, actions, constraints=None) -> None:
        grant = ObjectPermission.objects.create(
            name=f"{model._meta.model_name}-{actions}",
            actions=actions,
            constraints=constraints,
        )
        grant.object_types.add(ContentType.objects.get_for_model(model))
        grant.users.add(user)

    def _post(self, user=None, *, read_only=False) -> HttpResponse:
        token, headers = make_api_token(user or self.admin)
        if read_only:
            token.write_enabled = False
            token.save(update_fields=["write_enabled"])
        return self.client.post(
            reverse(
                "plugins-api:netbox_proxbox-api:endpoints:proxmoxendpoint-sync-cluster",
                args=[self.endpoint.pk],
            ),
            data={
                "name": "real-cluster",
                "mode": "cluster",
                "cluster_type": self.cluster_type.pk,
            },
            content_type="application/json",
            **headers,
        )

    def test_api_create_retry_read_only_field_and_token(self) -> None:
        response = self._post()
        self.assertEqual(response.status_code, 201, response.content)
        first_id = response.json()["cluster"]["id"]
        response = self._post()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["cluster"]["id"], first_id)
        self.assertEqual(self._post(read_only=True).status_code, 403)
        serializer = ProxmoxEndpointSerializer(self.endpoint, context={"request": None})
        self.assertTrue(serializer.fields["netbox_cluster"].read_only)

    def test_disabled_endpoint_and_missing_or_wrong_object_permissions_reject_without_writes(
        self,
    ) -> None:
        ProxmoxEndpoint.objects.filter(pk=self.endpoint.pk).update(enabled=False)
        self.assertEqual(self._post().status_code, 403)
        self.assertFalse(Cluster.objects.exists())
        ProxmoxEndpoint.objects.filter(pk=self.endpoint.pk).update(enabled=True)
        user = make_user("scoped")
        self._grant(
            user, ProxmoxEndpoint, ["view", "change"], {"id": self.endpoint.pk + 1000}
        )
        self.assertIn(self._post(user).status_code, (403, 404))
        self.assertFalse(Cluster.objects.exists())

    def test_missing_native_create_or_change_permission_rolls_back(self) -> None:
        user = make_user("no-native-create")
        self._grant(user, ProxmoxEndpoint, ["view", "change"])
        self._grant(user, ClusterType, ["view"])
        self.assertEqual(self._post(user).status_code, 403)
        self.assertFalse(Cluster.objects.exists())
        core, _, _ = self.sync()
        self._grant(user, Cluster, ["view"])
        self.assertEqual(self._post(user).status_code, 403)
        core.refresh_from_db()
        self.assertEqual(core.name, "real-cluster")

    def test_ui_and_api_hide_invisible_related_objects_without_sidecar(self) -> None:
        core, _, _ = self.sync()
        ProxboxClusterSyncState.objects.filter(cluster=core).delete()
        hidden_user = make_user("hidden-core")
        self._grant(hidden_user, ProxmoxEndpoint, ["view"])
        request = RequestFactory().get("/")
        request.user = hidden_user
        self.endpoint.refresh_from_db()
        serializer = ProxmoxEndpointSerializer(
            self.endpoint, context={"request": request}
        )
        self.assertIsNone(serializer.data["netbox_cluster"])
        self.assertIsNone(
            ProxmoxEndpointSerializer(self.endpoint, context={"request": None}).data[
                "netbox_cluster"
            ]
        )
        self.client.force_login(hidden_user)
        response = self.client.get(self.endpoint.get_absolute_url())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotContains(response, core.get_absolute_url())
        extension = ProxmoxClusterTemplateExtension(
            {"object": core, "request": request}
        )
        self.assertIn(self.endpoint.get_absolute_url(), extension.left_page())
        self.assertIn("Source", extension.left_page())
        other_user = make_user("hidden-endpoint")
        request.user = other_user
        self.assertEqual(extension.left_page(), "")


class EndpointClusterBindingReviewTest(EndpointClusterBindingTest):
    """Review regressions for protected authority and stale application objects."""

    def test_stale_endpoint_saves_and_update_fields_preserve_current_authority(
        self,
    ) -> None:
        stale = ProxmoxEndpoint.objects.get(pk=self.endpoint.pk)
        core, _, _ = self.sync()
        stale.name = "ordinary-edit"
        stale.save()
        stale.refresh_from_db()
        self.assertEqual(stale.netbox_cluster_id, core.pk)
        stale_before_delete = ProxmoxEndpoint.objects.get(pk=stale.pk)
        full_save_before_delete = ProxmoxEndpoint.objects.get(pk=stale.pk)
        core.delete()
        full_save_before_delete.name = "full-save-after-native-delete"
        full_save_before_delete.save()
        full_save_before_delete.refresh_from_db()
        self.assertIsNone(full_save_before_delete.netbox_cluster_id)
        stale_before_delete.name = "after-native-delete"
        stale_before_delete.save(update_fields=["name"])
        stale_before_delete.refresh_from_db()
        self.assertIsNone(stale_before_delete.netbox_cluster_id)
        stale_before_delete.netbox_cluster_id = core.pk or 99999
        with self.assertRaises(ValidationError):
            stale_before_delete.save(update_fields=["netbox_cluster"])

    def test_stale_preflight_refreshes_endpoint_and_preserves_tracking_identity(
        self,
    ) -> None:
        stale = ProxmoxEndpoint.objects.get(pk=self.endpoint.pk)
        core, tracking, _ = self.sync()
        record = SimpleNamespace(
            name="preflight-renamed", id="cluster", nodes=1, quorate=1, version=1
        )
        prepared = _sync_cluster_record(
            stale, stale.pk, record, [], "always", "cluster", ClusterSyncResult()
        )
        self.assertEqual(prepared.pk, tracking.pk)
        self.assertEqual(ProxmoxCluster.objects.filter(endpoint=stale).count(), 1)
        self.assertEqual(prepared.netbox_cluster_id, core.pk)

    def test_preflight_refuses_duplicate_linked_and_conflicting_named_rows(
        self,
    ) -> None:
        core, _, _ = self.sync()
        duplicate = ProxmoxCluster(
            endpoint=self.endpoint, netbox_cluster=core, name="duplicate"
        )
        ProxmoxCluster.objects.bulk_create([duplicate])
        record = SimpleNamespace(
            name="new-name", id="cluster", nodes=1, quorate=1, version=1
        )
        with self.assertRaises(ValueError):
            _sync_cluster_record(
                self.endpoint,
                self.endpoint.pk,
                record,
                [],
                "always",
                "cluster",
                ClusterSyncResult(),
            )
        ProxmoxCluster.objects.filter(pk=duplicate.pk).delete()
        ProxmoxCluster.objects.create(endpoint=self.endpoint, name="new-name")
        with self.assertRaises(ValueError):
            _sync_cluster_record(
                self.endpoint,
                self.endpoint.pk,
                record,
                [],
                "always",
                "cluster",
                ClusterSyncResult(),
            )

    def test_ordinary_tracking_claims_cannot_create_endpoint_authority(self) -> None:
        core = Cluster.objects.create(name="unclaimed", type=self.cluster_type)
        with self.assertRaises(ValidationError):
            ProxmoxCluster.objects.create(
                endpoint=self.endpoint, netbox_cluster=core, name="ordinary-claim"
            )
        self.endpoint.refresh_from_db()
        self.assertIsNone(self.endpoint.netbox_cluster_id)
        self.assertFalse(ProxmoxCluster.objects.exists())

    def test_tracking_api_writer_cannot_claim_or_resolve_hidden_references(
        self,
    ) -> None:
        core = Cluster.objects.create(name="api-unclaimed", type=self.cluster_type)
        user = make_user("tracking-only-writer")
        self._grant(user, ProxmoxCluster, ["view", "add", "change"])
        self._grant(user, ProxmoxEndpoint, ["view"], {"id": self.endpoint.pk})
        self._grant(user, Cluster, ["view"], {"id": core.pk})
        _, headers = make_api_token(user)
        path = reverse("plugins-api:netbox_proxbox-api:proxmoxcluster-list")
        body = {
            "endpoint": self.endpoint.pk,
            "netbox_cluster": core.pk,
            "name": "api-claim",
        }
        response = self.client.post(
            path, data=body, content_type="application/json", **headers
        )
        self.assertIn(response.status_code, (400, 403, 409), response.content)
        self.endpoint.refresh_from_db()
        self.assertIsNone(self.endpoint.netbox_cluster_id)
        self.assertFalse(ProxmoxCluster.objects.exists())
        hidden = make_user("tracking-hidden-references")
        self._grant(hidden, ProxmoxCluster, ["view", "add", "change"])
        token, hidden_headers = make_api_token(hidden)
        response = self.client.post(
            path, data=body, content_type="application/json", **hidden_headers
        )
        self.assertEqual(response.status_code, 400, response.content)
        token.write_enabled = False
        token.save(update_fields=["write_enabled"])
        response = self.client.post(
            path, data=body, content_type="application/json", **hidden_headers
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_tracking_metadata_and_clear_do_not_transfer_authority(self) -> None:
        core, tracking, _ = self.sync()
        other = ProxmoxEndpoint.objects.create(name="other-tracking-endpoint")
        tracking.endpoint = other
        with self.assertRaises(ValidationError):
            tracking.save()
        tracking.refresh_from_db()
        tracking.netbox_cluster = None
        tracking.save()
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.netbox_cluster_id, core.pk)
        self.assertIsNone(tracking.netbox_cluster_id)

    def test_action_derives_tracking_and_sidecar_authority_from_exact_endpoint_core_grants(
        self,
    ) -> None:
        user = make_user("derived-action-authority")
        self._grant(user, ProxmoxEndpoint, ["view", "change"], {"id": self.endpoint.pk})
        self._grant(user, ClusterType, ["view"], {"id": self.cluster_type.pk})
        self._grant(user, Cluster, ["view", "add", "change"], {"name": "real-cluster"})
        self._grant(user, ProxboxClusterSyncState, ["view", "change"], {"id": 999999})
        first = self._post(user)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertFalse(first.json()["changed"])
        second = self._post(user)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertFalse(second.json()["changed"])
        self.assertEqual(ProxboxClusterSyncState.objects.count(), 1)

    def test_resulting_core_outside_constrained_grants_rolls_back(self) -> None:
        user = make_user("forbidden-resulting-core")
        self._grant(user, ProxmoxEndpoint, ["view", "change"], {"id": self.endpoint.pk})
        self._grant(user, ClusterType, ["view"])
        self._grant(
            user, Cluster, ["view", "add", "change"], {"name": "permitted-other-name"}
        )
        response = self._post(user)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(Cluster.objects.exists())
        self.assertFalse(ProxmoxCluster.objects.exists())

    def test_request_name_boundary_and_native_change_indicator(self) -> None:
        from netbox_proxbox.api.cluster_binding import ClusterBindingRequestSerializer

        request = SimpleNamespace(user=self.admin)
        serializer = ClusterBindingRequestSerializer(
            data={
                "name": "x" * 100,
                "mode": "cluster",
                "cluster_type": self.cluster_type.pk,
            },
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        core, _, _ = self.sync(name="x" * 100)
        self.assertEqual(len(core.name), 100)
        serializer = ClusterBindingRequestSerializer(
            data={
                "name": "x" * 101,
                "mode": "cluster",
                "cluster_type": self.cluster_type.pk,
            },
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("name", serializer.errors)
        renamed, _, _ = self.sync(name="new-native-name")
        self.assertTrue(renamed._proxbox_binding_changed)
        repeated, _, _ = self.sync(name="new-native-name")
        self.assertFalse(repeated._proxbox_binding_changed)

    def test_ownership_sidecar_writes_preserve_stale_metadata_and_allow_repetition(
        self,
    ) -> None:
        from netbox_proxbox.api.serializers.sync_state import (
            ProxboxClusterSyncStateSerializer,
        )

        core, tracking, _ = self.sync()
        stale = ProxboxClusterSyncState.objects.get(cluster=core)
        wrong = ProxmoxCluster.objects.create(
            endpoint=self.endpoint, name="unlinked-sidecar"
        )
        serializer = ProxboxClusterSyncStateSerializer(
            stale,
            data={"proxmox_cluster": wrong.pk},
            partial=True,
            context={"request": SimpleNamespace(user=self.admin)},
        )
        self.assertFalse(serializer.is_valid())
        serializer = ProxboxClusterSyncStateSerializer(
            stale,
            data={"proxmox_cluster": tracking.pk},
            partial=True,
            context={"request": SimpleNamespace(user=self.admin)},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        stale.proxmox_cluster = wrong
        stale.proxmox_cluster_status = "updated-status"
        stale.save()
        stale.refresh_from_db()
        self.assertEqual(stale.proxmox_cluster_id, tracking.pk)
        self.assertEqual(stale.proxmox_cluster_status, "updated-status")

    def test_disappeared_endpoint_or_native_core_is_a_controlled_conflict(self) -> None:
        with patch(
            "netbox_proxbox.services.cluster_binding.ProxmoxEndpoint.objects.select_for_update"
        ) as locked:
            locked.return_value.get.side_effect = ProxmoxEndpoint.DoesNotExist
            with self.assertRaises(ClusterBindingConflict):
                self.sync()
        self.sync()
        with patch(
            "netbox_proxbox.services.cluster_binding.Cluster.objects.select_for_update"
        ) as locked:
            locked.return_value.get.side_effect = Cluster.DoesNotExist
            with self.assertRaises(ClusterBindingConflict):
                self.sync()


class EndpointClusterBindingMigrationTest(TransactionTestCase):
    """Exercise historical upgrade, retained-column reverse, and reapplication."""

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
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        plugin_leaves = tuple(executor.loader.graph.leaf_nodes("netbox_proxbox"))
        self.assertEqual(len(plugin_leaves), 1)
        self._migrate(plugin_leaves[0])
        super().tearDown()

    def test_historical_upgrade_reverse_and_reapply(self) -> None:
        old = self._migrate(self.before)
        Endpoint = old.get_model("netbox_proxbox", "ProxmoxEndpoint")
        Tracking = old.get_model("netbox_proxbox", "ProxmoxCluster")
        Native = old.get_model("virtualization", "Cluster")
        NativeType = old.get_model("virtualization", "ClusterType")
        native_type = NativeType.objects.create(
            name="migration-native", slug="migration-native"
        )
        endpoints = [
            Endpoint.objects.create(name=f"migration-endpoint-{index}")
            for index in range(6)
        ]
        cores = [
            Native.objects.create(name=f"migration-native-{index}", type=native_type)
            for index in range(5)
        ]
        self.assertNotIn(
            "netbox_cluster", {field.name for field in Endpoint._meta.get_fields()}
        )
        pairs = [(0, 0), (1, 1), (1, 2), (2, 3), (3, 3), (4, 4), (4, 4)]
        for index, (endpoint_index, core_index) in enumerate(pairs):
            Tracking.objects.create(
                endpoint=endpoints[endpoint_index],
                netbox_cluster=cores[core_index],
                name=f"legacy-{index}",
            )
        Tracking.objects.create(endpoint=endpoints[5], name="unlinked")
        upgraded = self._migrate(self.after)
        EndpointAfter = upgraded.get_model("netbox_proxbox", "ProxmoxEndpoint")
        expected = {endpoints[0].pk: cores[0].pk, endpoints[4].pk: cores[4].pk}
        for endpoint in endpoints:
            self.assertEqual(
                EndpointAfter.objects.get(pk=endpoint.pk).netbox_cluster_id,
                expected.get(endpoint.pk),
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            EndpointAfter.objects.filter(pk=endpoints[5].pk).update(
                netbox_cluster_id=cores[0].pk
            )
        reversed_apps = self._migrate(self.before)
        ReversedEndpoint = reversed_apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        self.assertNotIn(
            "netbox_cluster",
            {field.name for field in ReversedEndpoint._meta.get_fields()},
        )
        with connection.cursor() as cursor:
            columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, EndpointAfter._meta.db_table
                )
            }
        self.assertIn("netbox_cluster_id", columns)
        reapplied = self._migrate(self.after).get_model(
            "netbox_proxbox", "ProxmoxEndpoint"
        )
        for endpoint in endpoints:
            self.assertEqual(
                reapplied.objects.get(pk=endpoint.pk).netbox_cluster_id,
                expected.get(endpoint.pk),
            )
        self.assertEqual(reapplied.objects.count(), 6)

    def test_reapply_preserves_retained_owner_after_legacy_tracking_changes(
        self,
    ) -> None:
        old = self._migrate(self.before)
        Endpoint = old.get_model("netbox_proxbox", "ProxmoxEndpoint")
        Tracking = old.get_model("netbox_proxbox", "ProxmoxCluster")
        Native = old.get_model("virtualization", "Cluster")
        NativeType = old.get_model("virtualization", "ClusterType")
        native_type = NativeType.objects.create(
            name="recovery-native", slug="recovery-native"
        )
        owner = Endpoint.objects.create(name="recovery-owner")
        contender = Endpoint.objects.create(name="recovery-contender")
        safe = Endpoint.objects.create(name="recovery-safe")
        retained_core = Native.objects.create(name="retained-core", type=native_type)
        safe_core = Native.objects.create(name="safe-core", type=native_type)
        evidence = Tracking.objects.create(
            endpoint=owner, netbox_cluster=retained_core, name="original-owner"
        )
        upgraded = self._migrate(self.after).get_model(
            "netbox_proxbox", "ProxmoxEndpoint"
        )
        self.assertEqual(
            upgraded.objects.get(pk=owner.pk).netbox_cluster_id, retained_core.pk
        )

        historical = self._migrate(self.before)
        HistoricalTracking = historical.get_model("netbox_proxbox", "ProxmoxCluster")
        HistoricalTracking.objects.filter(pk=evidence.pk).update(netbox_cluster_id=None)
        HistoricalTracking.objects.create(
            endpoint_id=contender.pk,
            netbox_cluster_id=retained_core.pk,
            name="changed-legacy-owner",
        )
        HistoricalTracking.objects.create(
            endpoint_id=safe.pk, netbox_cluster_id=safe_core.pk, name="safe-new-pair"
        )

        reapplied_apps = self._migrate(self.after)
        ReappliedEndpoint = reapplied_apps.get_model(
            "netbox_proxbox", "ProxmoxEndpoint"
        )
        ReappliedTracking = reapplied_apps.get_model("netbox_proxbox", "ProxmoxCluster")
        self.assertEqual(
            ReappliedEndpoint.objects.get(pk=owner.pk).netbox_cluster_id,
            retained_core.pk,
        )
        self.assertIsNone(
            ReappliedEndpoint.objects.get(pk=contender.pk).netbox_cluster_id
        )
        self.assertEqual(
            ReappliedEndpoint.objects.get(pk=safe.pk).netbox_cluster_id, safe_core.pk
        )
        self.assertEqual(ReappliedEndpoint.objects.count(), 3)
        self.assertEqual(ReappliedTracking.objects.count(), 3)
        self.assertIsNone(
            ReappliedTracking.objects.get(pk=evidence.pk).netbox_cluster_id
        )
        self.assertEqual(
            ReappliedTracking.objects.get(endpoint_id=contender.pk).netbox_cluster_id,
            retained_core.pk,
        )


class EndpointClusterBindingConcurrencyTest(TransactionTestCase):
    """Separate PostgreSQL connections exercise the common ownership lock order."""

    def setUp(self) -> None:
        self.admin = make_user("binding-concurrent-admin", is_superuser=True)
        self.native_type = ClusterType.objects.create(
            name="concurrent", slug="concurrent"
        )
        self.endpoint = ProxmoxEndpoint.objects.create(
            name="concurrent-endpoint", domain="concurrent.example.test"
        )
        self.values = {
            "name": "concurrent-cluster",
            "mode": "cluster",
            "cluster_type": self.native_type,
        }

    def _worker(self, barrier: Barrier, *, preflight: bool = False) -> int:
        from django.db import close_old_connections, connections

        close_old_connections()
        try:
            endpoint = ProxmoxEndpoint.objects.get(pk=self.endpoint.pk)
            barrier.wait(timeout=10)
            if preflight:
                record = SimpleNamespace(
                    name=self.values["name"],
                    id="cluster",
                    nodes=1,
                    quorate=1,
                    version=1,
                )
                tracking = _sync_cluster_record(
                    endpoint,
                    endpoint.pk,
                    record,
                    [],
                    "always",
                    "cluster",
                    ClusterSyncResult(),
                )
                return tracking.pk
            user = type(self.admin).objects.get(pk=self.admin.pk)
            core, tracking, _ = synchronize_cluster(endpoint.pk, user, self.values)
            return tracking.pk
        finally:
            connections.close_all()

    def _compete(self, preflight: bool) -> None:
        from concurrent.futures import ThreadPoolExecutor

        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row-lock behavior is required.")
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self._worker, barrier, preflight=preflight),
                pool.submit(self._worker, barrier),
            ]
            results = [future.result(timeout=30) for future in futures]
        self.endpoint.refresh_from_db()
        self.assertEqual(len(set(results)), 1)
        self.assertIsNotNone(self.endpoint.netbox_cluster_id)
        self.assertEqual(
            ProxmoxCluster.objects.filter(endpoint=self.endpoint).count(), 1
        )
        self.assertEqual(
            Cluster.objects.filter(pk=self.endpoint.netbox_cluster_id).count(), 1
        )

    def test_two_atomic_first_claims_converge(self) -> None:
        self._compete(False)

    def test_preflight_and_action_share_one_lock_order(self) -> None:
        self._compete(True)

    def test_preflight_owns_endpoint_before_tracking_while_action_waits(self) -> None:
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from django.db import close_old_connections, connections
        from netbox_proxbox.services import sync_cluster

        synchronize_cluster(self.endpoint.pk, self.admin, self.values)
        reached_tracking = Event()
        action_started = Event()
        original = sync_cluster._select_cluster_tracking

        def gated_selection(endpoint, name) -> ProxmoxCluster | None:
            reached_tracking.set()
            self.assertTrue(action_started.wait(timeout=10))
            return original(endpoint, name)

        def prepare() -> int:
            close_old_connections()
            try:
                record = SimpleNamespace(
                    name=self.values["name"],
                    id="cluster",
                    nodes=1,
                    quorate=1,
                    version=1,
                )
                return _sync_cluster_record(
                    self.endpoint,
                    self.endpoint.pk,
                    record,
                    [],
                    "always",
                    "cluster",
                    ClusterSyncResult(),
                ).pk
            finally:
                connections.close_all()

        def reconcile() -> int:
            close_old_connections()
            try:
                self.assertTrue(reached_tracking.wait(timeout=10))
                action_started.set()
                return synchronize_cluster(self.endpoint.pk, self.admin, self.values)[
                    1
                ].pk
            finally:
                connections.close_all()

        with (
            patch.object(sync_cluster, "_select_cluster_tracking", gated_selection),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first = pool.submit(prepare)
            second = pool.submit(reconcile)
            self.assertEqual(first.result(timeout=30), second.result(timeout=30))

    def test_ordinary_sidecar_writer_cannot_overwrite_action_ownership(self) -> None:
        from concurrent.futures import ThreadPoolExecutor
        from django.db import close_old_connections, connections

        core, tracking, _ = synchronize_cluster(
            self.endpoint.pk, self.admin, self.values
        )
        barrier = Barrier(2)

        def metadata() -> int:
            close_old_connections()
            try:
                sidecar = ProxboxClusterSyncState.objects.get(cluster_id=core.pk)
                sidecar.proxmox_cluster_id = None
                sidecar.proxmox_cluster_status = "ordinary-metadata"
                barrier.wait(timeout=10)
                sidecar.save()
                return sidecar.pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(metadata)
            action = pool.submit(self._worker, barrier)
            writer.result(timeout=30)
            self.assertEqual(action.result(timeout=30), tracking.pk)
        self.assertEqual(
            ProxboxClusterSyncState.objects.get(cluster_id=core.pk).proxmox_cluster_id,
            tracking.pk,
        )
