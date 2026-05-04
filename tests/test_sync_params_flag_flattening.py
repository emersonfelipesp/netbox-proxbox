"""Tests that ``sync_stages._build_base_query_params`` flattens 22 overwrite flags.

The plugin sends overwrite flags to the FastAPI backend as flat query string
keys (one ``overwrite_*`` key per field, value ``"true"`` / ``"false"``). This
mirrors the backend's ``Annotated[SyncOverwriteFlags, Query()]`` flattening on
the receive side. If a future change drops a flag from this serialization, the
backend will silently fall back to its default (always overwrite) — so we lock
the contract here.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_overwrite_fields() -> tuple[str, ...]:
    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_constants_for_flattening",
        REPO_ROOT / "netbox_proxbox" / "constants.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.OVERWRITE_FIELDS)


@pytest.fixture
def sync_stages_module(monkeypatch):
    """Load sync_stages.py with all heavy imports stubbed."""
    fields = _load_overwrite_fields()
    state = {"global": {name: True for name in fields}}

    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    constants_mod = types.ModuleType("netbox_proxbox.constants")
    constants_mod.OVERWRITE_FIELDS = fields
    monkeypatch.setitem(sys.modules, "netbox_proxbox.constants", constants_mod)

    choices_mod = types.ModuleType("netbox_proxbox.choices")
    choices_mod.SyncTypeChoices = SimpleNamespace(
        ALL="all",
        VIRTUAL_MACHINES="virtual-machines",
        VIRTUAL_MACHINES_BACKUPS="vm-backups",
        VIRTUAL_MACHINES_SNAPSHOTS="vm-snapshots",
        VIRTUAL_MACHINES_DISKS="vm-disks",
        DEVICES="devices",
        STORAGE="storage",
        TASK_HISTORY="task-history",
        NETWORK_INTERFACES="network-interfaces",
        VM_INTERFACES="vm-interfaces",
        IP_ADDRESSES="ip-addresses",
        REPLICATIONS="replications",
        BACKUP_ROUTINES="backup-routines",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)

    class _ProxboxPluginSettings:
        @classmethod
        def get_solo(cls):
            return SimpleNamespace(
                use_guest_agent_interface_name=True,
                proxbox_fetch_max_concurrency=8,
                ignore_ipv6_link_local_addresses=True,
                primary_ip_preference="ipv4",
                **state["global"],
            )

    class _Manager:
        def filter(self, **kwargs):
            return self

        def first(self):
            return None

    class _ProxmoxEndpoint:
        objects = _Manager()

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxboxPluginSettings = _ProxboxPluginSettings
    models_mod.ProxmoxEndpoint = _ProxmoxEndpoint
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    netbox_jobs_mod = types.ModuleType("netbox.jobs")

    class _Job:
        pass

    netbox_jobs_mod.Job = _Job
    monkeypatch.setitem(sys.modules, "netbox.jobs", netbox_jobs_mod)

    # Load sync_types.py first since sync_stages imports from it.
    sys.modules.pop("netbox_proxbox.sync_types", None)
    spec_st = importlib.util.spec_from_file_location(
        "netbox_proxbox.sync_types",
        REPO_ROOT / "netbox_proxbox" / "sync_types.py",
    )
    assert spec_st and spec_st.loader
    mod_st = importlib.util.module_from_spec(spec_st)
    sys.modules["netbox_proxbox.sync_types"] = mod_st
    spec_st.loader.exec_module(mod_st)

    sys.modules.pop("netbox_proxbox.sync_params", None)
    spec_sp = importlib.util.spec_from_file_location(
        "netbox_proxbox.sync_params",
        REPO_ROOT / "netbox_proxbox" / "sync_params.py",
    )
    assert spec_sp and spec_sp.loader
    mod_sp = importlib.util.module_from_spec(spec_sp)
    sys.modules["netbox_proxbox.sync_params"] = mod_sp
    spec_sp.loader.exec_module(mod_sp)

    sys.modules.pop("netbox_proxbox.sync_ownership", None)
    spec_so = importlib.util.spec_from_file_location(
        "netbox_proxbox.sync_ownership",
        REPO_ROOT / "netbox_proxbox" / "sync_ownership.py",
    )
    assert spec_so and spec_so.loader
    mod_so = importlib.util.module_from_spec(spec_so)
    sys.modules["netbox_proxbox.sync_ownership"] = mod_so
    spec_so.loader.exec_module(mod_so)

    sys.modules.pop("netbox_proxbox.sync_stages", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.sync_stages",
        REPO_ROOT / "netbox_proxbox" / "sync_stages.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_proxbox.sync_stages"] = module
    spec.loader.exec_module(module)
    module._stubs = state  # type: ignore[attr-defined]
    return module


def test_build_base_query_params_includes_all_22_overwrite_keys(sync_stages_module):
    fields = _load_overwrite_fields()

    base_query = sync_stages_module._build_base_query_params(
        proxmox_endpoint_ids=None,
        netbox_endpoint_ids=None,
    )

    for name in fields:
        assert name in base_query, f"missing flag {name} in flattened query"
    overwrite_keys = [k for k in base_query if k.startswith("overwrite_")]
    assert len(overwrite_keys) == 22


def test_build_base_query_params_serializes_true_false_strings(sync_stages_module):
    fields = _load_overwrite_fields()
    sync_stages_module._stubs["global"] = {
        name: (idx % 2 == 0) for idx, name in enumerate(fields)
    }

    base_query = sync_stages_module._build_base_query_params(
        proxmox_endpoint_ids=None,
        netbox_endpoint_ids=None,
    )

    for idx, name in enumerate(fields):
        expected = "true" if idx % 2 == 0 else "false"
        assert base_query[name] == expected
        assert isinstance(base_query[name], str)


def test_build_base_query_params_falls_back_when_multiple_endpoints(sync_stages_module):
    """With >1 endpoint in scope we cannot encode a per-endpoint map; use global."""
    fields = _load_overwrite_fields()
    sync_stages_module._stubs["global"] = {name: False for name in fields}

    base_query = sync_stages_module._build_base_query_params(
        proxmox_endpoint_ids=["1", "2"],
        netbox_endpoint_ids=None,
    )

    for name in fields:
        assert base_query[name] == "false"
    assert base_query["proxmox_endpoint_ids"] == "1,2"


def test_build_base_query_params_includes_other_runtime_settings(sync_stages_module):
    base_query = sync_stages_module._build_base_query_params(
        proxmox_endpoint_ids=None,
        netbox_endpoint_ids=None,
    )

    assert base_query["use_guest_agent_interface_name"] in {"true", "false"}
    assert base_query["ignore_ipv6_link_local_addresses"] in {"true", "false"}
    assert base_query["fetch_max_concurrency"].isdigit()
    assert base_query["primary_ip_preference"] in {"ipv4", "ipv6"}
