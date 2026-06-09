"""Behavior tests for ``services.sync_backup_routines.sync_backup_routines``.

The full sync orchestration is heavy (Django ORM, transaction.atomic,
proxbox-api HTTP, Pydantic schema validation). The two pieces that are easy to
break in isolation are the small helpers and the early-exit error paths:

* ``_get_backup_routine_id_from_job_id`` — splits Proxmox job ids of the form
  ``"local:123"`` so they can be matched against backend records.
* The "endpoint not found" / "FastAPI URL not configured" branches that abort
  without touching the database.

This test file loads the module via importlib with stubbed ``django``,
``netbox_proxbox.models``, ``netbox_proxbox.choices``,
``netbox_proxbox.schemas.backup_routine``, and ``netbox_proxbox.services.*``
modules so it can exercise those paths without a NetBox environment.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sync_backup_module(monkeypatch):
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    choices = types.ModuleType("netbox_proxbox.choices")
    choices.BackupRoutineStatusChoices = SimpleNamespace(ACTIVE="active", STALE="stale")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices)

    class _DoesNotExist(Exception):
        pass

    class _Manager:
        def __init__(self, item: object | None = None):
            self.item = item

        def get(self, **_kwargs):
            if self.item is None:
                raise _DoesNotExist()
            return self.item

        def filter(self, **_kwargs):
            return self

        def values_list(self, *_args, **_kwargs):
            return []

        def update(self, **_kwargs):
            return (0, {})

        def update_or_create(self, defaults, **_kwargs):
            return SimpleNamespace(), True

        def first(self):
            return self.item

        def count(self):
            return 0

    class _ProxmoxEndpoint:
        DoesNotExist = _DoesNotExist
        objects = _Manager(SimpleNamespace(pk=1, name="pve"))

    class _ProxmoxNode:
        DoesNotExist = _DoesNotExist
        objects = _Manager()

    class _ProxmoxStorage:
        DoesNotExist = _DoesNotExist
        objects = _Manager()

    class _BackupRoutine:
        objects = _Manager()

    models = types.ModuleType("netbox_proxbox.models")
    models.BackupRoutine = _BackupRoutine
    models.ProxmoxEndpoint = _ProxmoxEndpoint
    models.ProxmoxNode = _ProxmoxNode
    models.ProxmoxStorage = _ProxmoxStorage
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    schemas_pkg = types.ModuleType("netbox_proxbox.schemas")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.schemas", schemas_pkg)

    backup_schema = types.ModuleType("netbox_proxbox.schemas.backup_routine")

    class _Schema:
        @classmethod
        def model_validate(cls, _data):
            return cls()

        def model_dump(self, **_kwargs):
            return {}

    backup_schema.GetClusterBackupIdResponse = _Schema
    backup_schema.BackupRoutineSchema = _Schema
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.schemas.backup_routine", backup_schema
    )

    services_pkg = types.ModuleType("netbox_proxbox.services")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)

    backend_proxy = types.ModuleType("netbox_proxbox.services.backend_proxy")
    backend_proxy.get_fastapi_request_context = lambda: None
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_proxy", backend_proxy
    )

    views_pkg = types.ModuleType("netbox_proxbox.views")
    views_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", views_pkg)

    backend_sync = types.ModuleType("netbox_proxbox.views.backend_sync")
    backend_sync.resolve_backend_endpoint_id = lambda endpoint, **_kwargs: (
        getattr(endpoint, "pk", None),
        None,
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.backend_sync", backend_sync)

    django_pkg = types.ModuleType("django")
    monkeypatch.setitem(sys.modules, "django", django_pkg)
    db_mod = types.ModuleType("django.db")

    class _Atomic:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    db_mod.transaction = SimpleNamespace(atomic=lambda: _Atomic())
    monkeypatch.setitem(sys.modules, "django.db", db_mod)

    sys.modules.pop("netbox_proxbox.services.sync_backup_routines", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.services.sync_backup_routines",
        REPO_ROOT / "netbox_proxbox" / "services" / "sync_backup_routines.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_proxbox.services.sync_backup_routines"] = module
    spec.loader.exec_module(module)
    return module


def test_get_backup_routine_id_from_job_id_strips_storage_prefix(sync_backup_module):
    assert sync_backup_module._get_backup_routine_id_from_job_id("local:123") == "123"
    assert sync_backup_module._get_backup_routine_id_from_job_id("nfs:abc") == "abc"


def test_get_backup_routine_id_from_job_id_returns_input_when_no_colon(
    sync_backup_module,
):
    assert (
        sync_backup_module._get_backup_routine_id_from_job_id("backup-1") == "backup-1"
    )


def test_sync_returns_error_when_endpoint_missing(sync_backup_module, monkeypatch):
    """Missing ProxmoxEndpoint must short-circuit before any HTTP call."""
    from netbox_proxbox.models import ProxmoxEndpoint

    ProxmoxEndpoint.objects = type(ProxmoxEndpoint.objects)(item=None)

    with patch("requests.get") as mock_get:
        result = sync_backup_module.sync_backup_routines(endpoint_id=42)
    assert result == {"success": False, "error": "Endpoint not found"}
    mock_get.assert_not_called()


def test_sync_returns_error_when_no_fastapi_url_and_context_missing(
    sync_backup_module,
):
    """If no FastAPI URL is configured and no context resolves, abort."""
    sync_backup_module.get_fastapi_request_context = lambda: None
    with patch("requests.get") as mock_get:
        result = sync_backup_module.sync_backup_routines(endpoint_id=1)
    assert result["success"] is False
    assert "FastAPI URL not configured" in result["error"]
    mock_get.assert_not_called()


def test_sync_propagates_http_error_for_list_endpoint(sync_backup_module):
    """A request error on the job-list endpoint should be reported, not raised."""
    import requests as real_requests

    err = real_requests.exceptions.ConnectionError("refused")
    sync_backup_module.resolve_backend_endpoint_id = lambda *args, **kwargs: (1, None)
    with patch("requests.get", side_effect=err):
        result = sync_backup_module.sync_backup_routines(
            endpoint_id=1,
            fastapi_url="http://backend:8000",
            auth_headers={"X-Proxbox-API-Key": "k"},
        )
    assert result["success"] is False
    assert "HTTP error fetching backup routine list" in result["error"]
