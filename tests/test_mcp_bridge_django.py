"""Runtime contracts for Proxbox bridge discovery and scheduling dispatch."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
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
    INTERVAL_VALUE_MAXIMUMS,
    MAX_EXACT_JSON_FLOAT_INTEGER,
    MAX_POSITIVE_SIGNED_64_BIT_INTEGER,
    MAX_PERSISTED_INTERVAL_MINUTES,
    SYNC_TYPE_VALUES,
    build_mcp_bridge_manifest,
    mcp_bridge_activation_record,
)
from netbox_proxbox.choices import (  # noqa: E402
    ScheduleIntervalUnitChoices,
    SyncTypeChoices,
)
from netbox_proxbox.models import NetBoxEndpoint, ProxmoxEndpoint  # noqa: E402
from netbox_proxbox.api.serializers import (  # noqa: E402
    ScheduleSyncRequestSerializer,
    ScheduledJobSerializer,
)
from tests.mcp_bridge_examples import load_mcp_guide_examples  # noqa: E402

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
            pk=7,
            name="mcp-enabled",
            domain="mcp-enabled.example.test",
            enabled=True,
        )
        cls.second_enabled_endpoint = ProxmoxEndpoint.objects.create(
            pk=9,
            name="mcp-enabled-second",
            domain="mcp-enabled-second.example.test",
            enabled=True,
        )
        cls.disabled_endpoint = ProxmoxEndpoint.objects.create(
            pk=10,
            name="mcp-disabled",
            domain="mcp-disabled.example.test",
            enabled=False,
        )
        cls.netbox_endpoint = NetBoxEndpoint.objects.create(
            pk=3,
            name="mcp-netbox",
            domain="mcp-netbox.example.test",
            enabled=True,
        )

    def setUp(self) -> None:
        self.client.force_login(self.operator)

    def _post_schedule(self, payload: dict[str, object]):
        return self.client.post(
            SCHEDULE_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _post_schedule_json(self, payload: str):
        """Post an exact JSON spelling without Python float re-serialization."""
        return self.client.post(
            SCHEDULE_URL,
            data=payload,
            content_type="application/json",
        )

    def test_root_and_manifest_routes_fail_closed_until_sdk_activation(self) -> None:
        root_response = self.client.get(ROOT_URL)
        self.assertEqual(root_response.status_code, 200, root_response.content)
        self.assertNotIn("mcp", root_response.json())

        manifest_response = self.client.get(MANIFEST_URL)
        self.assertEqual(manifest_response.status_code, 503, manifest_response.content)
        self.assertEqual(
            manifest_response.json(),
            {
                "detail": "The semantic MCP consumer bridge is not activated.",
                "activation": mcp_bridge_activation_record(),
            },
        )

    def test_blocked_manifest_route_is_get_only_and_does_not_require_add_job(
        self,
    ) -> None:
        self.client.force_login(self.bystander)
        get_response = self.client.get(MANIFEST_URL)
        post_response = self.client.post(MANIFEST_URL, data={})

        self.assertEqual(get_response.status_code, 503, get_response.content)
        self.assertEqual(
            get_response.json()["activation"], mcp_bridge_activation_record()
        )
        self.assertEqual(post_response.status_code, 405, post_response.content)

    @override_settings(LOGIN_REQUIRED=True)
    def test_manifest_requires_authentication_when_netbox_does(self) -> None:
        self.client.logout()
        response = self.client.get(MANIFEST_URL)
        self.assertIn(response.status_code, (401, 403))

    @override_settings(LOGIN_REQUIRED=False)
    def test_manifest_allows_anonymous_activation_check_when_netbox_does(self) -> None:
        self.client.logout()
        response = self.client.get(MANIFEST_URL)

        self.assertEqual(response.status_code, 503, response.content)
        self.assertEqual(response.json()["activation"], mcp_bridge_activation_record())

    def test_schedule_endpoint_preserves_core_add_job_permission(self) -> None:
        self.client.force_login(self.bystander)
        get_response = self.client.get(SCHEDULE_URL)
        post_response = self._post_schedule({"sync_types": ["all"]})
        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)

    def test_permission_denial_precedes_validation_identity_and_enqueue(self) -> None:
        self.client.force_login(self.bystander)
        with (
            patch(
                "netbox_proxbox.api.views.models.ProxmoxEndpoint.objects.filter",
                side_effect=AssertionError("endpoint identity lookup must not run"),
            ) as endpoint_lookup,
            patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue,
        ):
            response = self._post_schedule(
                {
                    "sync_stages": ["not-a-stage"],
                    "proxmox_endpoint_ids": [999],
                }
            )
        self.assertEqual(response.status_code, 403, response.content)
        endpoint_lookup.assert_not_called()
        enqueue.assert_not_called()

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

    def test_documented_list_response_round_trips_through_runtime_serializer(
        self,
    ) -> None:
        documented = load_mcp_guide_examples()["list-sync-jobs-output"]
        self.assertIsInstance(documented, dict)
        documented_body = documented["body"]
        runtime_row = dict(documented_body["scheduled_jobs"][0])
        runtime_row["schedule"] = datetime.fromisoformat(
            runtime_row["schedule"].replace("Z", "+00:00")
        )
        with patch(
            "netbox_proxbox.views.schedule_helpers.get_scheduled_jobs_list",
            return_value=[runtime_row],
        ):
            response = self.client.get(SCHEDULE_URL)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), documented_body)

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

    def test_documented_immediate_request_enqueues_with_omitted_scopes(self) -> None:
        payload = load_mcp_guide_examples()["schedule-immediate-input"]["arguments"]
        expected_response = load_mcp_guide_examples()["schedule-sync-output"]["body"]
        self.assertIsInstance(payload, dict)
        with patch(
            "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
            return_value=SimpleNamespace(pk=314),
        ) as enqueue:
            response = self._post_schedule(payload)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json(), expected_response)
        self.assertEqual(enqueue.call_args.kwargs["sync_types"], [SyncTypeChoices.ALL])
        self.assertEqual(
            enqueue.call_args.kwargs["name"], "operator-requested-full-sync"
        )
        self.assertEqual(enqueue.call_args.kwargs["proxmox_endpoint_ids"], [])
        self.assertEqual(enqueue.call_args.kwargs["netbox_endpoint_ids"], [])
        self.assertIsNone(enqueue.call_args.kwargs["schedule_at"])
        self.assertIsNone(enqueue.call_args.kwargs["interval"])

    def test_documented_future_request_preserves_scope_time_and_name(self) -> None:
        payload = load_mcp_guide_examples()["schedule-future-scoped-input"]["arguments"]
        self.assertIsInstance(payload, dict)
        with patch(
            "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
            return_value=SimpleNamespace(pk=315),
        ) as enqueue:
            response = self._post_schedule(payload)

        self.assertEqual(response.status_code, 201, response.content)
        kwargs = enqueue.call_args.kwargs
        self.assertEqual(kwargs["sync_types"], ["virtual-machines", "storage"])
        self.assertEqual(kwargs["name"], "maintenance-window-inventory")
        self.assertEqual(kwargs["schedule_at"].isoformat(), "2099-01-15T03:00:00+00:00")
        self.assertIsNone(kwargs["interval"])
        self.assertEqual(kwargs["proxmox_endpoint_ids"], ["7", "9"])
        self.assertEqual(kwargs["netbox_endpoint_ids"], [])

    def test_documented_recurring_request_converts_interval_and_sets_first_run(
        self,
    ) -> None:
        payload = load_mcp_guide_examples()["schedule-recurring-input"]["arguments"]
        self.assertIsInstance(payload, dict)
        server_now = datetime(2098, 12, 1, 12, 30, tzinfo=timezone.utc)
        with (
            patch("utilities.datetime.local_now", return_value=server_now),
            patch(
                "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
                return_value=SimpleNamespace(pk=316),
            ) as enqueue,
        ):
            response = self._post_schedule(payload)

        self.assertEqual(response.status_code, 201, response.content)
        kwargs = enqueue.call_args.kwargs
        self.assertEqual(kwargs["sync_types"], ["devices", "network-interfaces"])
        self.assertEqual(kwargs["name"], "six-hour-inventory")
        self.assertEqual(kwargs["interval"], 360)
        self.assertEqual(kwargs["schedule_at"], server_now)
        self.assertEqual(kwargs["proxmox_endpoint_ids"], ["7"])
        self.assertEqual(kwargs["netbox_endpoint_ids"], [])

    def test_sdk_valid_integral_json_numbers_normalize_before_dispatch(self) -> None:
        server_now = datetime(2098, 12, 1, 12, 30, tzinfo=timezone.utc)
        with (
            patch("utilities.datetime.local_now", return_value=server_now),
            patch(
                "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
                return_value=SimpleNamespace(pk=317),
            ) as enqueue,
        ):
            response = self._post_schedule(
                {
                    "sync_stages": ["storage"],
                    "recurrence": {"hours": 6.0},
                    "proxmox_endpoint_ids": [7.0],
                }
            )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(enqueue.call_args.kwargs["interval"], 360)
        self.assertIsInstance(enqueue.call_args.kwargs["interval"], int)
        self.assertEqual(enqueue.call_args.kwargs["proxmox_endpoint_ids"], ["7"])

    def test_largest_exact_integral_json_float_preserves_endpoint_identity(
        self,
    ) -> None:
        class MatchingEndpointIDs:
            def values_list(self, *args, **kwargs):
                return [MAX_EXACT_JSON_FLOAT_INTEGER]

        with (
            patch(
                "netbox_proxbox.api.views.models.ProxmoxEndpoint.objects.filter",
                return_value=MatchingEndpointIDs(),
            ) as endpoint_lookup,
            patch(
                "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
                return_value=SimpleNamespace(pk=3171),
            ) as enqueue,
        ):
            response = self._post_schedule_json(
                '{"sync_stages":["storage"],'
                f'"proxmox_endpoint_ids":[{MAX_EXACT_JSON_FLOAT_INTEGER}.0]}}'
            )

        self.assertEqual(response.status_code, 201, response.content)
        endpoint_lookup.assert_called_once_with(
            pk__in=[MAX_EXACT_JSON_FLOAT_INTEGER], enabled=True
        )
        self.assertEqual(
            enqueue.call_args.kwargs["proxmox_endpoint_ids"],
            [str(MAX_EXACT_JSON_FLOAT_INTEGER)],
        )

    def test_unsafe_integral_json_floats_reject_before_identity_or_enqueue(
        self,
    ) -> None:
        for token in ("9007199254740992.0", "9007199254740993.0"):
            with self.subTest(token=token):
                with (
                    patch(
                        "netbox_proxbox.api.views.models.ProxmoxEndpoint.objects.filter",
                        side_effect=AssertionError("unsafe float reached the ORM"),
                    ) as endpoint_lookup,
                    patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue,
                ):
                    response = self._post_schedule_json(
                        '{"sync_stages":["storage"],'
                        f'"proxmox_endpoint_ids":[{token}]}}'
                    )

                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("proxmox_endpoint_ids", response.json()["errors"])
                endpoint_lookup.assert_not_called()
                enqueue.assert_not_called()

    def test_decimal_integral_values_share_the_lossless_safe_range(self) -> None:
        accepted = ScheduleSyncRequestSerializer(
            data={
                "sync_stages": ["storage"],
                "proxmox_endpoint_ids": [Decimal(MAX_EXACT_JSON_FLOAT_INTEGER)],
            }
        )
        rejected = ScheduleSyncRequestSerializer(
            data={
                "sync_stages": ["storage"],
                "proxmox_endpoint_ids": [Decimal(MAX_EXACT_JSON_FLOAT_INTEGER + 1)],
            }
        )

        self.assertTrue(accepted.is_valid(), accepted.errors)
        self.assertEqual(
            accepted.validated_data["proxmox_endpoint_ids"],
            [MAX_EXACT_JSON_FLOAT_INTEGER],
        )
        self.assertFalse(rejected.is_valid())
        self.assertIn("proxmox_endpoint_ids", rejected.errors)

    def test_exact_full_stage_set_canonicalizes_for_recurring_job_identity(
        self,
    ) -> None:
        server_now = datetime(2098, 12, 1, 12, 30, tzinfo=timezone.utc)
        with (
            patch("utilities.datetime.local_now", return_value=server_now),
            patch(
                "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
                return_value=SimpleNamespace(pk=318),
            ) as enqueue,
        ):
            response = self._post_schedule(
                {
                    "sync_stages": list(reversed(SYNC_TYPE_VALUES)),
                    "recurrence": {"days": 1},
                }
            )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(enqueue.call_args.kwargs["sync_types"], [SyncTypeChoices.ALL])
        self.assertEqual(enqueue.call_args.kwargs["interval"], 1440)

    def test_incomplete_concrete_stage_set_remains_explicit(self) -> None:
        subset = SYNC_TYPE_VALUES[:-1]
        with patch(
            "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
            return_value=SimpleNamespace(pk=319),
        ) as enqueue:
            response = self._post_schedule({"sync_stages": subset})

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(enqueue.call_args.kwargs["sync_types"], subset)

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

    def test_bridge_rejects_schema_mutations_without_enqueue(self) -> None:
        base = {"sync_stages": ["virtual-machines"]}
        invalid_requests = (
            ("legacy all sentinel", {"sync_stages": ["all"]}),
            (
                "mixed bridge and REST discriminators",
                {**base, "sync_types": ["virtual-machines"]},
            ),
            ("unimplemented NetBox scope", {**base, "netbox_endpoint_ids": [3]}),
            ("legacy recurrence value", {**base, "interval_value": 2}),
            ("legacy recurrence unit", {**base, "interval_unit": "hours"}),
            (
                "legacy discriminator with bridge recurrence",
                {"sync_types": ["all"], "recurrence": {"hours": 1}},
            ),
            ("empty recurrence", {**base, "recurrence": {}}),
            (
                "two recurrence units",
                {**base, "recurrence": {"hours": 1, "minutes": 2}},
            ),
            ("unknown recurrence unit", {**base, "recurrence": {"months": 1}}),
            ("boolean recurrence", {**base, "recurrence": {"hours": True}}),
            ("nonintegral recurrence", {**base, "recurrence": {"hours": 1.5}}),
            (
                "nonintegral endpoint",
                {**base, "proxmox_endpoint_ids": [7.5]},
            ),
            (
                "numerically duplicate endpoints",
                {**base, "proxmox_endpoint_ids": [7, 7.0]},
            ),
            ("string endpoint", {**base, "proxmox_endpoint_ids": ["7"]}),
            (
                "converted recurrence overflow",
                {
                    **base,
                    "recurrence": {"weeks": INTERVAL_VALUE_MAXIMUMS["weeks"] + 1},
                },
            ),
            (
                "duplicate bridge stages",
                {"sync_stages": ["storage", "storage"]},
            ),
            (
                "timezone-less schedule",
                {**base, "schedule_at": "2099-01-15T03:00:00"},
            ),
            (
                "invalid calendar date",
                {**base, "schedule_at": "2099-02-30T03:00:00Z"},
            ),
            (
                "invalid timezone offset",
                {**base, "schedule_at": "2099-01-15T03:00:00+24:00"},
            ),
            ("non-string schedule", {**base, "schedule_at": True}),
            ("missing discriminator", {"job_name": "not-enough"}),
        )
        for label, payload in invalid_requests:
            with self.subTest(label=label):
                with patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue:
                    response = self._post_schedule(payload)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("errors", response.json())
                enqueue.assert_not_called()

    def test_bridge_accepts_each_exact_recurrence_boundary(self) -> None:
        server_now = datetime(2098, 12, 1, 12, 30, tzinfo=timezone.utc)
        multipliers = {"minutes": 1, "hours": 60, "days": 1440, "weeks": 10080}
        for unit, maximum in INTERVAL_VALUE_MAXIMUMS.items():
            with self.subTest(unit=unit):
                with (
                    patch("utilities.datetime.local_now", return_value=server_now),
                    patch(
                        "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
                        return_value=SimpleNamespace(pk=320),
                    ) as enqueue,
                ):
                    response = self._post_schedule(
                        {
                            "sync_stages": ["storage"],
                            "recurrence": {unit: maximum},
                        }
                    )
                self.assertEqual(response.status_code, 201, response.content)
                persisted = enqueue.call_args.kwargs["interval"]
                self.assertEqual(persisted, maximum * multipliers[unit])
                self.assertLessEqual(persisted, MAX_PERSISTED_INTERVAL_MINUTES)

    def test_bridge_rfc3339_parity_includes_leap_seconds(self) -> None:
        vectors = {
            "2099-12-31T23:59:60Z": "2100-01-01T00:00:00+00:00",
            "2100-01-01T00:59:60+01:00": "2100-01-01T00:00:00+00:00",
            "2099-12-31T18:59:60-05:00": "2100-01-01T00:00:00+00:00",
        }
        for schedule_at, expected in vectors.items():
            with self.subTest(schedule_at=schedule_at):
                with patch(
                    "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
                    return_value=SimpleNamespace(pk=321),
                ) as enqueue:
                    response = self._post_schedule(
                        {
                            "sync_stages": ["storage"],
                            "schedule_at": schedule_at,
                        }
                    )
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(
                    enqueue.call_args.kwargs["schedule_at"].isoformat(),
                    expected,
                )

    def test_invalid_or_unrepresentable_leap_instants_are_bounded_400s(self) -> None:
        for schedule_at in (
            "9999-12-31T23:59:60Z",
            "9999-12-31T23:59:60+23:59",
            "9999-12-31T23:59:59-23:59",
            "0001-01-01T00:00:00+23:59",
            "2026-08-12T12:34:60Z",
            "2099-12-31T23:59:60+01:00",
        ):
            with self.subTest(schedule_at=schedule_at):
                with (
                    patch(
                        "netbox_proxbox.api.views.models.ProxmoxEndpoint.objects.filter",
                        side_effect=AssertionError("invalid time reached the ORM"),
                    ) as endpoint_lookup,
                    patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue,
                ):
                    response = self._post_schedule(
                        {
                            "sync_stages": ["storage"],
                            "schedule_at": schedule_at,
                        }
                    )

                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("schedule_at", response.json()["errors"])
                endpoint_lookup.assert_not_called()
                enqueue.assert_not_called()

    def test_signed_64_bit_endpoint_bounds_apply_before_identity_lookup(self) -> None:
        serializer = ScheduleSyncRequestSerializer(
            data={
                "sync_stages": ["storage"],
                "proxmox_endpoint_ids": [MAX_POSITIVE_SIGNED_64_BIT_INTEGER],
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["proxmox_endpoint_ids"],
            [MAX_POSITIVE_SIGNED_64_BIT_INTEGER],
        )
        for invalid_number in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(invalid_number=invalid_number):
                invalid_serializer = ScheduleSyncRequestSerializer(
                    data={
                        "sync_stages": ["storage"],
                        "proxmox_endpoint_ids": [invalid_number],
                    }
                )
                self.assertFalse(invalid_serializer.is_valid())
                self.assertIn("proxmox_endpoint_ids", invalid_serializer.errors)

        for label, endpoint_id in (
            ("max plus one", MAX_POSITIVE_SIGNED_64_BIT_INTEGER + 1),
            ("hostile huge integer", 10**100),
        ):
            with self.subTest(label=label):
                with (
                    patch(
                        "netbox_proxbox.api.views.models.ProxmoxEndpoint.objects.filter",
                        side_effect=AssertionError("invalid ID reached the ORM"),
                    ) as endpoint_lookup,
                    patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue,
                ):
                    response = self._post_schedule(
                        {
                            "sync_stages": ["storage"],
                            "proxmox_endpoint_ids": [endpoint_id],
                        }
                    )
                self.assertEqual(response.status_code, 400, response.content)
                endpoint_lookup.assert_not_called()
                enqueue.assert_not_called()

    def test_exact_signed_64_bit_integer_token_reaches_identity_as_int(self) -> None:
        with patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue:
            response = self._post_schedule_json(
                '{"sync_stages":["storage"],'
                f'"proxmox_endpoint_ids":[{MAX_POSITIVE_SIGNED_64_BIT_INTEGER}]}}'
            )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            response.json()["errors"]["proxmox_endpoint_ids"],
            [
                "Unknown or disabled endpoint ID(s): "
                f"[{MAX_POSITIVE_SIGNED_64_BIT_INTEGER}]"
            ],
        )
        enqueue.assert_not_called()

    def test_legacy_netbox_endpoint_pk_uses_the_same_signed_64_bit_bound(self) -> None:
        with patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue:
            response = self._post_schedule(
                {
                    "sync_types": ["all"],
                    "netbox_endpoint_ids": [MAX_POSITIVE_SIGNED_64_BIT_INTEGER + 1],
                }
            )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("netbox_endpoint_ids", response.json()["errors"])
        enqueue.assert_not_called()

    def test_legacy_rest_schedule_fields_remain_compatible_but_unadvertised(
        self,
    ) -> None:
        with patch(
            "netbox_proxbox.jobs.ProxboxSyncJob.enqueue",
            return_value=SimpleNamespace(pk=322),
        ) as enqueue:
            response = self._post_schedule(
                {
                    "sync_types": ["all"],
                    "interval_value": 2,
                    "interval_unit": "hours",
                    "schedule_at": "2099-01-15T03:00:00",
                    "netbox_endpoint_ids": [self.netbox_endpoint.pk],
                }
            )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(enqueue.call_args.kwargs["sync_types"], ["all"])
        self.assertEqual(enqueue.call_args.kwargs["interval"], 120)
        self.assertEqual(
            enqueue.call_args.kwargs["schedule_at"].isoformat(),
            "2099-01-15T03:00:00+00:00",
        )
        self.assertEqual(enqueue.call_args.kwargs["netbox_endpoint_ids"], ["3"])

    def test_schedule_sync_rejects_invalid_type_and_all_combination(self) -> None:
        with patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue:
            invalid_response = self._post_schedule({"sync_types": ["not-real"]})
            all_response = self._post_schedule(
                {"sync_types": ["all", "virtual-machines"]}
            )

        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(all_response.status_code, 400)
        enqueue.assert_not_called()

    def test_schedule_sync_rejects_every_strict_schema_violation_without_enqueue(
        self,
    ) -> None:
        invalid_requests = (
            ("unknown field", {"sync_types": ["all"], "unexpected": True}),
            (
                "duplicate sync types",
                {"sync_types": ["virtual-machines", "virtual-machines"]},
            ),
            (
                "duplicate Proxmox endpoints",
                {"sync_types": ["all"], "proxmox_endpoint_ids": [7, 7]},
            ),
            (
                "duplicate NetBox endpoints",
                {"sync_types": ["all"], "netbox_endpoint_ids": [3, 3]},
            ),
            (
                "zero Proxmox endpoint",
                {"sync_types": ["all"], "proxmox_endpoint_ids": [0]},
            ),
            (
                "negative NetBox endpoint",
                {"sync_types": ["all"], "netbox_endpoint_ids": [-1]},
            ),
            (
                "string endpoint",
                {"sync_types": ["all"], "proxmox_endpoint_ids": ["7"]},
            ),
            (
                "boolean endpoint",
                {"sync_types": ["all"], "proxmox_endpoint_ids": [True]},
            ),
            (
                "string interval",
                {
                    "sync_types": ["all"],
                    "interval_value": "2",
                    "interval_unit": "hours",
                },
            ),
            (
                "boolean interval",
                {
                    "sync_types": ["all"],
                    "interval_value": True,
                    "interval_unit": "hours",
                },
            ),
            (
                "numeric job name",
                {"sync_types": ["all"], "job_name": 123},
            ),
            (
                "overlong job name",
                {"sync_types": ["all"], "job_name": "x" * 201},
            ),
            (
                "past schedule",
                {"sync_types": ["all"], "schedule_at": "2000-01-01T00:00:00Z"},
            ),
            (
                "zero interval",
                {
                    "sync_types": ["all"],
                    "interval_value": 0,
                    "interval_unit": "hours",
                },
            ),
            (
                "invalid interval unit",
                {
                    "sync_types": ["all"],
                    "interval_value": 2,
                    "interval_unit": "months",
                },
            ),
            (
                "legacy converted interval overflow",
                {
                    "sync_types": ["all"],
                    "interval_value": MAX_PERSISTED_INTERVAL_MINUTES,
                    "interval_unit": "weeks",
                },
            ),
        )
        for label, payload in invalid_requests:
            with self.subTest(label=label):
                with patch("netbox_proxbox.jobs.ProxboxSyncJob.enqueue") as enqueue:
                    response = self._post_schedule(payload)

                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("errors", response.json())
                enqueue.assert_not_called()

    def test_manifest_choice_values_match_runtime_choices(self) -> None:
        self.assertEqual(
            SYNC_TYPE_VALUES,
            [
                choice[0]
                for choice in SyncTypeChoices.CHOICES
                if choice[0] != SyncTypeChoices.ALL
            ],
        )
        self.assertEqual(
            INTERVAL_UNIT_VALUES,
            [choice[0] for choice in ScheduleIntervalUnitChoices.CHOICES],
        )
        request_serializer = ScheduleSyncRequestSerializer()
        self.assertEqual(
            list(request_serializer.fields["sync_stages"].child.choices),
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
