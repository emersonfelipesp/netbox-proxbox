"""Lock the plugin version and NetBox compatibility constants in source.

The plugin's ``version``, ``min_version``, and ``max_version`` are surfaced in
several places (docs, CI, release notes). This test parses
``netbox_proxbox/__init__.py`` directly via AST so the assertions run without
loading Django or NetBox; future version bumps will fail loudly here as a
reminder to update the docs and release-notes files at the same time.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "netbox_proxbox" / "__init__.py"


def _class_constants(class_name: str) -> dict[str, str]:
    module = ast.parse(INIT_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            constants: dict[str, str] = {}
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and isinstance(
                    stmt.value, ast.Constant
                ):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            constants[target.id] = stmt.value.value
            return constants
    raise AssertionError(f"class {class_name} not found in {INIT_PATH}")


def test_plugin_version_is_pinned():
    constants = _class_constants("ProxboxConfig")
    assert constants.get("version") == "0.0.13.post4", (
        "version drifted; update docs/, release-notes, and pyproject.toml together"
    )


def test_min_max_netbox_versions_are_pinned():
    constants = _class_constants("ProxboxConfig")
    assert constants.get("min_version") == "4.6.0"
    assert constants.get("max_version") == "4.6.99"
