"""Sub-PR D (#381): source-contract tests for the merge_validator.

The validator at ``netbox_proxbox/intent/merge_validator.py`` is
registered as a ``netbox_branching`` ``merge_validators`` entry by the
operator (see the ``proxbox_install_merge_validator`` management
command). Its contract:

* If the master flag is False -> permit unconditionally.
* If the branch's ``apply_to_proxmox`` CF is False -> permit
  unconditionally.
* If the branch has no VM ChangeDiff rows -> permit with a no-op
  message.
* If a DELETE diff exists but ``apply_destroy_confirmed`` is False ->
  block with the four-eyes message at the plugin layer (no remote
  call needed; Safety Model invariant 3).
* Otherwise -> POST /intent/plan via ``call_plan_endpoint`` and
  forward the verdict.
* On transport failure -> block with an operator-facing error rather
  than silently permit.

Behavioral coverage of these branches lands in the E2E suite (Sub-PR
J) where a real NetBox + proxbox-api are available. The tests here
are AST-based so they run without bootstrapping NetBox, matching the
existing pattern used by ``test_intent_shell_models.py`` and
``test_intent_permissions.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTENT_DIR = REPO_ROOT / "netbox_proxbox" / "intent"
VALIDATOR_PATH = INTENT_DIR / "merge_validator.py"
PLAN_CLIENT_PATH = INTENT_DIR / "plan_client.py"
INIT_PATH = INTENT_DIR / "__init__.py"

MGMT_CMD_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "management"
    / "commands"
    / "proxbox_install_merge_validator.py"
)


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _class_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}


def test_intent_package_exists_with_required_modules():
    assert INIT_PATH.exists(), "netbox_proxbox/intent/__init__.py must exist"
    assert VALIDATOR_PATH.exists(), (
        "merge_validator.py must exist on the intent package"
    )
    assert PLAN_CLIENT_PATH.exists(), "plan_client.py must exist on the intent package"


def test_validator_module_exports_validate_proxmox_intent():
    names = _function_names(VALIDATOR_PATH)
    assert "validate_proxmox_intent" in names

    init_text = INIT_PATH.read_text()
    assert (
        "from netbox_proxbox.intent.merge_validator import validate_proxmox_intent"
        in init_text
    )
    assert '"validate_proxmox_intent"' in init_text


def test_plan_client_exports_required_symbols():
    init_text = INIT_PATH.read_text()
    assert "PlanClientError" in init_text
    assert "PlanClientResult" in init_text
    assert "call_plan_endpoint" in init_text

    classes = _class_names(PLAN_CLIENT_PATH)
    functions = _function_names(PLAN_CLIENT_PATH)
    assert "PlanClientError" in classes
    assert "PlanClientResult" in classes
    assert "call_plan_endpoint" in functions


def test_validator_signature_matches_branching_contract():
    """``merge_validators`` callables receive ``(branch, user)``."""
    tree = ast.parse(VALIDATOR_PATH.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "validate_proxmox_intent":
            args = [a.arg for a in node.args.args]
            assert args[:2] == ["branch", "user"], (
                f"validate_proxmox_intent must be called as (branch, user); got {args}"
            )
            return
    raise AssertionError("validate_proxmox_intent function not found")


def test_validator_checks_master_flag_and_branch_optin():
    text = VALIDATOR_PATH.read_text()
    assert "netbox_to_proxmox_enabled" in text, (
        "validator must read the master flag from ProxboxPluginSettings"
    )
    assert "apply_to_proxmox" in text, (
        "validator must check the branch's apply_to_proxmox custom field"
    )


def test_validator_enforces_delete_destroy_confirmed_at_plugin_layer():
    """Safety Model invariant 3: DELETE without
    ``apply_destroy_confirmed`` is blocked at the plugin layer before
    any backend call."""
    text = VALIDATOR_PATH.read_text()
    assert "apply_destroy_confirmed" in text
    assert "authorize_deletion_request" in text, (
        "validator's DELETE block message must reference the four-eyes "
        "authorize_deletion_request permission"
    )


def test_validator_classifies_create_update_delete_diffs():
    text = VALIDATOR_PATH.read_text()
    for verb in ("create", "update", "delete"):
        assert f'"{verb}"' in text, (
            f"merge_validator must classify '{verb}' ChangeDiff rows"
        )


def test_validator_calls_plan_endpoint():
    text = VALIDATOR_PATH.read_text()
    assert "call_plan_endpoint" in text, (
        "validator must call proxbox-api /intent/plan via call_plan_endpoint"
    )
    assert "PlanClientError" in text, (
        "validator must surface PlanClientError as a non-permitting indicator"
    )


def test_plan_client_targets_intent_plan_path():
    text = PLAN_CLIENT_PATH.read_text()
    assert "/intent/plan" in text, (
        "plan_client must POST to /intent/plan on the FastAPIEndpoint"
    )
    assert "get_fastapi_request_context" in text, (
        "plan_client must resolve the active FastAPIEndpoint via "
        "services.backend_context"
    )


def test_management_command_emits_validator_dotted_path():
    text = MGMT_CMD_PATH.read_text()
    assert "netbox_proxbox.intent.merge_validator.validate_proxmox_intent" in text, (
        "proxbox_install_merge_validator must print the validator's "
        "dotted path so operators can paste it into PLUGINS_CONFIG"
    )
    assert "merge_validators" in text
    assert "netbox_branching" in text


def test_management_command_uses_basecommand():
    tree = ast.parse(MGMT_CMD_PATH.read_text())
    bases: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Command":
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(base.attr)
    assert "BaseCommand" in bases, (
        "Command must inherit from django.core.management.base.BaseCommand"
    )
