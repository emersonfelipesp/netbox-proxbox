"""Regression coverage for stage-failure message compatibility."""

from __future__ import annotations

import json
import sys

from tests import test_preflight_diagnosis as preflight_diagnosis


sync_stages_module = preflight_diagnosis.sync_stages_module


def _attempt(sync_types, payload):
    return sync_types._StageFailureAttempt(
        attempt_index=1,
        status=500,
        detail=sync_types._extract_backend_error_text(payload) or str(payload),
        classification="application",
        elapsed=0.125,
        payload=payload,
    )


def test_composer_preserves_postgres_slot_guidance(sync_stages_module):
    sync_types = sys.modules["netbox_proxbox.sync_types"]
    marker = (
        "remaining connection slots are reserved for roles with the superuser attribute"
    )
    payload = {
        "detail": json.dumps(
            {
                "error": f"FATAL: {marker}",
                "exception": "OperationalError",
            }
        )
    }

    message = sync_types._compose_stage_failure_message(
        "devices", [_attempt(sync_types, payload)]
    )

    assert message == (
        "Stage 'devices' failed (HTTP 500): NetBox database is overloaded and has "
        "no free PostgreSQL connections for this sync. Wait for running jobs to "
        "finish, then retry. If this keeps happening, increase PostgreSQL connection "
        "capacity or reduce concurrent sync jobs."
    )


def test_composer_preserves_exception_suffix(sync_stages_module):
    sync_types = sys.modules["netbox_proxbox.sync_types"]
    payload = {
        "detail": "backend validation failed",
        "exception": "ValidationError",
    }

    message = sync_types._compose_stage_failure_message(
        "devices", [_attempt(sync_types, payload)]
    )

    assert message == (
        "Stage 'devices' failed (HTTP 500): backend validation failed (ValidationError)"
    )
