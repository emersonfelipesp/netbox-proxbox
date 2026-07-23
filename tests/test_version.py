"""Lock the plugin version and NetBox compatibility constants in source.

The plugin's ``version``, ``min_version``, and ``max_version`` are surfaced in
several places (docs, CI, release notes). This test parses
``netbox_proxbox/__init__.py`` directly via AST so the assertions run without
loading Django or NetBox; future version bumps will fail loudly here as a
reminder to update the docs and release-notes files at the same time.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "netbox_proxbox" / "__init__.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
README_PATH = REPO_ROOT / "README.md"
CLAUDE_PATH = REPO_ROOT / "CLAUDE.md"
COMPATIBILITY_PATH = REPO_ROOT / "COMPATIBILITY.md"
DOCS_INDEX_PATH = REPO_ROOT / "docs" / "index.md"
INSTALL_GIT_PATH = REPO_ROOT / "docs" / "installation" / "2-installing-plugin-git.md"
UPGRADING_PATH = REPO_ROOT / "docs" / "installation" / "upgrading.md"
RELEASE_NOTES_INDEX_PATH = REPO_ROOT / "docs" / "release-notes" / "index.md"
RELEASE_NOTES_014_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.14.md"
RELEASE_NOTES_015_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.15.md"
RELEASE_NOTES_016_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.16.md"
RELEASE_NOTES_017_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.17.md"
RELEASE_NOTES_018_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.18.md"
RELEASE_NOTES_019_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.19.md"
RELEASE_NOTES_020_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.20.md"
RELEASE_NOTES_020_POST3_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.20.post3.md"
)
RELEASE_NOTES_021_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.21.md"
RELEASE_NOTES_022_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.22.md"
RELEASE_NOTES_023_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.23.md"
RELEASE_NOTES_023_POST1_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.23.post1.md"
)
E2E_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "e2e-docker.yml"
PUBLISH_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "publish-testpypi.yml"
NIGHTLY_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "nightly-contracts.yml"
DOCS_SCREENSHOTS_WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "docs-screenshots.yml"
)
DJANGO_TESTS_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "django-tests.yml"
PAGE_COVERAGE_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "page-coverage.yml"
CERTIFICATION_PATH = REPO_ROOT / "CERTIFICATION.md"
DOCS_CERTIFICATION_PATH = REPO_ROOT / "docs" / "certification.md"
APPLICATION_PACKET_PATH = REPO_ROOT / "docs" / "application-packet.md"

CURRENT_PLUGIN_VERSION = "0.0.23"
CURRENT_RELEASE_VERSION = "0.0.23.post1"
CURRENT_PROXBOX_API_PAIRING_LABEL = "guest-VM-interface writer build / next release"
CURRENT_PAIRING_LINE = (
    "Current pairing: netbox-proxbox 0.0.23.post1 <-> proxbox-api "
    "(guest-VM-interface writer build / next release) <-> proxmox-sdk 0.0.12 "
    "<-> netbox-sdk 0.0.10."
)
PROXBOX_API_WORKFLOW_DEFAULT_VERSION = "0.0.19.post5"
CURRENT_NETBOX_MIN_VERSION = "4.5.8"
CURRENT_NETBOX_MAX_VERSION = "4.6.99"
LATEST_CERTIFIED_NETBOX_VERSION = "4.6.5"
LATEST_CERTIFIED_NETBOX_IMAGE = (
    f"netboxcommunity/netbox:v{LATEST_CERTIFIED_NETBOX_VERSION}"
)
SUPPORTED_NETBOX_IMAGE_TAGS = (
    "netboxcommunity/netbox:v4.5.8",
    "netboxcommunity/netbox:v4.5.9",
    "netboxcommunity/netbox:v4.6.0",
    "netboxcommunity/netbox:v4.6.1",
    "netboxcommunity/netbox:v4.6.2",
    "netboxcommunity/netbox:v4.6.3",
    "netboxcommunity/netbox:v4.6.4",
    "netboxcommunity/netbox:v4.6.5",
)
E2E_DEFAULT_INSTALL_SOURCES = ("local", "pypi", "container")
E2E_EXPLICIT_INSTALL_SOURCES = (*E2E_DEFAULT_INSTALL_SOURCES, "testpypi")
DJANGO_TESTED_NETBOX_TAGS = ("v4.5.8", "v4.5.9", "v4.6.0", "v4.6.5")
PREVIOUS_PLUGIN_VERSION = "0.0.22"
PREVIOUS_PROXBOX_API_VERSION = "0.0.19.post5"
CURRENT_RELEASE_NOTES_PATH = RELEASE_NOTES_023_POST1_PATH


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


def _workflow_matrix_expression(workflow: str, matrix_key: str) -> str:
    prefix = f"        {matrix_key}: "
    matches = [
        line.removeprefix(prefix)
        for line in workflow.splitlines()
        if line.startswith(prefix)
    ]
    assert len(matches) == 1, (
        f"expected exactly one {matrix_key!r} matrix expression, got {len(matches)}"
    )
    return matches[0]


def _workflow_matrix_json_fallback(workflow: str, matrix_key: str) -> tuple[str, ...]:
    expression = _workflow_matrix_expression(workflow, matrix_key)
    match = re.search(r"\|\| '(?P<values>\[[^']*\])'\)\s*}}$", expression)
    assert match is not None, f"{matrix_key!r} matrix has no JSON fallback"
    values = json.loads(match.group("values"))
    assert isinstance(values, list)
    assert all(isinstance(value, str) for value in values)
    return tuple(values)


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
        CURRENT_RELEASE_NOTES_PATH,
    )
    for path in docs_with_explicit_range:
        text = _read(path)
        assert CURRENT_NETBOX_MIN_VERSION in text, f"{path} missing min version"
        assert CURRENT_NETBOX_MAX_VERSION in text, f"{path} missing max version"


def test_certified_netbox_versions_are_in_e2e_matrix():
    workflow = E2E_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert (
        _workflow_matrix_json_fallback(workflow, "netbox_image")
        == SUPPORTED_NETBOX_IMAGE_TAGS
    )


def test_e2e_scheduled_runs_expand_the_full_install_source_matrix():
    workflow = E2E_WORKFLOW_PATH.read_text(encoding="utf-8")
    expression = _workflow_matrix_expression(workflow, "install_source")
    recognized_sources = tuple(
        re.findall(r"inputs\.install_source == '([^']+)'", expression)
    )
    fallback_sources = _workflow_matrix_json_fallback(workflow, "install_source")

    assert recognized_sources == E2E_EXPLICIT_INSTALL_SOURCES
    assert fallback_sources == E2E_DEFAULT_INSTALL_SOURCES

    def expanded_sources(input_value: str) -> tuple[str, ...]:
        if input_value in recognized_sources:
            return (input_value,)
        return fallback_sources

    assert expanded_sources("") == E2E_DEFAULT_INSTALL_SOURCES
    assert expanded_sources("both") == E2E_DEFAULT_INSTALL_SOURCES
    assert expanded_sources("unrecognized") == E2E_DEFAULT_INSTALL_SOURCES


def test_e2e_stable_python_cells_are_gating_for_pve():
    workflow = E2E_WORKFLOW_PATH.read_text(encoding="utf-8")
    job_header = workflow.split("    steps:", maxsplit=1)[0]
    continue_on_error_lines = [
        line.strip()
        for line in job_header.splitlines()
        if line.strip().startswith("continue-on-error:")
    ]
    assert continue_on_error_lines == [
        "continue-on-error: ${{ matrix.proxbox_api_runtime == 'pyo3-rust' }}"
    ]


def test_docs_screenshots_pins_latest_certified_netbox():
    workflow = _read(DOCS_SCREENSHOTS_WORKFLOW_PATH)
    assert workflow.count(f"NETBOX_IMAGE: {LATEST_CERTIFIED_NETBOX_IMAGE}") == 1


def test_django_tests_pin_expected_netbox_matrix():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    expected_matrix = json.dumps(list(DJANGO_TESTED_NETBOX_TAGS))
    assert f"        netbox: {expected_matrix}" in workflow


def test_page_coverage_pins_latest_certified_netbox():
    workflow = _read(PAGE_COVERAGE_WORKFLOW_PATH)
    assert workflow.count(f"NETBOX_IMAGE: {LATEST_CERTIFIED_NETBOX_IMAGE}") == 1
    assert (
        f"name: Page Coverage / {LATEST_CERTIFIED_NETBOX_IMAGE} / local / pve"
        in workflow
    )


def test_certified_netbox_range_is_documented_independently():
    for path in (
        README_PATH,
        DOCS_INDEX_PATH,
        CURRENT_RELEASE_NOTES_PATH,
        CERTIFICATION_PATH,
        DOCS_CERTIFICATION_PATH,
        APPLICATION_PACKET_PATH,
    ):
        text = _read(path)
        assert CURRENT_NETBOX_MIN_VERSION in text, f"{path} missing certified floor"
        assert LATEST_CERTIFIED_NETBOX_VERSION in text, (
            f"{path} missing latest certified version"
        )


def test_certification_evidence_names_the_tested_plugin_artifact():
    for path in (CERTIFICATION_PATH, APPLICATION_PACKET_PATH):
        text = _read(path)
        assert CURRENT_RELEASE_VERSION in text, f"{path} missing tested plugin artifact"
        assert "0.0.18.post1" not in text, (
            f"{path} still names the historical certification target"
        )


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


def test_pydantic_pin_keeps_proxmox_sdk_peer_plugins_resolvable():
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    dependencies = {
        str(dep).lower().replace("_", "-")
        for dep in pyproject["project"].get("dependencies", [])
    }

    assert "pydantic>=2.13.3,<2.14.0" in dependencies
    assert "pydantic==2.13.4" not in dependencies


def test_pyproject_metadata_is_certification_ready():
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert re.fullmatch(
        rf"^{re.escape(CURRENT_PLUGIN_VERSION)}(rc\d+|\.post\d+)?$",
        project["version"],
    ), (
        f"pyproject.toml version {project['version']!r} does not match {CURRENT_PLUGIN_VERSION}"
    )
    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE"]
    assert (
        "License :: OSI Approved :: Apache Software License"
        not in project["classifiers"]
    )
    assert project["urls"]["Documentation"] == (
        "https://emersonfelipesp.github.io/netbox-proxbox/"
    )
    assert (REPO_ROOT / "LICENSE").is_file()


def test_release_notes_files_are_present():
    for path in (
        RELEASE_NOTES_014_PATH,
        RELEASE_NOTES_015_PATH,
        RELEASE_NOTES_016_PATH,
        RELEASE_NOTES_017_PATH,
        RELEASE_NOTES_018_PATH,
        RELEASE_NOTES_019_PATH,
        RELEASE_NOTES_020_PATH,
        RELEASE_NOTES_020_POST3_PATH,
        RELEASE_NOTES_021_PATH,
        RELEASE_NOTES_022_PATH,
        RELEASE_NOTES_023_PATH,
        RELEASE_NOTES_023_POST1_PATH,
    ):
        assert path.is_file(), f"{path} is missing"


def test_workflows_pin_proxbox_api_runtime_release_without_installing_package():
    e2e_workflow = E2E_WORKFLOW_PATH.read_text(encoding="utf-8")
    nightly_workflow = NIGHTLY_WORKFLOW_PATH.read_text(encoding="utf-8")
    docs_workflow = DOCS_SCREENSHOTS_WORKFLOW_PATH.read_text(encoding="utf-8")

    expected_pin = (
        f"PROXBOX_API_RELEASE_VERSION: {PROXBOX_API_WORKFLOW_DEFAULT_VERSION}"
    )
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
    assert (
        "PROXBOX_API_PACKAGE_SPEC=proxbox-api==${PROXBOX_API_VERSION}" in e2e_workflow
    )
    assert (
        "PROXBOX_API_PACKAGE_SPEC=proxbox-api[pyo3-rust]==${PROXBOX_API_VERSION}"
        in e2e_workflow
    )
    assert '"${PROXBOX_API_PACKAGE_SPEC}"' in e2e_workflow


def test_current_release_pairing_is_documented_in_primary_docs():
    current_row = (
        f">={CURRENT_NETBOX_MIN_VERSION}",
        f"v{CURRENT_RELEASE_VERSION}",
        CURRENT_PROXBOX_API_PAIRING_LABEL,
        "v0.0.10",
        "v0.0.12",
    )
    for path in (README_PATH, DOCS_INDEX_PATH, CURRENT_RELEASE_NOTES_PATH):
        text = _read(path)
        _assert_markdown_table_row(text, current_row)

    compatibility_row = (
        f"v{CURRENT_RELEASE_VERSION}",
        f">={CURRENT_NETBOX_MIN_VERSION}",
        ">=3.12",
        CURRENT_PROXBOX_API_PAIRING_LABEL,
        "v0.0.10",
        "v0.0.12",
    )
    _assert_markdown_table_row(_read(COMPATIBILITY_PATH), compatibility_row)

    for path in (
        CLAUDE_PATH,
        COMPATIBILITY_PATH,
        DOCS_INDEX_PATH,
        UPGRADING_PATH,
        RELEASE_NOTES_INDEX_PATH,
        CURRENT_RELEASE_NOTES_PATH,
    ):
        text = _read(path)
        assert CURRENT_RELEASE_VERSION in text, f"{path} missing release version"
        assert CURRENT_PLUGIN_VERSION in text, f"{path} missing plugin version"
        assert CURRENT_PROXBOX_API_PAIRING_LABEL in text, (
            f"{path} missing backend pairing label"
        )
        assert CURRENT_PAIRING_LINE in text, f"{path} missing pairing line"


def test_0_0_23_historical_compatibility_row_is_kept():
    historical_row = (
        f">={CURRENT_NETBOX_MIN_VERSION}",
        "v0.0.23",
        CURRENT_PROXBOX_API_PAIRING_LABEL,
        "v0.0.10",
        "v0.0.12",
    )
    for path in (README_PATH, DOCS_INDEX_PATH, RELEASE_NOTES_023_PATH):
        _assert_markdown_table_row(_read(path), historical_row)

    compatibility_row = (
        "v0.0.23",
        f">={CURRENT_NETBOX_MIN_VERSION}",
        ">=3.12",
        CURRENT_PROXBOX_API_PAIRING_LABEL,
        "v0.0.10",
        "v0.0.12",
    )
    _assert_markdown_table_row(_read(COMPATIBILITY_PATH), compatibility_row)


def test_previous_release_compatibility_row_matches_release_notes():
    previous_row = (
        f">={CURRENT_NETBOX_MIN_VERSION}",
        f"v{PREVIOUS_PLUGIN_VERSION}",
        f"v{PREVIOUS_PROXBOX_API_VERSION}",
        "v0.0.10",
        "v0.0.12",
    )
    for path in (
        README_PATH,
        DOCS_INDEX_PATH,
        RELEASE_NOTES_022_PATH,
    ):
        _assert_markdown_table_row(_read(path), previous_row)
