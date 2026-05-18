"""Sub-PR C (#380): contract test for the 12 NetBox→Proxmox intent CFs.

AST-only — does not bootstrap Django. Pins:

  * The data callable module exists at the canonical path.
  * It declares ``VM_INTENT_FIELDS`` (10 entries) and
    ``BRANCH_INTENT_FIELDS`` (2 entries) with the exact field-name set
    required by Sub-PRs F/G/H/K.
  * The v0.0.16 release migration is a ``RunPython`` calling
    the registration helper. Originally shipped as
    ``0039_intent_custom_fields``; now consolidated into
    ``0038_v0_0_16_release``.
  * The helper guards Branch CFs behind a ``ContentType.DoesNotExist``
    fallback so the migration survives when ``netbox_branching`` is not
    installed.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_MODULE = REPO_ROOT / "netbox_proxbox" / "migrations" / "_v0_0_16_release_data.py"
MIGRATION = REPO_ROOT / "netbox_proxbox" / "migrations" / "0038_v0_0_16_release.py"

EXPECTED_VM_CFS = {
    "proxmox_node",
    "proxmox_storage",
    "proxmox_iso",
    "proxmox_template_vmid",
    "cloud_init_user",
    "cloud_init_ssh_keys",
    "cloud_init_user_data",
    "cloud_init_network",
    "proxbox_intent_state",
    "proxbox_last_apply_run_id",
}

EXPECTED_BRANCH_CFS = {"apply_to_proxmox", "apply_destroy_confirmed"}


def _module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def _extract_tuple_of_tuples(module: ast.Module, name: str) -> tuple[tuple, ...]:
    for node in ast.iter_child_nodes(module):
        if isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        elif isinstance(node, ast.Assign):
            target = node.targets[0]
            value = node.value
        else:
            continue
        if not (isinstance(target, ast.Name) and target.id == name):
            continue
        if not isinstance(value, ast.Tuple):
            continue
        rows = []
        for elt in value.elts:
            if isinstance(elt, ast.Tuple):
                rows.append(
                    tuple(
                        inner.value
                        for inner in elt.elts
                        if isinstance(inner, ast.Constant)
                    )
                )
        return tuple(rows)
    raise AssertionError(f"Constant {name!r} not found in {DATA_MODULE}")


def test_data_module_exists():
    assert DATA_MODULE.exists(), (
        f"Sub-PR C requires {DATA_MODULE.relative_to(REPO_ROOT)} to exist."
    )


def test_vm_intent_fields_match_expected_set():
    """Operator + internal VM intent CFs must union to the 10 pinned names."""
    module = _module_ast(DATA_MODULE)
    operator_rows = _extract_tuple_of_tuples(module, "VM_OPERATOR_FIELDS")
    internal_rows = _extract_tuple_of_tuples(module, "VM_INTERNAL_FIELDS")
    names = {row[0] for row in operator_rows + internal_rows if row}
    assert names == EXPECTED_VM_CFS, (
        f"VM_OPERATOR_FIELDS + VM_INTERNAL_FIELDS must union to exactly "
        f"{EXPECTED_VM_CFS}; got {names}. Sub-PRs F/G/K read these names "
        f"directly."
    )
    assert len(operator_rows) + len(internal_rows) == 10
    # Internal stamps must be the two Proxbox-written drift-detection fields.
    internal_names = {row[0] for row in internal_rows if row}
    assert internal_names == {
        "proxbox_intent_state",
        "proxbox_last_apply_run_id",
    }, (
        "VM_INTERNAL_FIELDS must hold exactly the two Proxbox-managed "
        "stamps; they are registered hidden + non-editable so operators "
        "cannot hand-edit them and defeat drift detection."
    )


def test_branch_intent_fields_match_expected_set():
    module = _module_ast(DATA_MODULE)
    rows = _extract_tuple_of_tuples(module, "BRANCH_INTENT_FIELDS")
    names = {row[0] for row in rows if row}
    assert names == EXPECTED_BRANCH_CFS, (
        f"BRANCH_INTENT_FIELDS must declare exactly {EXPECTED_BRANCH_CFS}; "
        f"got {names}. Sub-PR D plan validator and Sub-PR H DELETE gate "
        "read these names directly."
    )
    assert len(rows) == 2


def test_migration_0039_runs_python_helpers():
    """The release migration must run the intent-CF registration helpers."""
    module = _module_ast(MIGRATION)
    run_python_calls = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "RunPython"
    ]
    assert run_python_calls, (
        "Release migration must declare a migrations.RunPython operation "
        "calling the intent-CF registration helpers."
    )
    matching = [
        call
        for call in run_python_calls
        if call.args
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "register_intent_custom_fields"
    ]
    assert matching, (
        "Release migration must call migrations.RunPython("
        "register_intent_custom_fields, ...)."
    )
    call = matching[0]
    reverse = next(
        (kw.value for kw in call.keywords if kw.arg == "reverse_code"),
        None,
    )
    assert isinstance(reverse, ast.Name)
    assert reverse.id == "unregister_intent_custom_fields"


def test_helper_guards_missing_content_type():
    """``_ensure_intent_cf`` must swallow ``ContentType.DoesNotExist``.

    The Branch CFs rely on the netbox_branching plugin's ContentType. If
    branching is not installed, the helper must return cleanly so the
    migration succeeds on either deployment shape.
    """
    text = DATA_MODULE.read_text()
    assert "ContentType.DoesNotExist" in text, (
        "_ensure_intent_cf must catch ContentType.DoesNotExist so Branch "
        "CFs are skipped silently when netbox_branching is absent."
    )


def test_migration_depends_on_0038():
    """The release migration must still reference 0038_intent_permissions.

    Originally a ``dependencies`` entry on the standalone
    ``0039_intent_custom_fields`` migration. The consolidated
    ``0038_v0_0_16_release`` migration now carries the operations under
    section comments tagged with the original migration name so the
    chain stays auditable.
    """
    text = MIGRATION.read_text()
    assert "# ── 0038_intent_permissions" in text, (
        "Release migration must include a # ── 0038_intent_permissions section "
        "comment so the migration chain stays auditable."
    )
