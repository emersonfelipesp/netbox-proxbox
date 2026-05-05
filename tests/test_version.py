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
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "netbox_proxbox" / "__init__.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
E2E_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "e2e-docker.yml"
NIGHTLY_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "nightly-contracts.yml"
DOCS_SCREENSHOTS_WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "docs-screenshots.yml"
)


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
    assert constants.get("version") == "0.0.14", (
        "version drifted; update docs/, release-notes, and pyproject.toml together"
    )


def test_min_max_netbox_versions_are_pinned():
    constants = _class_constants("ProxboxConfig")
    assert constants.get("min_version") == "4.5.8"
    assert constants.get("max_version") == "4.6.99"


def test_certified_netbox_versions_are_documented():
    constants = _class_constants("ProxboxConfig")
    assert constants["min_version"] == "4.5.8"
    assert constants["max_version"] == "4.6.99"


def test_certified_netbox_versions_are_in_e2e_matrix():
    workflow = E2E_WORKFLOW_PATH.read_text(encoding="utf-8")
    for version in ("v4.5.8", "v4.5.9", "v4.6.0"):
        assert f"netboxcommunity/netbox:{version}" in workflow
    assert "netboxcommunity/netbox:v4.6.0-beta2" not in workflow


def test_proxbox_api_is_not_a_python_dependency():
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    dependencies = list(pyproject["project"].get("dependencies", []))
    for extra_deps in pyproject["project"].get("optional-dependencies", {}).values():
        dependencies.extend(extra_deps)
    for group_deps in pyproject.get("dependency-groups", {}).values():
        dependencies.extend(group_deps)

    normalized = [str(dep).lower().replace("_", "-") for dep in dependencies]
    assert not any(dep.startswith("proxbox-api") for dep in normalized), (
        "netbox-proxbox talks to proxbox-api over REST/SSE/WebSocket; it must "
        "not install proxbox-api as a Python dependency"
    )


def test_workflows_pin_proxbox_api_runtime_release_without_installing_package():
    e2e_workflow = E2E_WORKFLOW_PATH.read_text(encoding="utf-8")
    nightly_workflow = NIGHTLY_WORKFLOW_PATH.read_text(encoding="utf-8")
    docs_workflow = DOCS_SCREENSHOTS_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "PROXBOX_API_RELEASE_VERSION: 0.0.10.post2" in e2e_workflow
    assert "PROXBOX_API_RELEASE_VERSION: 0.0.10.post2" in docs_workflow
    assert "pip install proxbox-api" not in nightly_workflow
