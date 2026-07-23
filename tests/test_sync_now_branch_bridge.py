"""Tests for the plugin-side bridge that threads the active netbox-branching
``Branch.schema_id`` into proxbox-api individual sync calls.

Issue #406 Phase 2 (plugin half). Whenever a user clicks "Sync Now" on a
NetBox model row while the netbox-branching plugin is active and a branch is
"checked out" in the current request, the plugin must:

1. Resolve the active branch's ``schema_id`` via
   :func:`netbox_proxbox.services.branch_lifecycle.get_active_branch_schema_id`
   (reads ``netbox_branching.contextvars.active_branch``).
2. Forward it to :func:`sync_individual_with_dependencies` so every
   recursive dependent sync also receives ``netbox_branch_schema_id`` as a
   query param.
3. :func:`sync_individual` materializes the param onto the outgoing HTTP
   request — proxbox-api consumes it via the ``netbox_branch_schema_id``
   query parameter pinned on the cluster route.

When no branch is active, the helper returns ``None`` and nothing changes
on the wire — preserves today's main-only behavior.
"""

from __future__ import annotations

import importlib
import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BRANCH_LIFECYCLE_PATH = (
    REPO_ROOT / "netbox_proxbox" / "services" / "branch_lifecycle.py"
)


def _install_branching_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available: bool,
    branch: object | None = None,
):
    """Stub the optional ``netbox_branching`` package and return the loaded
    ``branch_lifecycle`` module so ``get_active_branch_schema_id`` reads from
    a freshly-installed ``active_branch`` ContextVar each test."""

    for name in ("netbox_proxbox", "netbox_proxbox.services"):
        pkg = types.ModuleType(name)
        pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, pkg)

    models_pkg = types.ModuleType("netbox_proxbox.models")

    class _SettingsClass:
        @classmethod
        def get_solo(cls):
            return SimpleNamespace(branching_enabled=False)

    models_pkg.ProxboxPluginSettings = _SettingsClass
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_pkg)

    if available:
        from contextvars import ContextVar

        nb = types.ModuleType("netbox_branching")
        monkeypatch.setitem(sys.modules, "netbox_branching", nb)
        nb_ctx = types.ModuleType("netbox_branching.contextvars")
        nb_ctx.active_branch = ContextVar("active_branch", default=None)
        nb_ctx.active_branch.set(branch)
        monkeypatch.setitem(sys.modules, "netbox_branching.contextvars", nb_ctx)
    else:
        sys.modules.pop("netbox_branching", None)
        sys.modules.pop("netbox_branching.contextvars", None)
        monkeypatch.setitem(sys.modules, "netbox_branching", None)

    sys.modules.pop("netbox_proxbox.services.branch_lifecycle", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.services.branch_lifecycle",
        BRANCH_LIFECYCLE_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_proxbox.services.branch_lifecycle"] = module
    spec.loader.exec_module(module)
    return module


def test_get_active_branch_schema_id_returns_none_when_branching_unavailable(
    monkeypatch,
):
    """Optional plugin missing ⇒ helper returns ``None`` (never raises)."""
    mod = _install_branching_stubs(monkeypatch, available=False)
    assert mod.get_active_branch_schema_id() is None


def test_get_active_branch_schema_id_returns_none_when_no_branch_active(monkeypatch):
    """Branching installed but no branch checked out ⇒ ``None``."""
    mod = _install_branching_stubs(monkeypatch, available=True, branch=None)
    assert mod.get_active_branch_schema_id() is None


def test_get_active_branch_schema_id_returns_schema_id_when_branch_active(monkeypatch):
    """A real Branch in the ContextVar ⇒ string ``schema_id``."""
    branch = SimpleNamespace(name="b-1", schema_id="abcd1234")
    mod = _install_branching_stubs(monkeypatch, available=True, branch=branch)
    assert mod.get_active_branch_schema_id() == "abcd1234"


def test_get_active_branch_schema_id_treats_missing_schema_id_as_unset(monkeypatch):
    """A Branch-like object without ``.schema_id`` is treated as no branch."""
    branch = SimpleNamespace(name="b-broken")
    mod = _install_branching_stubs(monkeypatch, available=True, branch=branch)
    assert mod.get_active_branch_schema_id() is None


# ---------------------------------------------------------------------------
# individual_sync HTTP query-param forwarding
# ---------------------------------------------------------------------------


def _load_individual_sync_module(monkeypatch: pytest.MonkeyPatch):
    """Mirror of the loader in ``test_individual_sync_service.py``."""
    repo_root = pathlib.Path(__file__).resolve().parents[1]

    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)

    nbp_root = types.ModuleType("netbox_proxbox")
    nbp_root.__path__ = [str(repo_root / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", nbp_root)

    nbp_services = types.ModuleType("netbox_proxbox.services")
    nbp_services.__path__ = [str(repo_root / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", nbp_services)

    nbp_views = types.ModuleType("netbox_proxbox.views")
    nbp_views.__path__ = [str(repo_root / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", nbp_views)

    models_stub = types.ModuleType("netbox_proxbox.models")
    models_stub.FastAPIEndpoint = type(
        "FastAPIEndpoint",
        (),
        {"objects": SimpleNamespace(first=lambda: None)},
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_stub)

    utils_stub = types.ModuleType("netbox_proxbox.utils")
    utils_stub.get_fastapi_url = lambda obj: {}
    utils_stub.get_backend_auth_headers = lambda obj: {}
    utils_stub.get_first_fastapi_context = lambda **kwargs: None
    monkeypatch.setitem(sys.modules, "netbox_proxbox.utils", utils_stub)

    sys.modules.pop("netbox_proxbox.services.individual_sync", None)
    sys.modules.pop("netbox_proxbox.views.error_utils", None)
    return importlib.import_module("netbox_proxbox.services.individual_sync")


class _FakeResponse:
    def __init__(self, payload: dict):
        self.status_code = 200
        self._payload = payload
        self.text = ""
        self.url = "http://backend/sync/individual/cluster"
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_sync_individual_appends_schema_id_to_outgoing_query_params(monkeypatch):
    """``sync_individual(..., netbox_branch_schema_id=X)`` ⇒ HTTP query has X."""
    module = _load_individual_sync_module(monkeypatch)
    module.get_first_fastapi_context = lambda **kwargs: {
        "http_url": "http://backend",
        "headers": {},
        "verify_ssl": True,
    }

    captured: dict = {}

    def fake_get(
        url,
        *,
        params=None,
        headers=None,
        verify=None,
        timeout=None,
        allow_redirects=True,
    ):
        captured["params"] = dict(params or {})
        return _FakeResponse({"object_type": "cluster", "action": "unchanged"})

    monkeypatch.setattr(module.requests, "get", fake_get)

    payload, status = module.sync_individual(
        "sync/individual/cluster",
        {"cluster_name": "lab"},
        netbox_branch_schema_id="abcd1234",
    )

    assert status == 200
    assert captured["params"]["cluster_name"] == "lab"
    assert captured["params"]["netbox_branch_schema_id"] == "abcd1234"


def test_sync_individual_omits_schema_id_when_unset(monkeypatch):
    """No schema id ⇒ no ``netbox_branch_schema_id`` key on the wire."""
    module = _load_individual_sync_module(monkeypatch)
    module.get_first_fastapi_context = lambda **kwargs: {
        "http_url": "http://backend",
        "headers": {},
        "verify_ssl": True,
    }

    captured: dict = {}

    def fake_get(
        url,
        *,
        params=None,
        headers=None,
        verify=None,
        timeout=None,
        allow_redirects=True,
    ):
        captured["params"] = dict(params or {})
        return _FakeResponse({"object_type": "cluster", "action": "unchanged"})

    monkeypatch.setattr(module.requests, "get", fake_get)

    module.sync_individual("sync/individual/cluster", {"cluster_name": "lab"})

    assert "netbox_branch_schema_id" not in captured["params"]


def test_sync_individual_with_dependencies_threads_schema_id_through_recursion(
    monkeypatch,
):
    """Recursive dependency syncs inherit the same schema id."""
    module = _load_individual_sync_module(monkeypatch)

    calls: list[tuple[str, dict]] = []

    def fake_sync(
        path,
        query_params=None,
        netbox_branch_schema_id=None,
        fastapi_endpoint_id=None,
        proxmox_endpoint_ids=None,
    ):
        params = dict(query_params or {})
        if netbox_branch_schema_id is not None:
            params["__schema_id_kwarg__"] = netbox_branch_schema_id
        calls.append((path, params))
        if path == "sync/individual/vm":
            return (
                {
                    "object_type": "vm",
                    "action": "updated",
                    "dependencies_synced": [
                        {"object_type": "node", "name": "pve01", "action": "created"}
                    ],
                },
                200,
            )
        return (
            {"object_type": "node", "action": "updated", "dependencies_synced": []},
            200,
        )

    monkeypatch.setattr(module, "sync_individual", fake_sync)

    _, status, _ = module.sync_individual_with_dependencies(
        "sync/individual/vm",
        {"cluster_name": "lab", "node": "pve01", "type": "qemu", "vmid": 101},
        netbox_branch_schema_id="abcd1234",
    )

    assert status == 200
    # Both the top-level call and the dependent node call must carry the
    # schema id forward.
    assert all(call[1].get("__schema_id_kwarg__") == "abcd1234" for call in calls)
    assert any(call[0] == "sync/individual/node" for call in calls)
