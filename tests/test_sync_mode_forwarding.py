"""Focused tests for sync-mode query forwarding to proxbox-api."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_constants():
    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_constants_sync_mode_forwarding",
        REPO_ROOT / "netbox_proxbox" / "constants.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sync_stages_module(monkeypatch):
    """Load sync_stages.py with all heavy imports stubbed."""
    constants = _load_constants()
    fields = tuple(constants.OVERWRITE_FIELDS)
    state: dict[str, dict] = {"global": {name: True for name in fields}}

    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    constants_mod = types.ModuleType("netbox_proxbox.constants")
    constants_mod.OVERWRITE_FIELDS = constants.OVERWRITE_FIELDS
    constants_mod.SYNC_MODE_FIELDS = constants.SYNC_MODE_FIELDS
    constants_mod.SYNC_MODE_RESOURCE_TYPES = constants.SYNC_MODE_RESOURCE_TYPES
    constants_mod.SYNC_MODE_HIERARCHY = constants.SYNC_MODE_HIERARCHY
    monkeypatch.setitem(sys.modules, "netbox_proxbox.constants", constants_mod)

    choices_mod = types.ModuleType("netbox_proxbox.choices")
    sync_mode = SimpleNamespace(
        ALWAYS="always", BOOTSTRAP_ONLY="bootstrap_only", DISABLED="disabled"
    )
    choices_mod.SyncModeChoices = sync_mode
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

    bootstrap_mod = types.ModuleType("netbox_proxbox.netbox_bootstrap")
    bootstrap_mod.BOOTSTRAP_ONLY_TAG_SLUG = "bootstrap-only"
    bootstrap_mod.ensure_proxbox_tags = lambda: {}
    monkeypatch.setitem(sys.modules, "netbox_proxbox.netbox_bootstrap", bootstrap_mod)

    class _ProxboxPluginSettings:
        @classmethod
        def get_solo(cls):
            ns = SimpleNamespace(
                use_guest_agent_interface_name=True,
                proxbox_fetch_max_concurrency=8,
                ignore_ipv6_link_local_addresses=True,
                primary_ip_preference="ipv4",
                **{f: "always" for f in constants.SYNC_MODE_FIELDS},
            )
            ns.__dict__.update(state["global"])
            return ns

    class _Manager:
        def filter(self, **kw):
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
    netbox_jobs_mod.Job = object
    monkeypatch.setitem(sys.modules, "netbox.jobs", netbox_jobs_mod)

    for mod_name, filename in [
        ("netbox_proxbox.sync_types", "sync_types.py"),
        ("netbox_proxbox.sync_params", "sync_params.py"),
        ("netbox_proxbox.sync_ownership", "sync_ownership.py"),
    ]:
        sys.modules.pop(mod_name, None)
        spec = importlib.util.spec_from_file_location(
            mod_name, REPO_ROOT / "netbox_proxbox" / filename
        )
        assert spec and spec.loader
        m = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = m
        spec.loader.exec_module(m)

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


class TestSyncModeForwarding:
    def test_virtual_machines_stage_forwards_vm_and_template_modes(
        self, sync_stages_module
    ):
        m = sync_stages_module
        m._stubs["global"].update(
            {
                "sync_mode_vm": "bootstrap_only",
                "sync_mode_vm_template": "disabled",
            }
        )

        base_query = m._build_base_query_params(
            proxmox_endpoint_ids=None,
            netbox_endpoint_ids=None,
        )
        params = m._build_stage_query_params(
            base_query=base_query,
            sync_type=m.SyncTypeChoices.VIRTUAL_MACHINES,
            target_vm_ids=[],
        )

        assert params["sync_mode_vm"] == "bootstrap_only"
        assert params["sync_mode_vm_template"] == "disabled"

    def test_mac_disabled_forwards_to_vm_interfaces_stage(self, sync_stages_module):
        m = sync_stages_module
        params = m._build_stage_query_params(
            base_query={},
            sync_type=m.SyncTypeChoices.VM_INTERFACES,
            target_vm_ids=[],
            mac_disabled=True,
        )
        assert params.get("sync_vm_interface_macs") == "false"

    def test_ip_disabled_inline_forwards_assign_flag(self, sync_stages_module):
        m = sync_stages_module
        params = m._build_stage_query_params(
            base_query={},
            sync_type=m.SyncTypeChoices.VIRTUAL_MACHINES,
            target_vm_ids=[],
            disable_vm_network_on_vm_stage=False,
            ip_disabled=True,
        )
        assert "sync_vm_network" not in params
        assert params.get("assign_vm_interface_ips") == "false"
