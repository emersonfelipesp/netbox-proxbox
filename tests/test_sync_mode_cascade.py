"""Focused tests for sync-mode parent-child cascade behavior."""

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
        "_netbox_proxbox_constants_sync_mode_cascade",
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


def _set_modes(module, **resource_modes: str) -> None:
    modes = {field_name: "always" for field_name in module.SYNC_MODE_FIELDS}
    modes.update(
        {
            f"sync_mode_{resource_type}": mode
            for resource_type, mode in resource_modes.items()
        }
    )
    module._set_sync_mode_vars(modes)


class TestSyncModeCascadeResolver:
    def test_vm_interface_disabled_disables_ip_and_mac(self, sync_stages_module):
        m = sync_stages_module
        _set_modes(m, vm_interface="disabled")
        effective = m._active_sync_modes()
        assert effective["sync_mode_vm_interface"] == "disabled"
        assert effective["sync_mode_ip_address"] == "disabled"
        assert effective["sync_mode_mac"] == "disabled"

    def test_ip_disabled_does_not_disable_interface_or_mac(self, sync_stages_module):
        m = sync_stages_module
        _set_modes(m, ip_address="disabled")
        effective = m._active_sync_modes()
        assert effective["sync_mode_ip_address"] == "disabled"
        assert effective["sync_mode_vm_interface"] == "always"
        assert effective["sync_mode_mac"] == "always"

    def test_mac_disabled_does_not_disable_interface_or_ip(self, sync_stages_module):
        m = sync_stages_module
        _set_modes(m, mac="disabled")
        effective = m._active_sync_modes()
        assert effective["sync_mode_mac"] == "disabled"
        assert effective["sync_mode_vm_interface"] == "always"
        assert effective["sync_mode_ip_address"] == "always"

    def test_both_vm_modes_disabled_disables_network_descendants(
        self, sync_stages_module
    ):
        m = sync_stages_module
        _set_modes(m, vm="disabled", vm_template="disabled")
        effective = m._active_sync_modes()
        assert effective["sync_mode_vm_interface"] == "disabled"
        assert effective["sync_mode_ip_address"] == "disabled"
        assert effective["sync_mode_mac"] == "disabled"

    def test_cluster_disabled_disables_node(self, sync_stages_module):
        m = sync_stages_module
        _set_modes(m, cluster="disabled")
        effective = m._active_sync_modes()
        assert effective["sync_mode_cluster"] == "disabled"
        assert effective["sync_mode_node"] == "disabled"

    def test_node_disabled_does_not_disable_cluster(self, sync_stages_module):
        m = sync_stages_module
        _set_modes(m, node="disabled")
        effective = m._active_sync_modes()
        assert effective["sync_mode_node"] == "disabled"
        assert effective["sync_mode_cluster"] == "always"


class TestStageSkipReasonCascade:
    def test_vm_interfaces_skipped_when_vm_interface_disabled(
        self, sync_stages_module
    ):
        m = sync_stages_module
        _set_modes(m, vm_interface="disabled")
        assert m._stage_skip_reason(m.SyncTypeChoices.VM_INTERFACES)

    def test_vm_interfaces_skipped_when_both_vm_modes_disabled(
        self, sync_stages_module
    ):
        m = sync_stages_module
        _set_modes(m, vm="disabled", vm_template="disabled")
        assert m._stage_skip_reason(m.SyncTypeChoices.VM_INTERFACES)

    def test_ip_addresses_skipped_when_ip_disabled(self, sync_stages_module):
        m = sync_stages_module
        _set_modes(m, ip_address="disabled")
        assert m._stage_skip_reason(m.SyncTypeChoices.IP_ADDRESSES)

    def test_ip_addresses_skipped_when_vm_interface_disabled(
        self, sync_stages_module
    ):
        m = sync_stages_module
        _set_modes(m, vm_interface="disabled")
        assert m._stage_skip_reason(m.SyncTypeChoices.IP_ADDRESSES)

    def test_vm_interfaces_not_skipped_when_only_ip_disabled(
        self, sync_stages_module
    ):
        m = sync_stages_module
        _set_modes(m, ip_address="disabled")
        assert m._stage_skip_reason(m.SyncTypeChoices.VM_INTERFACES) is None
