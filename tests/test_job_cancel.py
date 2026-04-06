"""Compatibility-focused tests for job cancel behavior."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import load_plugin_module


def _load_module(monkeypatch):
    return load_plugin_module(
        "netbox_proxbox.views.job_cancel", monkeypatch=monkeypatch
    )


def test_cancel_prefers_core_stop_rq_job(monkeypatch):
    module = _load_module(monkeypatch)

    called = {"job_id": None}

    def fake_stop(job_id):
        called["job_id"] = job_id
        return ["stopped"]

    monkeypatch.setattr(module, "stop_rq_job", fake_stop)

    job = SimpleNamespace(job_id="abc-123", queue_name="default")
    ok = module.cancel_rq_job_for_netbox_job(job)

    assert ok is True
    assert called["job_id"] == "abc-123"


def test_cancel_falls_back_to_queue_cancel_for_scheduled(monkeypatch):
    module = _load_module(monkeypatch)

    class _RQJob:
        def __init__(self):
            self.cancelled = False

        def get_status(self):
            return module.RQJobStatus.SCHEDULED

        def cancel(self):
            self.cancelled = True

    rq_job = _RQJob()

    class _Queue:
        def fetch_job(self, jid):
            return rq_job

    monkeypatch.setattr(module, "stop_rq_job", lambda _job_id: [])
    monkeypatch.setattr(module, "get_queue", lambda _queue_name: _Queue())

    job = SimpleNamespace(job_id="job-44", queue_name="default")
    ok = module.cancel_rq_job_for_netbox_job(job)

    assert ok is True
    assert rq_job.cancelled is True


def test_cancel_returns_false_when_not_found(monkeypatch):
    module = _load_module(monkeypatch)

    class _Queue:
        def fetch_job(self, jid):
            return None

    def _raise_not_found(job_id):
        raise module.Http404()

    monkeypatch.setattr(module, "stop_rq_job", _raise_not_found)
    monkeypatch.setattr(module, "get_queue", lambda _queue_name: _Queue())

    job = SimpleNamespace(job_id="job-404", queue_name="default")
    ok = module.cancel_rq_job_for_netbox_job(job)

    assert ok is False
