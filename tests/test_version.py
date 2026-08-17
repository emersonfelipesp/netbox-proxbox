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
COMPAT_PATH = REPO_ROOT / "netbox_proxbox" / "compat.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
README_PATH = REPO_ROOT / "README.md"
LLMS_PATH = REPO_ROOT / "llms.txt"
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
RELEASE_NOTES_023_POST2_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.23.post2.md"
)
RELEASE_NOTES_024_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.24.md"
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

CURRENT_PLUGIN_VERSION = "0.0.24"
CURRENT_RELEASE_VERSION = "0.0.24"
CURRENT_PACKAGE_VERSION = "0.0.24rc1"
CURRENT_PROXBOX_API_PAIRING_LABEL = "v0.0.20"
CURRENT_PAIRING_LINE = (
    "Current backend-runtime pairing: netbox-proxbox 0.0.24 <-> proxbox-api "
    "0.0.20 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST "
    "dependency only and does not provide the semantic MCP bridge."
)
PROXBOX_API_WORKFLOW_DEFAULT_VERSION = "0.0.20"
CURRENT_NETBOX_MIN_VERSION = "4.5.8"
# Ceiling of the certified, CI-gated tier. Docs that describe *supported*
# NetBox still quote this range.
CURRENT_NETBOX_STABLE_MAX_VERSION = "4.6.99"
# Ceiling actually declared on ProxboxConfig.max_version — the experimental
# tier. NetBox 4.7 is admitted without an opt-in and warns at startup.
CURRENT_NETBOX_MAX_VERSION = "4.7.99"
CURRENT_NETBOX_EXPERIMENTAL_MIN_VERSION = "4.7.0"
LATEST_CERTIFIED_NETBOX_VERSION = "4.6.6"
LATEST_CERTIFIED_NETBOX_IMAGE = (
    f"netboxcommunity/netbox:v{LATEST_CERTIFIED_NETBOX_VERSION}"
)
LATEST_CANDIDATE_NETBOX_VERSION = "4.6.6"
LATEST_CANDIDATE_NETBOX_IMAGE = (
    f"netboxcommunity/netbox:v{LATEST_CANDIDATE_NETBOX_VERSION}"
)
SUPPORTED_NETBOX_IMAGE_TAGS = (
    "netboxcommunity/netbox:v4.5.8",
    "netboxcommunity/netbox:v4.5.9",
    "netboxcommunity/netbox:v4.5.10",
    "netboxcommunity/netbox:v4.6.0",
    "netboxcommunity/netbox:v4.6.1",
    "netboxcommunity/netbox:v4.6.2",
    "netboxcommunity/netbox:v4.6.3",
    "netboxcommunity/netbox:v4.6.4",
    "netboxcommunity/netbox:v4.6.5",
    "netboxcommunity/netbox:v4.6.6",
)
E2E_DEFAULT_INSTALL_SOURCES = ("local", "pypi", "container")
E2E_EXPLICIT_INSTALL_SOURCES = (*E2E_DEFAULT_INSTALL_SOURCES, "testpypi")
DJANGO_TESTED_NETBOX_TAGS = (
    "v4.5.8",
    "v4.5.10",
    "v4.6.0",
    "v4.6.6",
    # Experimental tier. Pinned to the immutable beta tag and required,
    # not continue-on-error.
    "v4.7.0-beta1",
)
PREVIOUS_PLUGIN_VERSION = "0.0.22"
PREVIOUS_PROXBOX_API_VERSION = "0.0.19.post5"
CURRENT_RELEASE_NOTES_PATH = RELEASE_NOTES_024_PATH


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


def test_current_release_version_identity_is_exact():
    constants = _class_constants("ProxboxConfig")
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    config_version = constants.get("version")
    pyproject_version = pyproject["project"]["version"]

    assert config_version == pyproject_version == CURRENT_PACKAGE_VERSION, (
        "release version identity drifted: "
        f"ProxboxConfig.version={config_version!r}, "
        f"pyproject.toml={pyproject_version!r}, "
        f"package constant={CURRENT_PACKAGE_VERSION!r}"
    )


def _compat_constants() -> dict[str, str]:
    """Module-level string constants declared in netbox_proxbox/compat.py.

    Resolves one level of aliasing, because the values the plugin actually
    declares (`PLUGIN_MIN_VERSION`, `PLUGIN_MAX_VERSION`) are assigned from the
    band constants rather than re-typed as literals.
    """
    module = ast.parse(COMPAT_PATH.read_text(encoding="utf-8"))
    constants: dict[str, str] = {}
    for stmt in module.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            value = stmt.value.value
        elif isinstance(stmt.value, ast.Name) and stmt.value.id in constants:
            value = constants[stmt.value.id]
        else:
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value
    return constants


def _class_constant_names(class_name: str) -> dict[str, str]:
    """Class attributes assigned from a bare name, e.g. `min_version = X`."""
    module = ast.parse(INIT_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            names: dict[str, str] = {}
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Name):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            names[target.id] = stmt.value.id
            return names
    raise AssertionError(f"class {class_name} not found in {INIT_PATH}")


