"""Real Django response-lifecycle coverage for the Proxbox job SSE stream."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (
    REPO_ROOT.parent / "netbox" / "netbox",
    REPO_ROOT.parents[1] / "nmulticloud-context" / "netbox" / "netbox",
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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

if not hasattr(django, "__path__"):
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
except Exception as exc:  # pragma: no cover - external test harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}",
        allow_module_level=True,
    )

from django.http import HttpRequest  # noqa: E402

from netbox_proxbox.views import job_stream as job_stream_module  # noqa: E402


def test_streaming_response_close_releases_job_observer_producer() -> None:
    """Django response.close() must close the generator Gunicorn iterates."""
    created_threads = []
    real_thread = job_stream_module.threading.Thread

    def recording_thread(*args, **kwargs):
        thread = real_thread(*args, **kwargs)
        created_threads.append(thread)
        return thread

    job = SimpleNamespace(
        pk=61,
        status="running",
        data={"proxbox_sync": {"params": {}}},
        save=lambda **kwargs: None,
        refresh_from_db=lambda: None,
        log_entries=[],
    )
    queryset = SimpleNamespace(first=lambda: job)

    with (
        patch.object(
            job_stream_module.JobModel.objects, "filter", return_value=queryset
        ),
        patch.object(job_stream_module, "JOB_STREAM_HEARTBEAT_INTERVAL", 0.01),
        patch.object(job_stream_module.threading, "Thread", recording_thread),
    ):
        response = job_stream_module.JobStreamSSEView().get(HttpRequest(), job.pk)
        response_iterator = iter(response.streaming_content)

        assert b"event: step" in next(response_iterator)
        assert next(response_iterator) == b": keep-alive\n\n"
        response.close()

    assert response.closed
    assert len(created_threads) == 1
    created_threads[0].join(timeout=0.5)
    assert not created_threads[0].is_alive()
