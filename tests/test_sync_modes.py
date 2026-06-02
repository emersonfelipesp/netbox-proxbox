"""Tests for per-resource SyncMode controls.

Covers:
- SyncModeChoices values (always / bootstrap_only / disabled) via AST
- SYNC_MODE_FIELDS constant coverage
- Module-level sync mode variables in sync_stages
- VM resource sync gating (_should_sync_vm_resource)
- Bootstrap-only tag detection helpers
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# ── AST-based choices inspection ──────────────────────────────────────────────


def _load_choices_ast():
    """Parse choices.py with AST — no Django import needed."""
    src = (REPO_ROOT / "netbox_proxbox" / "choices.py").read_text()
    tree = ast.parse(src)
    classes: dict[str, dict[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            attrs: dict[str, str] = {}
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and isinstance(
                    stmt.value, ast.Constant
                ):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            attrs[target.id] = stmt.value.value
            classes[node.name] = attrs
    return classes


def _load_constants():
    """Load constants.py without Django (no non-stdlib imports)."""
    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_constants_sync_modes",
        REPO_ROOT / "netbox_proxbox" / "constants.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── sync_stages fixture ────────────────────────────────────────────────────────


@pytest.fixture
def sync_stages_module(monkeypatch):
    """Load sync_stages.py with all heavy imports stubbed."""
    constants = _load_constants()
    fields = tuple(constants.OVERWRITE_FIELDS)

    # Shared mutable state for stub settings
    state: dict[str, dict] = {"global": {name: True for name in fields}}

    # --- package root ---
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    # --- constants ---
    constants_mod = types.ModuleType("netbox_proxbox.constants")
    constants_mod.OVERWRITE_FIELDS = constants.OVERWRITE_FIELDS
    constants_mod.SYNC_MODE_FIELDS = constants.SYNC_MODE_FIELDS
    constants_mod.SYNC_MODE_RESOURCE_TYPES = constants.SYNC_MODE_RESOURCE_TYPES
    monkeypatch.setitem(sys.modules, "netbox_proxbox.constants", constants_mod)

    # --- choices ---
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

    # --- bootstrap module ---
    bootstrap_mod = types.ModuleType("netbox_proxbox.netbox_bootstrap")
    bootstrap_mod.BOOTSTRAP_ONLY_TAG_SLUG = "bootstrap-only"
    bootstrap_mod.ensure_proxbox_tags = lambda: {}
    monkeypatch.setitem(sys.modules, "netbox_proxbox.netbox_bootstrap", bootstrap_mod)

    # --- models ---
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

    # --- netbox.jobs ---
    netbox_jobs_mod = types.ModuleType("netbox.jobs")
    netbox_jobs_mod.Job = object
    monkeypatch.setitem(sys.modules, "netbox.jobs", netbox_jobs_mod)

    # Load sync_types → sync_params → sync_ownership → sync_stages in order
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

    # --- sync_stages ---
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


# ── SyncModeChoices (AST) ──────────────────────────────────────────────────────


class TestSyncModeChoicesAST:
    def test_sync_mode_choices_class_exists(self):
        classes = _load_choices_ast()
        assert "SyncModeChoices" in classes, "SyncModeChoices class not in choices.py"

    def test_always_value(self):
        classes = _load_choices_ast()
        attrs = classes["SyncModeChoices"]
        assert attrs.get("ALWAYS") == "always"

    def test_bootstrap_only_value(self):
        classes = _load_choices_ast()
        attrs = classes["SyncModeChoices"]
        assert attrs.get("BOOTSTRAP_ONLY") == "bootstrap_only"

    def test_disabled_value(self):
        classes = _load_choices_ast()
        attrs = classes["SyncModeChoices"]
        assert attrs.get("DISABLED") == "disabled"


# ── SYNC_MODE_FIELDS constant ──────────────────────────────────────────────────


class TestSyncModeConstants:
    def test_all_six_resource_types_present(self):
        constants = _load_constants()
        expected = {"vm", "vm_template", "cluster", "node", "storage", "ip_address"}
        assert expected <= set(constants.SYNC_MODE_RESOURCE_TYPES)

    def test_six_sync_mode_fields(self):
        constants = _load_constants()
        expected = {
            "sync_mode_vm",
            "sync_mode_vm_template",
            "sync_mode_cluster",
            "sync_mode_node",
            "sync_mode_storage",
            "sync_mode_ip_address",
        }
        assert expected <= set(constants.SYNC_MODE_FIELDS)


# ── sync_stages module-level defaults ─────────────────────────────────────────


class TestSyncStagesDefaults:
    def test_sync_mode_vm_default_is_always(self, sync_stages_module):
        assert sync_stages_module.sync_mode_vm == "always"

    def test_sync_mode_vm_template_default_is_always(self, sync_stages_module):
        assert sync_stages_module.sync_mode_vm_template == "always"

    def test_sync_mode_cluster_default_is_always(self, sync_stages_module):
        assert sync_stages_module.sync_mode_cluster == "always"

    def test_sync_mode_node_default_is_always(self, sync_stages_module):
        assert sync_stages_module.sync_mode_node == "always"

    def test_sync_mode_storage_default_is_always(self, sync_stages_module):
        assert sync_stages_module.sync_mode_storage == "always"

    def test_sync_mode_ip_address_default_is_always(self, sync_stages_module):
        assert sync_stages_module.sync_mode_ip_address == "always"


# ── VM resource gating ─────────────────────────────────────────────────────────


class TestShouldSyncVMResource:
    def test_non_template_allowed_when_vm_mode_always(self, sync_stages_module):
        m = sync_stages_module
        m.sync_mode_vm = "always"
        m.sync_mode_vm_template = "always"
        resource = SimpleNamespace(template=False)
        assert m._vm_resource_allowed_by_sync_mode(resource) is True

    def test_template_allowed_when_vm_template_mode_always(self, sync_stages_module):
        m = sync_stages_module
        m.sync_mode_vm = "always"
        m.sync_mode_vm_template = "always"
        resource = SimpleNamespace(template=True)
        assert m._vm_resource_allowed_by_sync_mode(resource) is True

    def test_template_blocked_when_vm_template_disabled(self, sync_stages_module):
        m = sync_stages_module
        m.sync_mode_vm = "always"
        m.sync_mode_vm_template = "disabled"
        resource = SimpleNamespace(template=True)
        assert m._vm_resource_allowed_by_sync_mode(resource) is False

    def test_non_template_blocked_when_vm_disabled(self, sync_stages_module):
        m = sync_stages_module
        m.sync_mode_vm = "disabled"
        m.sync_mode_vm_template = "always"
        resource = SimpleNamespace(template=False)
        assert m._vm_resource_allowed_by_sync_mode(resource) is False

    def test_both_disabled_blocks_all(self, sync_stages_module):
        m = sync_stages_module
        m.sync_mode_vm = "disabled"
        m.sync_mode_vm_template = "disabled"
        for is_template in (True, False):
            resource = SimpleNamespace(template=is_template)
            assert m._vm_resource_allowed_by_sync_mode(resource) is False


# ── Bootstrap-only helpers ─────────────────────────────────────────────────────


def _make_tagged_obj(has_tag: bool):
    """Build a stub with tags.filter().exists() returning `has_tag`."""
    mock_qs = SimpleNamespace(exists=lambda: has_tag)
    return SimpleNamespace(tags=SimpleNamespace(filter=lambda **kw: mock_qs))


class TestBootstrapOnlyHelpers:
    def test_has_bootstrap_only_tag_true_when_tag_present(self, sync_stages_module):
        obj = _make_tagged_obj(True)
        assert sync_stages_module._has_bootstrap_only_tag(obj) is True

    def test_has_bootstrap_only_tag_false_when_tag_absent(self, sync_stages_module):
        obj = _make_tagged_obj(False)
        assert sync_stages_module._has_bootstrap_only_tag(obj) is False

    def test_skip_existing_when_bootstrap_mode_and_tag_present(
        self, sync_stages_module
    ):
        obj = _make_tagged_obj(True)
        assert (
            sync_stages_module._bootstrap_only_should_skip_existing(
                obj, "bootstrap_only"
            )
            is True
        )

    def test_no_skip_when_mode_always_even_if_tag_present(self, sync_stages_module):
        obj = _make_tagged_obj(True)
        assert (
            sync_stages_module._bootstrap_only_should_skip_existing(obj, "always")
            is False
        )

    def test_no_skip_when_bootstrap_mode_but_no_tag(self, sync_stages_module):
        obj = _make_tagged_obj(False)
        assert (
            sync_stages_module._bootstrap_only_should_skip_existing(
                obj, "bootstrap_only"
            )
            is False
        )
