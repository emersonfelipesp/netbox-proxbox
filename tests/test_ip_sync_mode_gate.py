"""Tests for the IP-sync-mode gate on the virtual-machines stage.

When sync_mode_ip_address=disabled but VM interface sync remains active, the
virtual-machines stage keeps inline interface creation enabled and forwards
assign_vm_interface_ips=false to proxbox-api. Dedicated interface/IP stages still
disable inline VM network work with sync_vm_network=false.
"""

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
        "_netbox_proxbox_constants_ip_gate",
        REPO_ROOT / "netbox_proxbox" / "constants.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sync_stages_module(monkeypatch):
    """Load sync_stages.py with all heavy imports stubbed, same as test_sync_modes."""
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


# ── _build_stage_query_params helper ──────────────────────────────────────────


def _build(
    module,
    sync_type: str,
    *,
    disable_vm_network: bool,
    ip_disabled: bool = False,
    mac_disabled: bool = False,
) -> dict:
    """Call _build_stage_query_params with a minimal base_query."""
    return module._build_stage_query_params(
        base_query={},
        sync_type=sync_type,
        target_vm_ids=[],
        disable_vm_network_on_vm_stage=disable_vm_network,
        ip_disabled=ip_disabled,
        mac_disabled=mac_disabled,
    )


class TestBuildStageQueryParamsVMNetwork:
    def test_sync_vm_network_false_when_flag_set_for_vm_stage(self, sync_stages_module):
        m = sync_stages_module
        STC = m.SyncTypeChoices
        params = _build(m, STC.VIRTUAL_MACHINES, disable_vm_network=True)
        assert params.get("sync_vm_network") == "false"

    def test_sync_vm_network_absent_when_flag_clear_for_vm_stage(
        self, sync_stages_module
    ):
        m = sync_stages_module
        STC = m.SyncTypeChoices
        params = _build(m, STC.VIRTUAL_MACHINES, disable_vm_network=False)
        assert "sync_vm_network" not in params

    def test_sync_vm_network_absent_for_non_vm_stage_even_with_flag(
        self, sync_stages_module
    ):
        m = sync_stages_module
        STC = m.SyncTypeChoices
        params = _build(m, STC.IP_ADDRESSES, disable_vm_network=True)
        assert "sync_vm_network" not in params


# ── IP-mode gate — the core regression ────────────────────────────────────────


class TestIPSyncModeGate:
    """Verify the fix for GitHub #556.

    When sync_mode_ip_address=disabled, VM-only sync forwards a narrower
    assign_vm_interface_ips=false flag. Full syncs with dedicated interface/IP
    stages still send sync_vm_network=false on the VM stage.
    """

    def _compute_flag(self, module, stages: list[str]) -> bool:
        """Mirror the production logic from _run_all_stages_sync."""
        STC = module.SyncTypeChoices
        SMC = module.SyncModeChoices
        return STC.VIRTUAL_MACHINES in stages and (
            STC.VM_INTERFACES in stages
            or STC.IP_ADDRESSES in stages
            or module._sync_mode_for_resource("vm_interface") == SMC.DISABLED
        )

    def test_flag_false_when_ip_mode_disabled_vm_only_stages(self, sync_stages_module):
        """VM-only sync: IP mode alone no longer disables all VM network sync."""
        m = sync_stages_module
        m.sync_mode_ip_address = "disabled"
        stages = [m.SyncTypeChoices.VIRTUAL_MACHINES]
        assert self._compute_flag(m, stages) is False

    def test_flag_false_when_ip_mode_always_vm_only_stages(self, sync_stages_module):
        """VM-only sync: flag is False when ip_address mode is always (original behaviour)."""
        m = sync_stages_module
        m.sync_mode_ip_address = "always"
        stages = [m.SyncTypeChoices.VIRTUAL_MACHINES]
        assert self._compute_flag(m, stages) is False

    def test_flag_true_when_ip_addresses_stage_present_regardless_of_mode(
        self, sync_stages_module
    ):
        """Full sync: flag is True because IP_ADDRESSES stage is present (existing behaviour)."""
        m = sync_stages_module
        m.sync_mode_ip_address = "always"
        stages = [m.SyncTypeChoices.VIRTUAL_MACHINES, m.SyncTypeChoices.IP_ADDRESSES]
        assert self._compute_flag(m, stages) is True

    def test_flag_true_when_vm_interfaces_stage_present_regardless_of_ip_mode(
        self, sync_stages_module
    ):
        """Full sync: flag is True because VM_INTERFACES stage is present."""
        m = sync_stages_module
        m.sync_mode_ip_address = "always"
        stages = [m.SyncTypeChoices.VIRTUAL_MACHINES, m.SyncTypeChoices.VM_INTERFACES]
        assert self._compute_flag(m, stages) is True

    def test_flag_false_when_no_vm_stage_even_if_ip_disabled(self, sync_stages_module):
        """No VM stage: flag must remain False even when ip_address is disabled."""
        m = sync_stages_module
        m.sync_mode_ip_address = "disabled"
        stages = [m.SyncTypeChoices.IP_ADDRESSES]
        assert self._compute_flag(m, stages) is False

    def test_assign_vm_interface_ips_false_sent_when_ip_disabled_vm_only(
        self, sync_stages_module
    ):
        """End-to-end: verify the narrower query param when ip_mode=disabled, VM-only."""
        m = sync_stages_module
        m.sync_mode_ip_address = "disabled"
        stages = [m.SyncTypeChoices.VIRTUAL_MACHINES]
        flag = self._compute_flag(m, stages)
        params = _build(
            m,
            m.SyncTypeChoices.VIRTUAL_MACHINES,
            disable_vm_network=flag,
            ip_disabled=m._sync_mode_for_resource("ip_address") == "disabled",
        )
        assert "sync_vm_network" not in params
        assert params.get("assign_vm_interface_ips") == "false", (
            "assign_vm_interface_ips must be 'false' when only IP sync is disabled"
        )

    def test_sync_vm_network_not_sent_when_ip_always_vm_only(self, sync_stages_module):
        """End-to-end: sync_vm_network absent when ip_mode=always, VM-only."""
        m = sync_stages_module
        m.sync_mode_ip_address = "always"
        stages = [m.SyncTypeChoices.VIRTUAL_MACHINES]
        flag = self._compute_flag(m, stages)
        params = _build(m, m.SyncTypeChoices.VIRTUAL_MACHINES, disable_vm_network=flag)
        assert "sync_vm_network" not in params
