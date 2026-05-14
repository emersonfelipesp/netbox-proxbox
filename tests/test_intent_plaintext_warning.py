"""AST-only contracts for Sub-PR K plaintext password warnings."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "merge_validator.py"
PLUGIN_SETTINGS_PATH = (
    REPO_ROOT / "netbox_proxbox" / "models" / "plugin_settings.py"
)


def _class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{name} class not found")


def _class_assignment_names(class_node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for node in class_node.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def test_merge_validator_contains_plaintext_password_warning_contract():
    text = VALIDATOR_PATH.read_text(encoding="utf-8")
    assert '"plaintext_password_warning"' in text
    assert '"password:"' in text
    assert ".lower()" in text or "re.IGNORECASE" in text


def test_plugin_settings_declares_plaintext_password_warning_flag():
    module = ast.parse(PLUGIN_SETTINGS_PATH.read_text(encoding="utf-8"))
    settings_class = _class(module, "ProxboxPluginSettings")
    assignments = _class_assignment_names(settings_class)
    assert "intent_warn_plaintext_password" in assignments
