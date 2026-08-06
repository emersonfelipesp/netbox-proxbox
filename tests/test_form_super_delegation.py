"""Structural contracts for Django form lifecycle-hook delegation."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FORMS_ROOT = REPO_ROOT / "netbox_proxbox" / "forms"


def _calls_super_method(function: ast.FunctionDef, method_name: str) -> bool:
    """Return whether ``function`` delegates ``method_name`` through ``super``."""
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != method_name:
            continue
        receiver = node.func.value
        if (
            isinstance(receiver, ast.Call)
            and isinstance(receiver.func, ast.Name)
            and receiver.func.id == "super"
        ):
            return True
    return False


def test_every_post_clean_override_delegates_to_super() -> None:
    """Keep NetBox's M2M preparation in every package form override."""
    overrides: list[tuple[Path, ast.ClassDef, ast.FunctionDef]] = []
    for path in sorted(FORMS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "_post_clean":
                    overrides.append((path, node, child))

    assert overrides, "expected at least one form _post_clean() override"
    assert any(
        path.name == "ssh_credential.py" and class_node.name == "NodeSSHCredentialForm"
        for path, class_node, _function in overrides
    )

    missing = [
        f"{path.relative_to(REPO_ROOT)}:{function.lineno} ({class_node.name})"
        for path, class_node, function in overrides
        if not _calls_super_method(function, "_post_clean")
    ]
    assert not missing, (
        "Every form _post_clean() override must call super()._post_clean() so "
        f"NetBox can populate instance._m2m_values; missing delegation: {missing}"
    )
