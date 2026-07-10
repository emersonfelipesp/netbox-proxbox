"""Isolated tests for service-monitoring scheduler due selection."""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_jobs_module(monkeypatch):
    netbox_constants = types.ModuleType("netbox.constants")
    netbox_constants.RQ_QUEUE_DEFAULT = "default"

    netbox_jobs = types.ModuleType("netbox.jobs")

    class _JobRunner:
        pass

    netbox_jobs.JobRunner = _JobRunner
    netbox_jobs.system_job = lambda **kwargs: lambda cls: cls

    choices = types.ModuleType("netbox_proxbox.choices")
    choices.SyncModeChoices = SimpleNamespace(
        ALWAYS="always",
        BOOTSTRAP_ONLY="bootstrap_only",
        DISABLED="disabled",
    )
    choices.SyncTypeChoices = SimpleNamespace(ALL="all")

    models = types.ModuleType("netbox_proxbox.models")

    class _EndpointManager:
        def filter(self, **kwargs):
            return []

    models.ProxmoxEndpoint = type(
        "ProxmoxEndpoint",
        (),
        {"objects": _EndpointManager()},
    )

    schemas = types.ModuleType("netbox_proxbox.schemas")
    schemas.SyncJobData = SimpleNamespace(from_job=lambda job: None)

    sync_types = types.ModuleType("netbox_proxbox.sync_types")
    sync_types._TARGETED_VM_JOB_NAME_RE = re.compile("^$")
    sync_types.expanded_sync_stages = lambda types_: []
    sync_types.normalize_sync_types = lambda values: values

    sync_params = types.ModuleType("netbox_proxbox.sync_params")
    for name in (
        "_ignore_ipv6_link_local_addresses_setting",
        "_primary_ip_preference_setting",
        "_infer_targeted_vm_job_params",
        "_normalize_batch_object_ids",
        "_proxbox_fetch_max_concurrency_setting",
        "_serialize_sync_params",
        "_use_guest_agent_interface_name_setting",
        "_vm_interface_sync_strategy_setting",
        "effective_sync_modes_for_endpoint",
    ):
        setattr(sync_params, name, lambda *args, **kwargs: {})

    sync_stages = types.ModuleType("netbox_proxbox.sync_stages")
    sync_stages._run_batch_selected_sync = lambda *args, **kwargs: {}
    sync_stages._run_all_stages_sync = lambda *args, **kwargs: []

    sync_ownership = types.ModuleType("netbox_proxbox.sync_ownership")
    sync_ownership._claim_rq_sync_ownership = lambda job: True
    sync_ownership._release_rq_sync_ownership = lambda job: None

    package = types.ModuleType("netbox_proxbox")
    package.__path__ = [str(REPO_ROOT / "netbox_proxbox")]

    for name, mod in [
        ("netbox.constants", netbox_constants),
        ("netbox.jobs", netbox_jobs),
        ("netbox_proxbox", package),
        ("netbox_proxbox.choices", choices),
        ("netbox_proxbox.models", models),
        ("netbox_proxbox.schemas", schemas),
        ("netbox_proxbox.sync_types", sync_types),
        ("netbox_proxbox.sync_params", sync_params),
        ("netbox_proxbox.sync_stages", sync_stages),
        ("netbox_proxbox.sync_ownership", sync_ownership),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)

    path = REPO_ROOT / "netbox_proxbox" / "jobs.py"
    spec = importlib.util.spec_from_file_location("_jobs_service_monitoring", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _endpoint(**overrides):
    data = {
        "service_monitoring_enabled": True,
        "service_monitoring_eligible": True,
        "service_monitoring_interval_minutes": 5,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_service_monitoring_due_selection(monkeypatch):
    module = _load_jobs_module(monkeypatch)
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)

    assert module.service_monitoring_collection_due(
        _endpoint(),
        latest_collected_at=None,
        now=now,
    )
    assert not module.service_monitoring_collection_due(
        _endpoint(),
        latest_collected_at=now - timedelta(minutes=4, seconds=59),
        now=now,
    )
    assert module.service_monitoring_collection_due(
        _endpoint(),
        latest_collected_at=now - timedelta(minutes=5),
        now=now,
    )
    assert not module.service_monitoring_collection_due(
        _endpoint(service_monitoring_enabled=False),
        latest_collected_at=None,
        now=now,
    )
    assert not module.service_monitoring_collection_due(
        _endpoint(service_monitoring_eligible=False),
        latest_collected_at=None,
        now=now,
    )


def test_scheduler_skips_endpoint_with_pending_unprojected_collection() -> None:
    source = (REPO_ROOT / "netbox_proxbox" / "jobs.py").read_text(encoding="utf-8")

    assert "SERVICE_COLLECTION_STATUS_PENDING" in source
    assert "pending_endpoint_ids = set(" in source
    assert "status=SERVICE_COLLECTION_STATUS_PENDING" in source
    assert "if endpoint.pk in pending_endpoint_ids:" in source
    assert "a prior collection is still pending" in source
