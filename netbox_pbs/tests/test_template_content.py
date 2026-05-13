"""AST tests for the cross-plugin ``template_content`` cross-link.

The cross-link panel (issue #325, sub-PR C4) is presentation-only: the
panel lists rows that match a natural key (vmid + creation_time)
between :class:`netbox_proxbox.models.VMBackup` and
:class:`netbox_pbs.models.PBSSnapshot`. No FK, no schema change, no
signal-backed backfill.

These tests pin:

* ``template_extensions`` is an unconditional module-level list. Per the
  2026-05-13 pivot, ``netbox_proxbox`` is declared in
  ``PBSConfig.required_plugins``, so the cross-link is always live and the
  old ``apps.is_installed("netbox_proxbox")`` guard is gone.
* Both extension classes target the correct host model and define
  ``right_page``.
* The two panel templates exist.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_CONTENT_PATH = REPO_ROOT / "netbox_pbs" / "template_content.py"
PANEL_DIR = REPO_ROOT / "netbox_pbs" / "templates" / "netbox_pbs" / "inc"
VMBACKUP_PANEL = PANEL_DIR / "vmbackup_pbs_snapshots_panel.html"
PBSSNAPSHOT_PANEL = PANEL_DIR / "pbssnapshot_vm_backups_panel.html"


def _module() -> ast.Module:
    return ast.parse(TEMPLATE_CONTENT_PATH.read_text(encoding="utf-8"))


def _classdef(name: str) -> ast.ClassDef:
    for node in ast.walk(_module()):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name!r} not found in template_content.py")


def _models_assignment(cls: ast.ClassDef) -> list[str]:
    for stmt in cls.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "models"
            and isinstance(stmt.value, ast.List)
        ):
            return [
                elt.value
                for elt in stmt.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
    raise AssertionError(f"class {cls.name!r} has no ``models = [...]`` literal")


def _method_names(cls: ast.ClassDef) -> set[str]:
    return {
        stmt.name
        for stmt in cls.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_template_content_module_exists() -> None:
    assert TEMPLATE_CONTENT_PATH.is_file(), TEMPLATE_CONTENT_PATH


def test_vmbackup_extension_targets_vmbackup() -> None:
    cls = _classdef("VMBackupPBSSnapshotExtension")
    assert _models_assignment(cls) == ["netbox_proxbox.vmbackup"]
    assert "right_page" in _method_names(cls)


def test_pbssnapshot_extension_targets_pbssnapshot() -> None:
    cls = _classdef("PBSSnapshotVMBackupExtension")
    assert _models_assignment(cls) == ["netbox_pbs.pbssnapshot"]
    assert "right_page" in _method_names(cls)


def test_template_extensions_is_unconditional_list() -> None:
    """``template_extensions`` must be an unconditional module-level list.

    Per the 2026-05-13 pivot, ``netbox_proxbox`` is a hard dependency
    declared in ``PBSConfig.required_plugins`` — NetBox refuses to load
    ``netbox_pbs`` without it — so the old
    ``if apps.is_installed("netbox_proxbox"): template_extensions = [...]``
    guard is gone.
    """
    module = _module()
    found = False
    for stmt in module.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "template_extensions"
            and isinstance(stmt.value, ast.List)
        ):
            names = {
                elt.id for elt in stmt.value.elts if isinstance(elt, ast.Name)
            }
            assert {
                "VMBackupPBSSnapshotExtension",
                "PBSSnapshotVMBackupExtension",
            } <= names, names
            found = True
            break
    assert found, "expected module-level `template_extensions = [...]` assignment"

    # And the old guard must NOT be present.
    for stmt in module.body:
        if isinstance(stmt, ast.If):
            test = stmt.test
            if (
                isinstance(test, ast.Call)
                and isinstance(test.func, ast.Attribute)
                and test.func.attr == "is_installed"
            ):
                raise AssertionError(
                    "Stale `apps.is_installed(...)` guard found in "
                    "template_content.py — pivot requires unconditional "
                    "registration."
                )


def test_panel_templates_exist() -> None:
    assert VMBACKUP_PANEL.is_file(), VMBACKUP_PANEL
    assert PBSSNAPSHOT_PANEL.is_file(), PBSSNAPSHOT_PANEL


def test_matcher_helpers_exist() -> None:
    """Both natural-key matchers must exist as module-level functions."""
    names = {
        node.name
        for node in ast.walk(_module())
        if isinstance(node, ast.FunctionDef)
    }
    assert {"_match_pbs_snapshots", "_match_vm_backups"} <= names, names
