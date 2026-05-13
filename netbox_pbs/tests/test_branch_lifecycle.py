"""AST-based contract tests for the branch_lifecycle shim.

Per the 2026-05-13 pivot, ``netbox_pbs.services.branch_lifecycle`` is a
**shim** that re-exports the canonical primitives from
``netbox_proxbox.services.branch_lifecycle`` and defines only one
PBS-specific function (``branching_enabled_settings``) which reads from
``PBSPluginSettings.get_solo()`` rather than the proxbox settings model.

The tests are AST-driven so the per-commit gate runs offline.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BRANCH_LIFECYCLE = REPO_ROOT / "netbox_pbs" / "services" / "branch_lifecycle.py"


REEXPORTED_NAMES = (
    "is_branching_available",
    "get_active_branch_schema_id",
    "create_and_provision_branch",
    "branch_has_conflicts",
    "merge_branch",
)


def _module() -> ast.Module:
    return ast.parse(BRANCH_LIFECYCLE.read_text(encoding="utf-8"))


def test_branch_lifecycle_module_exists():
    assert BRANCH_LIFECYCLE.is_file(), (
        f"missing {BRANCH_LIFECYCLE.relative_to(REPO_ROOT)}"
    )


def test_shim_reexports_canonical_primitives_from_netbox_proxbox():
    """The shim must import all five canonical names from netbox_proxbox."""
    module = _module()
    reexported: set[str] = set()
    for node in module.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "netbox_proxbox.services.branch_lifecycle"
        ):
            reexported.update(alias.name for alias in node.names)
    missing = set(REEXPORTED_NAMES) - reexported
    assert not missing, (
        f"branch_lifecycle.py must re-export {sorted(missing)} from "
        "netbox_proxbox.services.branch_lifecycle"
    )


def test_shim_defines_only_branching_enabled_settings_locally():
    """The shim must define ``branching_enabled_settings`` and nothing else."""
    module = _module()
    local_funcs = {
        node.name for node in module.body if isinstance(node, ast.FunctionDef)
    }
    assert "branching_enabled_settings" in local_funcs, (
        "shim must define branching_enabled_settings() locally so it can "
        "read PBSPluginSettings instead of ProxboxPluginSettings"
    )
    # No other primitives should be redefined — they come from netbox_proxbox.
    redefined = local_funcs & set(REEXPORTED_NAMES)
    assert not redefined, (
        f"shim must not redefine {sorted(redefined)} — re-export from "
        "netbox_proxbox instead"
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


def test_all_includes_branching_enabled_settings_and_reexports():
    """``__all__`` must surface the shim's public API."""
    module = _module()
    for stmt in module.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "__all__"
        ):
            values: set[str] = set()
            if isinstance(stmt.value, (ast.Tuple, ast.List)):
                values = {
                    elt.value
                    for elt in stmt.value.elts
                    if isinstance(elt, ast.Constant)
                    and isinstance(elt.value, str)
                }
            expected = set(REEXPORTED_NAMES) | {"branching_enabled_settings"}
            missing = expected - values
            assert not missing, f"__all__ missing names: {sorted(missing)}"
            return
    raise AssertionError("branch_lifecycle.py must declare __all__")
