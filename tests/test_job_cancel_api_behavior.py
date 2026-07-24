"""Behavioral tests for the Proxbox Sync job cancel API (issue #268).

`api/jobs.py` is not loadable through ``conftest.load_plugin_module`` (that helper
is hardcoded for ``netbox_proxbox.views.*``), and neither DRF nor NetBox is
installed in the pure-domain test env, so this module path-loads ``api/jobs.py``
against a compact stub environment — the same technique
``test_node_ssh_credential_api.py`` uses for a comparable custom ``APIView``.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
JOBS_API = REPO_ROOT / "netbox_proxbox" / "api" / "jobs.py"


def _load(monkeypatch):
    """Path-load ``netbox_proxbox.api.jobs`` against stub deps; return the module."""
    calls = {"cancel": 0}

    # --- rest_framework stubs -------------------------------------------------
    class _BasePermission:
        pass

    class _APIView:
        pass

    class _Response:
        def __init__(self, data, status=200):
            self.data = data
            self.status_code = status

    rf = types.ModuleType("rest_framework")
    rf_status = types.ModuleType("rest_framework.status")
    rf_status.HTTP_400_BAD_REQUEST = 400
    rf_perms = types.ModuleType("rest_framework.permissions")
    rf_perms.BasePermission = _BasePermission
    rf_req = types.ModuleType("rest_framework.request")
    rf_req.Request = object
    rf_resp = types.ModuleType("rest_framework.response")
    rf_resp.Response = _Response
    rf_views = types.ModuleType("rest_framework.views")
    rf_views.APIView = _APIView

    # --- core / django stubs --------------------------------------------------
    core_choices = types.ModuleType("core.choices")
    core_choices.JobStatusChoices = SimpleNamespace(
        TERMINAL_STATE_CHOICES=("completed", "errored", "failed"),
        STATUS_FAILED="failed",
    )
    core_models = types.ModuleType("core.models")
    core_models.Job = SimpleNamespace(objects=SimpleNamespace())
    django_shortcuts = types.ModuleType("django.shortcuts")
    django_shortcuts.get_object_or_404 = lambda qs, pk: qs  # overridden per test

    # --- reused netbox_proxbox helpers (stubbed) ------------------------------
    nbp = types.ModuleType("netbox_proxbox")
    nbp_jobs = types.ModuleType("netbox_proxbox.jobs")
    nbp_jobs.is_proxbox_sync_job = lambda job: True
    nbp_views = types.ModuleType("netbox_proxbox.views")
    nbp_job_cancel = types.ModuleType("netbox_proxbox.views.job_cancel")

    def _cancel(job):
        calls["cancel"] += 1
        return False

    nbp_job_cancel.cancel_rq_job_for_netbox_job = _cancel

    for name, mod in {
        "rest_framework": rf,
        "rest_framework.status": rf_status,
        "rest_framework.permissions": rf_perms,
        "rest_framework.request": rf_req,
        "rest_framework.response": rf_resp,
        "rest_framework.views": rf_views,
        "core": types.ModuleType("core"),
        "core.choices": core_choices,
        "core.models": core_models,
        "django": types.ModuleType("django"),
        "django.shortcuts": django_shortcuts,
        "netbox_proxbox": nbp,
        "netbox_proxbox.jobs": nbp_jobs,
        "netbox_proxbox.views": nbp_views,
        "netbox_proxbox.views.job_cancel": nbp_job_cancel,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)

    spec = importlib.util.spec_from_file_location("netbox_proxbox.api.jobs", JOBS_API)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.api.jobs", module)
    spec.loader.exec_module(module)
    module._test_calls = calls
    return module


def _request(*, authenticated=True, perms=("core.delete_job",), user=True):
    if not user:
        return SimpleNamespace(user=None)
    return SimpleNamespace(
        user=SimpleNamespace(
            is_authenticated=authenticated,
            has_perm=lambda perm: perm in perms,
        )
    )


def test_permission_allows_authenticated_user_with_delete_job(monkeypatch):
    module = _load(monkeypatch)
    assert module._ProxboxJobCancelPermission().has_permission(_request(), object()) is True


def test_permission_denies_without_delete_job(monkeypatch):
    module = _load(monkeypatch)
    perm = module._ProxboxJobCancelPermission()
    assert perm.has_permission(_request(perms=("core.view_job",)), object()) is False


def test_permission_denies_unauthenticated(monkeypatch):
    module = _load(monkeypatch)
    perm = module._ProxboxJobCancelPermission()
    assert perm.has_permission(_request(authenticated=False), object()) is False


def test_permission_denies_when_no_user(monkeypatch):
    module = _load(monkeypatch)
    perm = module._ProxboxJobCancelPermission()
    assert perm.has_permission(_request(user=False), object()) is False


class _FakeJob:
    def __init__(self, status):
        self.pk = 42
        self.status = status
        self.terminated = None

    def refresh_from_db(self):
        return None

    def terminate(self, status, error):
        self.terminated = (status, error)
        self.status = status


def _wire_job(module, monkeypatch, job, *, is_proxbox=True):
    module.Job.objects = SimpleNamespace(restrict=lambda user, action: job)
    monkeypatch.setattr(module, "get_object_or_404", lambda qs, pk: job)
    monkeypatch.setattr(module, "is_proxbox_sync_job", lambda j: is_proxbox)


def test_post_cancels_running_proxbox_job(monkeypatch):
    module = _load(monkeypatch)
    job = _FakeJob("running")
    _wire_job(module, monkeypatch, job)
    resp = module.ProxboxJobCancelAPIView().post(_request(), pk=42)
    assert resp.data["ok"] is True
    assert resp.data["job_id"] == 42
    assert module._test_calls["cancel"] == 1
    assert job.terminated == ("failed", "Cancelled via API.")
    assert job.status == "failed"


def test_post_rejects_non_proxbox_job(monkeypatch):
    module = _load(monkeypatch)
    job = _FakeJob("running")
    _wire_job(module, monkeypatch, job, is_proxbox=False)
    resp = module.ProxboxJobCancelAPIView().post(_request(), pk=42)
    assert resp.status_code == 400
    assert resp.data["ok"] is False
    assert module._test_calls["cancel"] == 0
    assert job.terminated is None


def test_post_noops_on_already_terminal_job(monkeypatch):
    module = _load(monkeypatch)
    job = _FakeJob("failed")
    _wire_job(module, monkeypatch, job)
    resp = module.ProxboxJobCancelAPIView().post(_request(), pk=42)
    assert resp.data["ok"] is True
    assert module._test_calls["cancel"] == 0
    assert job.terminated is None
    assert "already finished" in resp.data["detail"]
