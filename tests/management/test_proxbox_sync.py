"""Tests for the proxbox_sync Django management command."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from django.core.management.base import CommandError


@pytest.fixture
def proxbox_sync_command(monkeypatch):
    """Load proxbox_sync.py with stubs for plugin internals.

    Mirrors the stub pattern used by tests/test_jobs.py — we don't bootstrap
    Django/NetBox; we inject just enough of the plugin's modules to let the
    command import and run.
    """
    # netbox_proxbox.choices
    choices_mod = types.ModuleType("netbox_proxbox.choices")
    choices_mod.SyncTypeChoices = SimpleNamespace(ALL="all")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)

    # netbox_proxbox.jobs — only the symbols the command imports
    jobs_mod = types.ModuleType("netbox_proxbox.jobs")
    jobs_mod.PROXBOX_SYNC_QUEUE_NAME = "default"
    jobs_mod.PROXBOX_SYNC_JOB_TIMEOUT = 7200

    enqueue_calls: list[dict] = []

    class _ProxboxSyncJob:
        last_kwargs: dict = {}
        raise_on_enqueue: Exception | None = None
        next_job_pk: int = 42

        @classmethod
        def enqueue(cls, **kwargs):
            cls.last_kwargs = kwargs
            enqueue_calls.append(kwargs)
            if cls.raise_on_enqueue is not None:
                raise cls.raise_on_enqueue
            return SimpleNamespace(pk=cls.next_job_pk)

    jobs_mod.ProxboxSyncJob = _ProxboxSyncJob
    monkeypatch.setitem(sys.modules, "netbox_proxbox.jobs", jobs_mod)

    # netbox_proxbox.models — only ProxmoxEndpoint is needed
    models_mod = types.ModuleType("netbox_proxbox.models")

    class _ValuesList:
        def __init__(self, rows):
            self._rows = list(rows)

        def __iter__(self):
            return iter(self._rows)

    class _ProxmoxEndpointObjects:
        rows: list[int] = [1, 2]

        @classmethod
        def values_list(cls, *args, **kwargs):
            return _ValuesList(cls.rows)

    class _ProxmoxEndpoint:
        objects = _ProxmoxEndpointObjects

    models_mod.ProxmoxEndpoint = _ProxmoxEndpoint
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    # netbox_proxbox.services.backend_auth
    backend_auth_mod = types.ModuleType("netbox_proxbox.services.backend_auth")
    backend_auth_mod.wait_for_backend_ready_result = (True, "Backend is reachable")

    def _wait_for_backend_ready(context, max_retries: int = 30, **kwargs):
        return backend_auth_mod.wait_for_backend_ready_result

    backend_auth_mod.wait_for_backend_ready = _wait_for_backend_ready
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_auth", backend_auth_mod
    )

    # netbox_proxbox.services.backend_context
    backend_context_mod = types.ModuleType("netbox_proxbox.services.backend_context")
    backend_context_mod.context_result = SimpleNamespace(http_url="http://backend.test")
    backend_context_mod.get_fastapi_request_context = lambda **kw: (
        backend_context_mod.context_result
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_context", backend_context_mod
    )

    # netbox.jobs — for the --wait Job polling
    netbox_jobs_mod = types.ModuleType("netbox.jobs")

    class _JobObjects:
        status_sequence: list[str] = ["completed"]
        _idx = 0

        @classmethod
        def reset(cls):
            cls._idx = 0

        @classmethod
        def get(cls, pk):
            idx = min(cls._idx, len(cls.status_sequence) - 1)
            status = cls.status_sequence[idx]
            cls._idx += 1
            return SimpleNamespace(pk=pk, status=status)

    class _Job:
        objects = _JobObjects

    netbox_jobs_mod.Job = _Job
    monkeypatch.setitem(sys.modules, "netbox.jobs", netbox_jobs_mod)

    # django.contrib.auth.get_user_model
    fake_user = SimpleNamespace(username="admin", pk=1)

    class _UserQS:
        users: list = [fake_user]
        return_first: SimpleNamespace | None = fake_user

        @classmethod
        def filter(cls, **kwargs):
            qs = cls()
            qs._kwargs = kwargs
            return qs

        def order_by(self, *_):
            return self

        def first(self):
            kwargs = getattr(self, "_kwargs", {})
            if "username" in kwargs:
                for u in _UserQS.users:
                    if u.username == kwargs["username"]:
                        return u
                return None
            return _UserQS.return_first

    class _UserModel:
        objects = _UserQS

    def _get_user_model():
        return _UserModel

    monkeypatch.setattr(
        "django.contrib.auth.get_user_model", _get_user_model, raising=True
    )

    # django_rq stub (worker probe)
    django_rq_mod = types.ModuleType("django_rq")
    django_rq_mod.worker_count = 1

    def _get_queue(_name):
        return SimpleNamespace(workers=[object()] * django_rq_mod.worker_count)

    django_rq_mod.get_queue = _get_queue
    monkeypatch.setitem(sys.modules, "django_rq", django_rq_mod)

    # Load the command module fresh
    root = Path(__file__).resolve().parents[2]
    path = (
        root
        / "netbox_proxbox"
        / "management"
        / "commands"
        / "proxbox_sync.py"
    )
    sys.modules.pop("netbox_proxbox.management.commands.proxbox_sync", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.management.commands.proxbox_sync", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.management.commands.proxbox_sync"] = module
    spec.loader.exec_module(module)

    return SimpleNamespace(
        module=module,
        enqueue_calls=enqueue_calls,
        jobs_mod=jobs_mod,
        models_mod=models_mod,
        backend_auth_mod=backend_auth_mod,
        backend_context_mod=backend_context_mod,
        netbox_jobs_mod=netbox_jobs_mod,
        django_rq_mod=django_rq_mod,
        user_model=_UserModel,
        user_qs=_UserQS,
        fake_user=fake_user,
        job_objects=_JobObjects,
        proxbox_sync_job=_ProxboxSyncJob,
        proxmox_endpoint=_ProxmoxEndpoint,
    )


def _run(command_module, **options):
    """Invoke Command().handle with full defaults populated."""
    defaults = {
        "username": None,
        "wait": False,
        "timeout": None,
        "poll_interval": 0.0,
        "worker_grace": 0.0,
    }
    defaults.update(options)
    cmd = command_module.Command()
    cmd.stdout = MagicMock()
    cmd.stderr = MagicMock()
    cmd.style = SimpleNamespace(
        SUCCESS=lambda x: x,
        WARNING=lambda x: x,
        ERROR=lambda x: x,
        NOTICE=lambda x: x,
    )
    cmd.handle(**defaults)
    return cmd


def test_healthy_enqueue_path(proxbox_sync_command):
    """Healthy path enqueues a job with ALL sync types and all endpoint IDs."""
    proxbox_sync_command.proxbox_sync_job.raise_on_enqueue = None
    proxbox_sync_command.user_qs.return_first = proxbox_sync_command.fake_user

    _run(proxbox_sync_command.module)

    assert len(proxbox_sync_command.enqueue_calls) == 1
    call = proxbox_sync_command.enqueue_calls[0]
    assert call["sync_types"] == ["all"]
    assert call["proxmox_endpoint_ids"] == [1, 2]
    assert call["queue_name"] == "default"
    assert call["user"] is proxbox_sync_command.fake_user
    assert "CLI" in call["name"]


def test_backend_unreachable_raises_command_error(proxbox_sync_command):
    """A failed reachability probe must surface as a non-zero exit."""
    proxbox_sync_command.backend_auth_mod.wait_for_backend_ready_result = (
        False,
        "Backend not reachable after 5 attempts",
    )
    with pytest.raises(CommandError, match="not reachable"):
        _run(proxbox_sync_command.module)
    assert proxbox_sync_command.enqueue_calls == []


def test_no_fastapi_endpoint_raises_command_error(proxbox_sync_command):
    """Missing FastAPIEndpoint config must hard-fail before enqueuing."""
    proxbox_sync_command.backend_context_mod.context_result = None
    with pytest.raises(CommandError, match="No FastAPIEndpoint"):
        _run(proxbox_sync_command.module)
    assert proxbox_sync_command.enqueue_calls == []


def test_no_proxmox_endpoints_exits_zero_without_enqueue(proxbox_sync_command):
    """Zero ProxmoxEndpoint rows is a warning, not an error."""
    proxbox_sync_command.proxmox_endpoint.objects.rows = []
    _run(proxbox_sync_command.module)
    assert proxbox_sync_command.enqueue_calls == []


def test_unknown_user_raises_command_error(proxbox_sync_command):
    """--user must resolve to an existing user."""
    with pytest.raises(CommandError, match="ghost"):
        _run(proxbox_sync_command.module, username="ghost")
    assert proxbox_sync_command.enqueue_calls == []


def test_no_active_superuser_raises_command_error(proxbox_sync_command):
    """If no --user is given and no superuser exists, hard-fail."""
    proxbox_sync_command.user_qs.return_first = None
    with pytest.raises(CommandError, match="superuser"):
        _run(proxbox_sync_command.module)


def test_wait_happy_path_returns_on_completion(proxbox_sync_command):
    """--wait blocks until completion; success exits cleanly."""
    proxbox_sync_command.job_objects.status_sequence = ["pending", "running", "completed"]
    proxbox_sync_command.job_objects.reset()
    _run(proxbox_sync_command.module, wait=True, timeout=5, poll_interval=0.0)
    assert len(proxbox_sync_command.enqueue_calls) == 1


def test_wait_failed_status_raises_command_error(proxbox_sync_command):
    """A terminal non-success status must surface as a non-zero exit."""
    proxbox_sync_command.job_objects.status_sequence = ["running", "errored"]
    proxbox_sync_command.job_objects.reset()
    with pytest.raises(CommandError, match="errored"):
        _run(proxbox_sync_command.module, wait=True, timeout=5, poll_interval=0.0)


def test_wait_no_worker_fast_fails(proxbox_sync_command):
    """--wait with no RQ worker and job stuck pending must fast-fail."""
    proxbox_sync_command.job_objects.status_sequence = ["pending"]
    proxbox_sync_command.job_objects.reset()
    proxbox_sync_command.django_rq_mod.worker_count = 0
    with pytest.raises(CommandError, match="No RQ worker"):
        _run(
            proxbox_sync_command.module,
            wait=True,
            timeout=5,
            poll_interval=0.0,
            worker_grace=0.0,
        )


def test_enqueue_failure_surfaces_as_command_error(proxbox_sync_command):
    """If ProxboxSyncJob.enqueue raises, the command must exit non-zero."""
    proxbox_sync_command.proxbox_sync_job.raise_on_enqueue = RuntimeError("boom")
    with pytest.raises(CommandError, match="boom"):
        _run(proxbox_sync_command.module)
