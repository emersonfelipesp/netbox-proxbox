"""Real-NetBox rendering tests for the data-protection calendars."""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (Path("/opt/netbox/netbox"), REPO_ROOT.parent / "netbox" / "netbox")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import django
except ModuleNotFoundError:
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

if not hasattr(django, "__path__"):
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

for candidate in NETBOX_ROOTS:
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")
try:
    django.setup()
except ModuleNotFoundError as exc:
    if exc.name == "netbox" or (exc.name and exc.name.startswith("netbox.")):
        pytest.skip(
            "NetBox is not importable in this environment.", allow_module_level=True
        )
    raise

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.test import Client, TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils import timezone  # noqa: E402
from users.models import ObjectPermission  # noqa: E402
from virtualization.models import Cluster, ClusterType, VirtualMachine  # noqa: E402

from netbox_proxbox.models import (  # noqa: E402
    BackupRoutine,
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxNode,
    Replication,
    VMBackup,
    VMSnapshot,
)


class DataProtectionCalendarRenderTest(TestCase):
    """Render list and combined views against real models and templates."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_superuser(
            username="data-protection-calendar",
            email="calendar@example.invalid",
            password="test-password",
        )
        cls.vm = VirtualMachine.objects.create(name="calendar-vm", status="active")
        cls.endpoint = ProxmoxEndpoint.objects.create(name="calendar-endpoint")
        cls.now = timezone.now().replace(second=0, microsecond=0)
        VMBackup.objects.create(
            virtual_machine=cls.vm,
            creation_time=cls.now,
            volume_id="calendar-backup",
        )
        VMBackup.objects.create(
            virtual_machine=cls.vm,
            creation_time=None,
            volume_id="undated-backup",
        )
        VMSnapshot.objects.create(
            virtual_machine=cls.vm,
            name="calendar-snapshot",
            vmid=534,
            node="calendar-node",
            snaptime=cls.now,
        )
        Replication.objects.create(
            endpoint=cls.endpoint,
            virtual_machine=cls.vm,
            replication_id="534-1",
            guest=534,
            target="calendar-target",
            jobnum=1,
            schedule="daily 03:00",
        )
        BackupRoutine.objects.create(
            endpoint=cls.endpoint,
            job_id="calendar-routine",
            schedule="daily 04:00",
        )
        cls._create_endpoint_qualified_rows()
        cls._create_permission_users()

    @classmethod
    def _create_endpoint_qualified_rows(cls) -> None:
        cluster_type = ClusterType.objects.create(
            name="calendar-cluster-type",
            slug="calendar-cluster-type",
        )
        first_cluster = Cluster.objects.create(
            name="calendar-native-cluster-a", type=cluster_type
        )
        second_cluster = Cluster.objects.create(
            name="calendar-native-cluster-b", type=cluster_type
        )
        cls.second_endpoint = ProxmoxEndpoint.objects.create(name="calendar-endpoint-b")
        first_proxmox_cluster = ProxmoxCluster.objects.create(
            endpoint=cls.endpoint,
            netbox_cluster=first_cluster,
            name="calendar-proxmox-cluster-a",
        )
        second_proxmox_cluster = ProxmoxCluster.objects.create(
            endpoint=cls.second_endpoint,
            netbox_cluster=second_cluster,
            name="calendar-proxmox-cluster-b",
        )
        cls.first_node = ProxmoxNode.objects.create(
            endpoint=cls.endpoint,
            proxmox_cluster=first_proxmox_cluster,
            name="node1",
            ip_address=".".join(("192", "0", "2", "31")),
        )
        cls.second_node = ProxmoxNode.objects.create(
            endpoint=cls.second_endpoint,
            proxmox_cluster=second_proxmox_cluster,
            name="node1",
            ip_address=".".join(("192", "0", "2", "32")),
        )
        cls.second_endpoint_node2 = ProxmoxNode.objects.create(
            endpoint=cls.second_endpoint,
            proxmox_cluster=second_proxmox_cluster,
            name="node2",
            ip_address=".".join(("192", "0", "2", "33")),
        )
        first_vm = VirtualMachine.objects.create(
            name="calendar-endpoint-vm-a", status="active", cluster=first_cluster
        )
        second_vm = VirtualMachine.objects.create(
            name="calendar-endpoint-vm-b", status="active", cluster=second_cluster
        )
        VMSnapshot.objects.create(
            virtual_machine=first_vm,
            name="first-endpoint-snapshot",
            vmid=535,
            node="node1",
            snaptime=cls.now,
        )
        VMSnapshot.objects.create(
            virtual_machine=second_vm,
            name="second-endpoint-snapshot",
            vmid=536,
            node="node1",
            snaptime=cls.now,
        )
        Replication.objects.create(
            endpoint=cls.endpoint,
            virtual_machine=first_vm,
            replication_id="first-endpoint-replication",
            guest=535,
            target="node1",
            jobnum=2,
            schedule="daily 03:00",
        )
        Replication.objects.create(
            endpoint=cls.second_endpoint,
            virtual_machine=second_vm,
            replication_id="second-endpoint-replication",
            guest=536,
            target="node1",
            jobnum=3,
            schedule="daily 03:00",
        )
        VMSnapshot.objects.create(
            virtual_machine=second_vm,
            name="second-endpoint-node2-snapshot",
            vmid=537,
            node="node2",
            snaptime=cls.now,
        )
        Replication.objects.create(
            endpoint=cls.second_endpoint,
            virtual_machine=second_vm,
            replication_id="second-endpoint-node2-replication",
            guest=537,
            target="node2",
            jobnum=4,
            schedule="daily 03:00",
        )
        BackupRoutine.objects.create(
            endpoint=cls.endpoint,
            job_id="first-endpoint-all-nodes",
            node=None,
            schedule="daily 05:00",
        )
        BackupRoutine.objects.create(
            endpoint=cls.second_endpoint,
            job_id="second-endpoint-all-nodes",
            node=None,
            schedule="daily 05:00",
        )

    @classmethod
    def _grant_view(
        cls, user: object, model: type, *, constraints: dict[str, str] | None = None
    ) -> None:
        permission = ObjectPermission.objects.create(
            name=f"Calendar view {model._meta.label} for {user.username}",
            actions=["view"],
            constraints=constraints,
        )
        permission.object_types.add(ContentType.objects.get_for_model(model))
        permission.users.add(user)

    @classmethod
    def _create_permission_users(cls) -> None:
        user_model = get_user_model()
        cls.backup_only_user = user_model.objects.create_user(
            username="calendar-backup-only"
        )
        cls._grant_view(cls.backup_only_user, VMBackup)
        cls.constrained_backup_user = user_model.objects.create_user(
            username="calendar-constrained-backup"
        )
        cls._grant_view(
            cls.constrained_backup_user,
            VMBackup,
            constraints={"volume_id": "calendar-backup"},
        )
        cls.no_permission_user = user_model.objects.create_user(
            username="calendar-no-permissions"
        )
        cls.snapshot_only_user = user_model.objects.create_user(
            username="calendar-snapshot-only"
        )
        cls._grant_view(cls.snapshot_only_user, VMSnapshot)

    def setUp(self) -> None:
        self.client = Client()
        self.client.force_login(self.user)
        self.anchor = timezone.localtime(self.now).date().isoformat()

    def test_all_four_list_pages_render_calendar_before_object_list(self) -> None:
        names = (
            "vmbackup_list",
            "vmsnapshot_list",
            "replication_list",
            "backuproutine_list",
        )
        for name in names:
            with self.subTest(name=name):
                response = self.client.get(
                    reverse(f"plugins:netbox_proxbox:{name}"),
                    {"cal_date": self.anchor},
                )
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assertIn("data-protection-calendar", html)
                self.assertLess(
                    html.index("data-protection-calendar"),
                    html.index('id="object_list"'),
                )

    def test_combined_page_renders_all_four_kinds_and_undated_notice(self) -> None:
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {"cal_date": self.anchor},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "calendar-vm — calendar-backup")
        self.assertContains(response, "calendar-vm — calendar-snapshot")
        self.assertContains(response, "534-1")
        self.assertContains(response, "calendar-routine")
        self.assertContains(response, "visible record has no date")

    def test_week_navigation_preserves_filters_and_changes_the_visible_range(
        self,
    ) -> None:
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {
                "cal_view": "week",
                "cal_date": self.anchor,
                "virtual_machine": self.vm.pk,
                "per_page": 100,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cal_view=week")
        self.assertContains(response, f"virtual_machine={self.vm.pk}")
        self.assertContains(response, "per_page=100")
        calendar = response.context["calendar"]
        self.assertEqual(calendar["view"], "week")
        self.assertEqual(len(calendar["rows"]), 1)
        self.assertIn("cal_date=", calendar["prev_query"])
        self.assertIn("cal_date=", calendar["next_query"])

    def test_invalid_calendar_state_falls_back_without_error(self) -> None:
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {"cal_view": "agenda", "cal_date": "not-a-date"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["calendar"]["view"], "month")
        self.assertEqual(response.context["calendar"]["anchor"], timezone.localdate())

    def test_month_next_navigation_crosses_the_year_boundary(self) -> None:
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {"cal_view": "month", "cal_date": "2026-12-15"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("cal_date=2027-01-15", response.context["calendar"]["next_query"])
        self.assertNotEqual(
            response.context["calendar"]["next_query"],
            response.context["calendar"]["prev_query"],
        )

    def test_week_next_moves_exactly_seven_days(self) -> None:
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {"cal_view": "week", "cal_date": self.anchor},
        )

        expected = (timezone.localtime(self.now).date() + timedelta(days=7)).isoformat()
        self.assertIn(
            f"cal_date={expected}", response.context["calendar"]["next_query"]
        )

    def test_date_from_filter_anchors_the_calendar_when_cal_date_is_absent(
        self,
    ) -> None:
        params = {
            "cluster": "",
            "node": "",
            "virtual_machine": "",
            "date_from": "2025-03-05",
            "date_to": "2025-03-20",
            "kinds_submitted": "1",
            "backups": "on",
            "snapshots": "on",
            "replications": "on",
            "routines": "on",
            "cal_view": "month",
        }
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            params,
        )

        self.assertEqual(response.status_code, 200)
        calendar = response.context["calendar"]
        self.assertEqual(calendar["anchor"], timezone.datetime(2025, 3, 5).date())
        self.assertEqual(calendar["title"], "March 2025")
        self.assertEqual(response.context["event_rows_limit"], 500)
        self.assertLessEqual(
            len(response.context["event_rows"]), response.context["event_rows_total"]
        )

    def test_stale_cal_date_outside_range_reanchors_to_date_from(self) -> None:
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {
                "date_from": "2025-03-05",
                "date_to": "2025-03-20",
                "cal_date": "2024-01-10",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["calendar"]["title"], "March 2025")

    def test_explicit_cal_date_inside_range_remains_authoritative(self) -> None:
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {
                "date_from": "2025-03-05",
                "date_to": "2025-04-20",
                "cal_date": "2025-04-10",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["calendar"]["title"], "April 2025")

    def test_node_name_fallbacks_are_endpoint_and_cluster_qualified(self) -> None:
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {"node": self.first_node.pk, "cal_date": self.anchor},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "first-endpoint-snapshot")
        self.assertNotContains(response, "second-endpoint-snapshot")
        self.assertContains(response, "first-endpoint-replication")
        self.assertNotContains(response, "second-endpoint-replication")
        self.assertContains(response, "first-endpoint-all-nodes")
        self.assertNotContains(response, "second-endpoint-all-nodes")

    def test_multi_node_selection_keeps_each_node_paired_with_its_endpoint(
        self,
    ) -> None:
        # node1 on endpoint A plus node2 on endpoint B: the second endpoint's
        # own node1 rows must stay excluded even though "node1" is selected.
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {
                "node": [self.first_node.pk, self.second_endpoint_node2.pk],
                "cal_date": self.anchor,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "first-endpoint-snapshot")
        self.assertContains(response, "second-endpoint-node2-snapshot")
        self.assertNotContains(response, "second-endpoint-snapshot")
        self.assertContains(response, "first-endpoint-replication")
        self.assertContains(response, "second-endpoint-node2-replication")
        self.assertNotContains(response, "second-endpoint-replication")
        self.assertContains(response, "first-endpoint-all-nodes")
        self.assertContains(response, "second-endpoint-all-nodes")

    def test_boundary_year_date_ranges_render_instead_of_raising(self) -> None:
        for view, date_from, date_to in (
            ("month", "0001-01-05", "0001-01-20"),
            ("week", "0001-01-05", "0001-01-20"),
            ("month", "9999-12-05", "9999-12-20"),
            ("week", "9999-12-05", "9999-12-20"),
        ):
            with self.subTest(view=view, date_from=date_from):
                response = self.client.get(
                    reverse("plugins:netbox_proxbox:data_protection"),
                    {"cal_view": view, "date_from": date_from, "date_to": date_to},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.context["calendar"]["anchor"], timezone.localdate()
                )

    def test_active_schedules_win_the_event_budget_over_stale_ones(self) -> None:
        stale = BackupRoutine.objects.create(
            endpoint=self.endpoint,
            job_id="budget-stale-routine",
            schedule="daily 01:00",
            status="stale",
        )
        active = BackupRoutine.objects.create(
            endpoint=self.endpoint,
            job_id="budget-newest-active-routine",
            schedule="daily 02:00",
        )
        self.assertLess(stale.pk, active.pk)
        with patch("netbox_proxbox.views.data_protection.CALENDAR_SOURCE_LIMIT", 7):
            response = self.client.get(
                reverse("plugins:netbox_proxbox:backuproutine_list"),
                {"cal_view": "week", "cal_date": self.anchor, "q": "budget-"},
            )

        self.assertEqual(response.status_code, 200)
        labels = [
            event.label
            for row in response.context["calendar"]["rows"]
            for cell in row
            for event in cell.events + cell.overflow
        ]
        self.assertIn("budget-newest-active-routine", labels)
        self.assertNotIn("budget-stale-routine", labels)

    def test_timestamp_source_limit_reports_omitted_events(self) -> None:
        VMBackup.objects.create(
            virtual_machine=self.vm,
            creation_time=self.now + timedelta(minutes=1),
            volume_id="calendar-limit-two",
        )
        VMBackup.objects.create(
            virtual_machine=self.vm,
            creation_time=self.now + timedelta(minutes=2),
            volume_id="calendar-limit-three",
        )
        with patch("netbox_proxbox.views.data_protection.CALENDAR_SOURCE_LIMIT", 2):
            response = self.client.get(
                reverse("plugins:netbox_proxbox:vmbackup_list"),
                {"cal_date": self.anchor},
            )

        self.assertEqual(response.status_code, 200)
        truncation = response.context["calendar"]["truncation"]
        self.assertTrue(truncation.more_rows)
        self.assertEqual(truncation.omitted_events, 0)
        self.assertContains(response, "Rendering limit reached.")
        self.assertContains(response, "Further records exist beyond the first 2")

    def test_schedule_source_limit_reports_unprojected_objects(self) -> None:
        # Three daily routines project seven events each in the week view. A
        # ten-event limit is filled by the first routine plus three occurrences
        # of the second, so four occurrences are omitted and the third routine
        # is never projected; both are reported in their own units.
        with patch("netbox_proxbox.views.data_protection.CALENDAR_SOURCE_LIMIT", 10):
            response = self.client.get(
                reverse("plugins:netbox_proxbox:backuproutine_list"),
                {"cal_view": "week", "cal_date": self.anchor},
            )

        self.assertEqual(response.status_code, 200)
        truncation = response.context["calendar"]["truncation"]
        self.assertEqual(truncation.omitted_events, 4)
        self.assertEqual(truncation.unprojected_objects, 1)
        self.assertFalse(truncation.more_rows)
        self.assertContains(response, "4 projected schedule occurrences")
        self.assertContains(response, "1 scheduled objects were not projected")

    def test_backup_only_permission_hides_every_other_kind(self) -> None:
        self.client.force_login(self.backup_only_user)
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {"cal_date": self.anchor},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "calendar-vm — calendar-backup")
        self.assertNotContains(response, "calendar-snapshot")
        self.assertNotContains(response, "534-1")
        self.assertNotContains(response, "calendar-routine")

    def test_constrained_backup_permission_excludes_undated_row_everywhere(
        self,
    ) -> None:
        self.client.force_login(self.constrained_backup_user)
        combined = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {"cal_date": self.anchor},
        )
        backup_list = self.client.get(
            reverse("plugins:netbox_proxbox:vmbackup_list"),
            {"cal_date": self.anchor},
        )

        for response in (combined, backup_list):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "calendar-vm — calendar-backup")
            self.assertNotContains(response, "undated-backup")
            self.assertNotContains(response, "visible record has no date")
            self.assertEqual(response.context["calendar"]["undated_count"], 0)

    def test_no_permissions_render_empty_sources_and_filter_choices(self) -> None:
        self.client.force_login(self.no_permission_user)
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {"cal_date": self.anchor},
        )

        self.assertEqual(response.status_code, 200)
        for label in (
            "calendar-backup",
            "calendar-snapshot",
            "534-1",
            "calendar-routine",
        ):
            self.assertNotContains(response, label)
        form = response.context["filter_form"]
        for field in ("cluster", "node", "virtual_machine"):
            self.assertFalse(form.fields[field].queryset.exists())

    def test_snapshot_permission_does_not_imply_cluster_choice_permission(
        self,
    ) -> None:
        self.client.force_login(self.snapshot_only_user)
        response = self.client.get(
            reverse("plugins:netbox_proxbox:data_protection"),
            {"cal_date": self.anchor},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "calendar-vm — calendar-snapshot")
        self.assertNotContains(response, "calendar-backup")
        self.assertNotContains(response, "534-1")
        self.assertNotContains(response, "calendar-routine")
        self.assertFalse(
            response.context["filter_form"].fields["cluster"].queryset.exists()
        )
