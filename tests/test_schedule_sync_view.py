from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from tests.conftest import load_plugin_module


class _QueryDict(dict):
    def getlist(self, key):
        value = self.get(key, [])
        if isinstance(value, list):
            return value
        return [value]


class _JobQuerySet:
    def __init__(self, jobs):
        self._jobs = list(jobs)

    def restrict(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def exclude(self, **kwargs):
        status = kwargs.get("status")
        if status is None:
            return self
        return _JobQuerySet(
            [job for job in self._jobs if getattr(job, "status", None) != status]
        )

    def order_by(self, *args, **kwargs):
        return self

    def iterator(self, chunk_size=64):
        return iter(self._jobs)

    def get(self, pk=None, **kwargs):
        target = pk if pk is not None else kwargs.get("pk")
        for job in self._jobs:
            if str(getattr(job, "pk", "")) == str(target):
                return job
        raise self.model.DoesNotExist()


class _JobModel:
    class DoesNotExist(Exception):
        pass

    objects = None


def test_schedule_sync_get_uses_scheduled_field_and_pk(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.schedule_sync", monkeypatch=monkeypatch
    )

    scheduled_at = datetime(2026, 4, 8, 3, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(
        pk=7,
        name="Daily Proxbox Sync",
        scheduled=scheduled_at,
        interval=1440,
        status="scheduled",
        data={"proxbox_sync": {"params": {"sync_types": ["all"]}}},
    )
    job_qs = _JobQuerySet([job])
    job_qs.model = _JobModel

    monkeypatch.setattr(module, "Job", _JobModel)
    monkeypatch.setattr(module.Job, "objects", job_qs, raising=False)
    monkeypatch.setattr(module, "is_proxbox_sync_job", lambda candidate: True)
    monkeypatch.setattr(
        module.SyncTypeChoices,
        "CHOICES",
        [(module.SyncTypeChoices.ALL, "All")],
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "proxbox_sync_params_from_job",
        lambda candidate: {"sync_types": ["all"]},
    )

    response = module.ScheduleSyncView().get(
        SimpleNamespace(
            user=SimpleNamespace(has_perm=lambda *args, **kwargs: True),
            GET=_QueryDict({"edit": "7"}),
        )
    )

    form = response["context"]["form"]
    assert form.kwargs["initial"]["schedule_at"] == scheduled_at
    assert response["context"]["scheduled_jobs"][0]["pk"] == 7
    assert response["context"]["scheduled_jobs"][0]["schedule"] == scheduled_at


def test_schedule_sync_cancel_marks_job_failed_without_rescheduling(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.schedule_sync", monkeypatch=monkeypatch
    )

    job = SimpleNamespace(
        pk=9,
        name="Daily Proxbox Sync",
        scheduled=datetime(2026, 4, 8, 3, 0, tzinfo=timezone.utc),
        interval=1440,
        status="scheduled",
        completed=None,
        error="",
        data={"proxbox_sync": {"params": {"sync_types": ["all"]}}},
    )

    def save(*args, **kwargs):
        return None

    job.save = save

    job_qs = _JobQuerySet([job])
    job_qs.model = _JobModel

    enqueue_calls: list[dict[str, object]] = []

    monkeypatch.setattr(module, "Job", _JobModel)
    monkeypatch.setattr(module.Job, "objects", job_qs, raising=False)
    monkeypatch.setattr(module, "is_proxbox_sync_job", lambda candidate: True)
    monkeypatch.setattr(
        module.ProxboxSyncJob,
        "enqueue",
        classmethod(lambda cls, **kwargs: enqueue_calls.append(kwargs)),
    )

    response = module.ScheduleSyncView().post(
        SimpleNamespace(
            user=SimpleNamespace(has_perm=lambda *args, **kwargs: True),
            POST={"cancel_job": "9"},
        )
    )

    assert response["redirect"] == "plugins:netbox_proxbox:schedule_sync"
    assert job.status == module.JobStatusChoices.STATUS_FAILED
    assert job.error == "Cancelled by user."
    assert job.completed is not None
    assert enqueue_calls == []
