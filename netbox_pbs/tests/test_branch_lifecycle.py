"""AST-based contract tests for the PR C3 branch_lifecycle module.

Verifies that ``netbox_pbs.services.branch_lifecycle`` exposes the same six
canonical functions used by ``netbox_proxbox`` and reads its config from
``PBSPluginSettings.get_solo()`` (not the proxbox settings model). The tests
are AST-driven so the per-commit gate runs offline.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BRANCH_LIFECYCLE = REPO_ROOT / "netbox_pbs" / "services" / "branch_lifecycle.py"


REQUIRED_FUNCTIONS = (
    "is_branching_available",
    "get_active_branch_schema_id",
    "branching_enabled_settings",
    "create_and_provision_branch",
    "branch_has_conflicts",
    "merge_branch",
)


def _module() -> ast.Module:
    return ast.parse(BRANCH_LIFECYCLE.read_text(encoding="utf-8"))


def _function(module: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def test_branch_lifecycle_module_exists():
    assert BRANCH_LIFECYCLE.is_file(), (
        f"missing {BRANCH_LIFECYCLE.relative_to(REPO_ROOT)}"
    )


def test_branch_lifecycle_defines_all_six_canonical_functions():
    module = _module()
    for name in REQUIRED_FUNCTIONS:
        assert _function(module, name) is not None, (
            f"netbox_pbs.services.branch_lifecycle must define {name}()"
        )


def test_branching_enabled_settings_uses_pbs_plugin_settings():
    """The settings loader must read PBSPluginSettings, not the proxbox one."""
    text = BRANCH_LIFECYCLE.read_text(encoding="utf-8")
    assert "from netbox_pbs.models import PBSPluginSettings" in text, (
        "branch_lifecycle.py must import PBSPluginSettings from netbox_pbs.models"
    )
    assert "PBSPluginSettings.get_solo()" in text, (
        "branching_enabled_settings() must call PBSPluginSettings.get_solo()"
    )
    assert "ProxboxPluginSettings" not in text, (
        "branch_lifecycle.py must not reference ProxboxPluginSettings — "
        "the PBS plugin owns its own settings row"
    )


def test_create_and_provision_branch_polls_until_ready():
    """The provisioning helper must wait for BranchStatusChoices.READY."""
    text = BRANCH_LIFECYCLE.read_text(encoding="utf-8")
    assert "BranchStatusChoices.READY" in text, (
        "create_and_provision_branch must poll until READY"
    )
    assert "BranchStatusChoices.FAILED" in text, (
        "create_and_provision_branch must surface FAILED status"
    )
    assert "branch.provision(user=user)" in text, (
        "create_and_provision_branch must call branch.provision(user=user)"
    )


def test_merge_branch_respects_on_conflict_policy():
    text = BRANCH_LIFECYCLE.read_text(encoding="utf-8")
    assert 'on_conflict != "acknowledge"' in text, (
        "merge_branch must refuse merge on conflicts unless on_conflict=='acknowledge'"
    )
    assert "branch.merge(user=user)" in text, (
        "merge_branch must call branch.merge(user=user)"
    )


def test_get_active_branch_schema_id_reads_contextvar():
    text = BRANCH_LIFECYCLE.read_text(encoding="utf-8")
    assert "from netbox_branching.contextvars import active_branch" in text, (
        "get_active_branch_schema_id must read netbox_branching.contextvars.active_branch"
    )