def test_min_max_netbox_versions_are_pinned():
    compat = _compat_constants()
    assert compat["STABLE_MIN_NETBOX_VERSION"] == CURRENT_NETBOX_MIN_VERSION
    assert compat["STABLE_MAX_NETBOX_VERSION"] == CURRENT_NETBOX_STABLE_MAX_VERSION
    assert (
        compat["EXPERIMENTAL_MIN_NETBOX_VERSION"]
        == CURRENT_NETBOX_EXPERIMENTAL_MIN_VERSION
    )
    assert compat["EXPERIMENTAL_MAX_NETBOX_VERSION"] == CURRENT_NETBOX_MAX_VERSION
    assert compat["PLUGIN_MIN_VERSION"] == CURRENT_NETBOX_MIN_VERSION
    assert compat["PLUGIN_MAX_VERSION"] == CURRENT_NETBOX_MAX_VERSION


def test_plugin_config_bounds_are_wired_to_compat():
    """The declared bounds must come from compat.py, not a re-typed literal.

    Two copies of the range would drift silently; this asserts there is only one.
    """
    names = _class_constant_names("ProxboxConfig")
    assert names.get("min_version") == "PLUGIN_MIN_VERSION"
    assert names.get("max_version") == "PLUGIN_MAX_VERSION"
    literals = _class_constants("ProxboxConfig")
    assert "min_version" not in literals
    assert "max_version" not in literals


def test_certified_netbox_versions_are_documented():
    compat = _compat_constants()
    assert compat["PLUGIN_MIN_VERSION"] == CURRENT_NETBOX_MIN_VERSION
    assert compat["PLUGIN_MAX_VERSION"] == CURRENT_NETBOX_MAX_VERSION

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
        assert CURRENT_NETBOX_STABLE_MAX_VERSION in text, (
            f"{path} missing certified max version"
        )


#: Every page an operator could reasonably consult for "which NetBox does this
#: support". All of them must agree, because sending someone to a page that
#: still names the old ceiling is how a mixed upgrade happens.
COMPATIBILITY_AUTHORITY_PATHS = (
    README_PATH,
    COMPATIBILITY_PATH,
    CLAUDE_PATH,
    DOCS_INDEX_PATH,
    INSTALL_GIT_PATH,
    UPGRADING_PATH,
    APPLICATION_PACKET_PATH,
)


def test_experimental_netbox_tier_is_documented():
    """The experimental tier must be stated where operators actually look."""
    for path in (README_PATH, COMPATIBILITY_PATH, CLAUDE_PATH):
        text = _read(path)
        assert CURRENT_NETBOX_MAX_VERSION in text, (
            f"{path} missing experimental ceiling"
        )
        assert "experimental" in text.lower(), f"{path} does not name the tier"
    # And the silencing escape hatch must be discoverable, since the warning is
    # the one visible change an upgrading operator sees. NetBox does not read
    # SILENCED_SYSTEM_CHECKS from configuration.py, so the PLUGINS_CONFIG key is
    # the mechanism that has to be documented.
    for path in (README_PATH, COMPATIBILITY_PATH):
        assert "silence_netbox_compatibility_warning" in _read(path), (
            f"{path} does not document how to silence the notice"
        )


def test_every_page_that_discusses_the_ceiling_names_the_current_one():
    """Presence-somewhere checks are not enough — contradictions have to fail.

    The regression this catches is real: `docs/index.md` named the new tier in a
    table near the top and then, forty lines later, listed
    ``max_version = "4.6.99"`` as the declared value. An operator who scrolled
    to the second statement would conclude 4.7 is unsupported.

    The rule is deliberately shaped to avoid false positives. A page may
    legitimately quote ``4.6.99`` while describing *something else* — the
    previously published package, `netbox-branching`, an older companion
    artifact — so the assertion is not "never mention it". It is: **if a page
    discusses `max_version` at all, it must name the current declared ceiling**,
    so the two statements are never available to a reader in isolation.
    """
    for path in COMPATIBILITY_AUTHORITY_PATHS:
        text = _read(path)
        if "max_version" not in text:
            continue
        assert CURRENT_NETBOX_MAX_VERSION in text, (
            f"{path} discusses max_version but never names the current declared "
            f"ceiling {CURRENT_NETBOX_MAX_VERSION}; a reader landing there is "
            f"told the maximum is {CURRENT_NETBOX_STABLE_MAX_VERSION}"
        )


