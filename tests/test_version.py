"""Lock the plugin version and NetBox compatibility constants in source.

The plugin's ``version``, ``min_version``, and ``max_version`` are surfaced in
several places (docs, CI, release notes). This test parses
``netbox_proxbox/__init__.py`` directly via AST so the assertions run without
loading Django or NetBox; future version bumps will fail loudly here as a
reminder to update the docs and release-notes files at the same time.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "netbox_proxbox" / "__init__.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
README_PATH = REPO_ROOT / "README.md"
CLAUDE_PATH = REPO_ROOT / "CLAUDE.md"
DOCS_INDEX_PATH = REPO_ROOT / "docs" / "index.md"
INSTALL_GIT_PATH = REPO_ROOT / "docs" / "installation" / "2-installing-plugin-git.md"
UPGRADING_PATH = REPO_ROOT / "docs" / "installation" / "upgrading.md"
RELEASE_NOTES_INDEX_PATH = REPO_ROOT / "docs" / "release-notes" / "index.md"
RELEASE_NOTES_014_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.14.md"
RELEASE_NOTES_015_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.15.md"
RELEASE_NOTES_016_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.16.md"
E2E_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "e2e-docker.yml"
PUBLISH_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "publish-testpypi.yml"
NIGHTLY_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "nightly-contracts.yml"
DOCS_SCREENSHOTS_WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "docs-screenshots.yml"
)

CURRENT_PLUGIN_VERSION = "0.0.16"
CURRENT_PROXBOX_API_VERSION = "0.0.12"
CURRENT_NETBOX_MIN_VERSION = "4.5.8"
CURRENT_NETBOX_MAX_VERSION = "4.6.99"
PREVIOUS_PLUGIN_VERSION = "0.0.15"
PREVIOUS_PROXBOX_API_VERSION = "0.0.11"


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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_markdown_table_row(text: str, expected_cells: tuple[str, ...]) -> None:
    normalized_rows = {
        "|".join(cell.strip() for cell in line.strip().strip("|").split("|"))
        for line in text.splitlines()
        if line.lstrip().startswith("|")
    }
    expected = "|".join(expected_cells)
    assert expected in normalized_rows


def test_plugin_version_is_pinned():
    constants = _class_constants("ProxboxConfig")
    actual = constants.get("version") or ""
    pattern = rf"^{re.escape(CURRENT_PLUGIN_VERSION)}(rc\d+|\.post\d+)?$"
    assert re.match(pattern, actual), (
        f"version drifted (got {actual!r}); update docs/, release-notes, "
        "and pyproject.toml together"
    )


def test_min_max_netbox_versions_are_pinned():
    constants = _class_constants("ProxboxConfig")
    assert constants.get("min_version") == CURRENT_NETBOX_MIN_VERSION
    assert constants.get("max_version") == CURRENT_NETBOX_MAX_VERSION


def test_certified_netbox_versions_are_documented():
    constants = _class_constants("ProxboxConfig")
    assert constants["min_version"] == CURRENT_NETBOX_MIN_VERSION
    assert constants["max_version"] == CURRENT_NETBOX_MAX_VERSION

    docs_with_explicit_range = (
        CLAUDE_PATH,
        DOCS_INDEX_PATH,
        INSTALL_GIT_PATH,
        UPGRADING_PATH,
        RELEASE_NOTES_016_PATH,
    )
    for path in docs_with_explicit_range:
        text = _read(path)
        assert CURRENT_NETBOX_MIN_VERSION in text, f"{path} missing min version"
        assert CURRENT_NETBOX_MAX_VERSION in text, f"{path} missing max version"


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

    expected_pin = f"PROXBOX_API_RELEASE_VERSION: {CURRENT_PROXBOX_API_VERSION}"
    assert expected_pin in e2e_workflow
    assert expected_pin in docs_workflow
    assert "pip install proxbox-api" not in nightly_workflow


def test_release_workflow_uses_matching_package_indexes_for_e2e():
    # The release workflow pairs each E2E gate with the same package index the
    # plugin is being validated against: TestPyPI gate installs the matching
    # proxbox-api from TestPyPI; PyPI candidate and PyPI final gates install
    # the matching proxbox-api from PyPI. `dependency_mode: dev` clones
    # proxbox-api main HEAD and must not appear here — main may sit on a
    # different release line than the rc/tag being validated.
    publish_workflow = PUBLISH_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "--skip-existing" not in publish_workflow
    assert "PROXBOX_API_TESTPYPI_VERSION" in publish_workflow
    assert "PROXBOX_API_PYPI_VERSION" in publish_workflow

    assert "install_source: testpypi" in publish_workflow
    assert "install_source: local" in publish_workflow
    assert "install_source: pypi" in publish_workflow
    assert "dependency_mode: dev" not in publish_workflow
    assert publish_workflow.count("dependency_mode: testpypi-package") == 1
    assert publish_workflow.count("dependency_mode: pypi-package") == 2
    assert (
        publish_workflow.count(
            "proxbox_api_version: ${{ needs.prepare-release.outputs.proxbox_api_version }}"
        )
        == 3
    )


def test_e2e_workflow_supports_proxbox_api_package_index_runtime_modes():
    e2e_workflow = E2E_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "- testpypi" in e2e_workflow
    assert "- testpypi-package" in e2e_workflow
    assert "- pypi-package" in e2e_workflow
    assert 'PROXBOX_API_VERSION="${{ inputs.proxbox_api_version }}"' in e2e_workflow
    assert "--index-url https://test.pypi.org/simple/" in e2e_workflow
    assert "--extra-index-url https://pypi.org/simple/" in e2e_workflow
    assert "--index-url https://pypi.org/simple/" in e2e_workflow
    assert '"proxbox-api==${PROXBOX_API_VERSION}"' in e2e_workflow


def test_current_release_pairing_is_documented_in_primary_docs():
    current_row = (
        f">={CURRENT_NETBOX_MIN_VERSION}",
        f"v{CURRENT_PLUGIN_VERSION}",
        f"v{CURRENT_PROXBOX_API_VERSION}",
        "v0.0.8.post1",
        "v0.0.3.post1",
    )
    for path in (README_PATH, DOCS_INDEX_PATH, RELEASE_NOTES_016_PATH):
        text = _read(path)
        _assert_markdown_table_row(text, current_row)

    for path in (
        CLAUDE_PATH,
        DOCS_INDEX_PATH,
        UPGRADING_PATH,
        RELEASE_NOTES_INDEX_PATH,
        RELEASE_NOTES_016_PATH,
    ):
        text = _read(path)
        assert CURRENT_PLUGIN_VERSION in text, f"{path} missing plugin version"
        assert CURRENT_PROXBOX_API_VERSION in text, f"{path} missing backend pin"


def test_previous_release_compatibility_row_matches_release_notes():
    previous_row = (
        f">={CURRENT_NETBOX_MIN_VERSION}",
        f"v{PREVIOUS_PLUGIN_VERSION}",
        f"v{PREVIOUS_PROXBOX_API_VERSION}",
        "v0.0.8.post1",
        "v0.0.3.post1",
    )
    for path in (
        README_PATH,
        DOCS_INDEX_PATH,
        RELEASE_NOTES_015_PATH,
        RELEASE_NOTES_016_PATH,
    ):
        _assert_markdown_table_row(_read(path), previous_row)
