"""Runtime contracts for Proxbox bridge discovery and scheduling dispatch."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
except ModuleNotFoundError:
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - depends on external test services
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import TestCase, override_settings  # noqa: E402

from netbox_proxbox.api.mcp_bridge import (  # noqa: E402
    INTERVAL_UNIT_VALUES,
    SYNC_TYPE_VALUES,
    build_mcp_bridge_manifest,
)
from netbox_proxbox.choices import (  # noqa: E402
    ScheduleIntervalUnitChoices,
    SyncTypeChoices,
)
from netbox_proxbox.models import ProxmoxEndpoint  # noqa: E402
from netbox_proxbox.api.serializers import (  # noqa: E402
    ScheduleSyncRequestSerializer,
    ScheduledJobSerializer,
)


ROOT_URL = "/api/plugins/proxbox/"
MANIFEST_URL = "/api/plugins/proxbox/mcp/"
SCHEDULE_URL = "/api/plugins/proxbox/sync/schedule/"


class MCPBridgeRuntimeTest(TestCase):
    """Exercise the real DRF routes and their existing permission boundary."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.operator = get_user_model().objects.create_user(
            username="mcp-bridge-operator",
            is_staff=True,
            is_superuser=True,
        )
        cls.bystander = get_user_model().objects.create_user(
            username="mcp-bridge-bystander",
            is_staff=True,
        )
        cls.enabled_endpoint = ProxmoxEndpoint.objects.create(
            name="mcp-enabled",
            domain="mcp-enabled.example.test",
            enabled=True,
        )
        cls.disabled_endpoint = ProxmoxEndpoint.objects.create(
            name="mcp-disabled",
            domain="mcp-disabled.example.test",
            enabled=False,
        )

    def setUp(self) -> None:
        self.client.force_login(self.operator)

    def _post_schedule(self, payload: dict[str, object]):
        return self.client.post(
            SCHEDULE_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_root_and_manifest_routes_render_bridge_contract(self) -> None:
        root_response = self.client.get(ROOT_URL)
        self.assertEqual(root_response.status_code, 200, root_response.content)
        self.assertEqual(
            root_response.json()["mcp"],
            {
                "schema_version": "1",
                "manifest": "http://testserver/api/plugins/proxbox/mcp/",
            },
        )

        manifest_response = self.client.get(MANIFEST_URL)
        self.assertEqual(manifest_response.status_code, 200, manifest_response.content)
        self.assertEqual(manifest_response.json(), build_mcp_bridge_manifest())

    @override_settings(LOGIN_REQUIRED=True)
    def test_manifest_requires_authentication_when_netbox_does(self) -> None:
        self.client.logout()
        response = self.client.get(MANIFEST_URL)
        self.assertIn(response.status_code, (401, 403))

    def test_schedule_endpoint_preserves_core_add_job_permission(self) -> None:
        self.client.force_login(self.bystander)
        get_response = self.client.get(SCHEDULE_URL)
        post_response = self._post_schedule({"sync_types": ["all"]})
        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)

    def test_list_sync_jobs_returns_existing_envelope(self) -> None:
        scheduled_jobs = [
            {
                "id": 7,
                "pk": 7,
                "name": "nightly",
                "sync_types": ["all"],
                "schedule": None,
                "interval": 1440,
                "status": "scheduled",
            }
        ]
        with patch(
            "netbox_proxbox.views.schedule_helpers.get_scheduled_jobs_list",
            return_value=scheduled_jobs,
        ):
            response = self.client.get(SCHEDULE_URL)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(), {"count": 1, "scheduled_jobs": scheduled_jobs}
        )

    def test_schedule_sync_enqueues_only_an_enabled_requested_scope(self) -> None:
        with patch(
            "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
            return_value=SimpleNamespace(pk=29),
        ) as enqueue:
            response = self._post_schedule(
                {
                    "sync_types": ["virtual-machines"],
                    "proxmox_endpoint_ids": [self.enabled_endpoint.pk],
                }
            )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["job_id"], 29)
        self.assertEqual(
            enqueue.call_args.kwargs["proxmox_endpoint_ids"],
            [str(self.enabled_endpoint.pk)],
        )

    def test_schedule_sync_rejects_any_unavailable_requested_endpoint(self) -> None:
        unavailable_id = self.disabled_endpoint.pk + 100_000
        with patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue:
            disabled_response = self._post_schedule(
                {
                    "sync_types": ["virtual-machines"],
                    "proxmox_endpoint_ids": [
                        self.enabled_endpoint.pk,
                        self.disabled_endpoint.pk,
                    ],
                }
            )
            unknown_response = self._post_schedule(
                {
                    "sync_types": ["virtual-machines"],
                    "proxmox_endpoint_ids": [unavailable_id],
                }
            )

        self.assertEqual(disabled_response.status_code, 400)
        self.assertEqual(unknown_response.status_code, 400)
        self.assertEqual(
            disabled_response.json()["errors"]["proxmox_endpoint_ids"],
            [f"Unknown or disabled endpoint ID(s): [{self.disabled_endpoint.pk}]"],
        )
        self.assertEqual(
            unknown_response.json()["errors"]["proxmox_endpoint_ids"],
            [f"Unknown or disabled endpoint ID(s): [{unavailable_id}]"],
        )
        enqueue.assert_not_called()

    def test_schedule_sync_rejects_explicit_empty_endpoint_scopes(self) -> None:
        with patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue:
            proxmox_response = self._post_schedule(
                {"sync_types": ["all"], "proxmox_endpoint_ids": []}
            )
            netbox_response = self._post_schedule(
                {"sync_types": ["all"], "netbox_endpoint_ids": []}
            )

        self.assertEqual(proxmox_response.status_code, 400)
        self.assertEqual(netbox_response.status_code, 400)
        self.assertIn("proxmox_endpoint_ids", proxmox_response.json()["errors"])
        self.assertIn("netbox_endpoint_ids", netbox_response.json()["errors"])
        enqueue.assert_not_called()

    def test_schedule_sync_rejects_incomplete_recurrence(self) -> None:
        with patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue:
            value_only = self._post_schedule(
                {"sync_types": ["all"], "interval_value": 2}
            )
            unit_only = self._post_schedule(
                {"sync_types": ["all"], "interval_unit": "hours"}
            )

        self.assertEqual(value_only.status_code, 400)
        self.assertEqual(unit_only.status_code, 400)
        self.assertIn("interval_unit", value_only.json()["errors"])
        self.assertIn("interval_value", unit_only.json()["errors"])
        enqueue.assert_not_called()

    def test_schedule_sync_rejects_invalid_type_and_all_combination(self) -> None:
        with patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue:
            invalid_response = self._post_schedule({"sync_types": ["not-real"]})
            all_response = self._post_schedule(
                {"sync_types": ["all", "virtual-machines"]}
            )

        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(all_response.status_code, 400)
        enqueue.assert_not_called()

    def test_manifest_choice_values_match_runtime_choices(self) -> None:
        self.assertEqual(
            SYNC_TYPE_VALUES, [choice[0] for choice in SyncTypeChoices.CHOICES]
        )
        self.assertEqual(
            INTERVAL_UNIT_VALUES,
            [choice[0] for choice in ScheduleIntervalUnitChoices.CHOICES],
        )
        request_serializer = ScheduleSyncRequestSerializer()
        self.assertEqual(
            list(request_serializer.fields["sync_types"].child.choices),
            SYNC_TYPE_VALUES,
        )
        self.assertEqual(
            list(request_serializer.fields["interval_unit"].choices),
            INTERVAL_UNIT_VALUES,
        )

    def test_manifest_job_envelope_matches_runtime_response_serializer(self) -> None:
        manifest = build_mcp_bridge_manifest()
        list_tool = next(
            tool for tool in manifest["tools"] if tool["name"] == "list_sync_jobs"
        )
        required = set(
            list_tool["outputSchema"]["properties"]["scheduled_jobs"]["items"][
                "required"
            ]
        )

        self.assertEqual(required, set(ScheduledJobSerializer().fields))