def test_the_beta_example_keeps_the_prerelease_caveat():
    """A README example showing the stable hint for a beta undoes the warning.

    The pre-release paragraph is the only thing telling an operator that
    upstream does not support the release in production and offers no upgrade
    path to GA. An example that quotes the *stable* hint next to a
    ``4.7.0-beta1`` banner tells them the opposite.
    """
    text = _read(README_PATH)
    beta_marker = "4.7.0-beta1) Proxbox is running on NetBox 4.7.0-beta1"
    assert beta_marker in text or "W001) Proxbox is running on NetBox 4.7.0-beta1" in text
    # Locate the fenced example and check the caveat travels with it.
    start = text.index("W001) Proxbox is running on NetBox 4.7.0-beta1")
    example = text[start : text.index("```", start)]
    assert "pre-release" in example.lower(), (
        "the beta example dropped the pre-release caveat"
    )
    assert "fully operational" not in example, (
        "the beta example quotes the stable hint, which reads as production "
        "clearance for a pre-release"
    )


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
    assert workflow.count(f"NETBOX_IMAGE: {LATEST_CANDIDATE_NETBOX_IMAGE}") == 1


def test_django_tests_pin_expected_netbox_matrix():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    expected_matrix = json.dumps(list(DJANGO_TESTED_NETBOX_TAGS))
    assert f"        netbox: {expected_matrix}" in workflow


def test_page_coverage_pins_latest_certified_netbox():
    workflow = _read(PAGE_COVERAGE_WORKFLOW_PATH)
    assert workflow.count(f"NETBOX_IMAGE: {LATEST_CANDIDATE_NETBOX_IMAGE}") == 1
    assert (
        f"name: Page Coverage / {LATEST_CANDIDATE_NETBOX_IMAGE} / local / pve"
        in workflow
    )


def _contains_exact_version(text, version):
    """True when *version* appears as an exact token, not as a prefix.

    Substring membership would let "4.6.50" satisfy a "4.6.5" assertion and
    "0.0.23.post10" satisfy "0.0.23.post1"; require a non-version character
    (or end of string) after the match.
    """
    import re

    return re.search(rf"(?<![0-9.]){re.escape(version)}(?![0-9])", text) is not None


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
        assert _contains_exact_version(text, CURRENT_NETBOX_MIN_VERSION), (
            f"{path} missing certified floor"
        )
        assert _contains_exact_version(text, LATEST_CERTIFIED_NETBOX_VERSION), (
            f"{path} missing latest certified version"
        )


def test_certification_evidence_names_the_tested_plugin_artifact():
    for path in (CERTIFICATION_PATH, APPLICATION_PACKET_PATH):
        text = _read(path)
        assert _contains_exact_version(text, CURRENT_RELEASE_VERSION), (
            f"{path} missing tested plugin artifact"
        )
        assert "0.0.18.post1" not in text, (
            f"{path} still names the historical certification target"
        )


def test_exact_version_matcher_rejects_prefix_collisions():
    assert _contains_exact_version("certified against 4.6.5.", "4.6.5")
    assert not _contains_exact_version("certified against 4.6.50", "4.6.5")
    assert not _contains_exact_version("certified against 14.6.5", "4.6.5")
    assert _contains_exact_version("artifact 0.0.23.post1 tested", "0.0.23.post1")
    assert not _contains_exact_version("artifact 0.0.23.post10 tested", "0.0.23.post1")


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

    assert project["version"] == CURRENT_PACKAGE_VERSION
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
        RELEASE_NOTES_023_POST2_PATH,
        RELEASE_NOTES_024_PATH,
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
        "v0.0.13",
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
        "v0.0.13",
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
        assert CURRENT_PROXBOX_API_PAIRING_LABEL.removeprefix("v") in text, (
            f"{path} missing backend pairing label"
        )
        assert CURRENT_PAIRING_LINE in text, f"{path} missing pairing line"


def test_0_0_23_historical_compatibility_row_is_kept():
    historical_row = (
        f">={CURRENT_NETBOX_MIN_VERSION}",
        "v0.0.23",
        "guest-VM-interface writer build / next release",
        "v0.0.10",
        "v0.0.12",
    )
    for path in (README_PATH, DOCS_INDEX_PATH, RELEASE_NOTES_023_PATH):
        _assert_markdown_table_row(_read(path), historical_row)

    compatibility_row = (
        "v0.0.23",
        f">={CURRENT_NETBOX_MIN_VERSION}",
        ">=3.12",
        "guest-VM-interface writer build / next release",
        "v0.0.10",
        "v0.0.12",
    )
    _assert_markdown_table_row(_read(COMPATIBILITY_PATH), compatibility_row)


def test_llms_index_identifies_current_plugin_version() -> None:
    assert f"Plugin version: `{CURRENT_PLUGIN_VERSION}`" in _read(LLMS_PATH)


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


def test_packaging_is_a_declared_dependency() -> None:
    """`compat.py` imports packaging at module scope, so the metadata must say so.

    Inside a NetBox install it happens to be present transitively — NetBox core
    uses it on the very same `PluginConfig.validate` path — and pytest drags it
    in during CI. Neither is a declaration. Without this the wheel's metadata
    misstates what the package imports, and a consumer resolving it outside a
    NetBox environment gets an ImportError at plugin import time.
    """
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    declared = data["project"]["dependencies"]

    assert any(spec.split(">=")[0].strip() == "packaging" for spec in declared), (
        f"packaging must be declared in [project.dependencies]; got {declared}"
    )
