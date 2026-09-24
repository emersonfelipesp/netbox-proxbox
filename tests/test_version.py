"""Lock the plugin version and NetBox compatibility constants in source.

The plugin's ``version``, ``min_version``, and ``max_version`` are surfaced in
several places (docs, CI, release notes). This test parses
``netbox_proxbox/__init__.py`` directly via AST so the assertions run without
loading Django or NetBox; future version bumps will fail loudly here as a
reminder to update the docs and release-notes files at the same time.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
import tomllib

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "netbox_proxbox" / "__init__.py"
COMPAT_PATH = REPO_ROOT / "netbox_proxbox" / "compat.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
README_PATH = REPO_ROOT / "README.md"
LLMS_PATH = REPO_ROOT / "llms.txt"
CLAUDE_PATH = REPO_ROOT / "CLAUDE.md"
COMPATIBILITY_PATH = REPO_ROOT / "COMPATIBILITY.md"
DOCS_INDEX_PATH = REPO_ROOT / "docs" / "index.md"
CI_E2E_WORKFLOWS_DOC_PATH = REPO_ROOT / "docs" / "developer" / "ci-e2e-workflows.md"
RELEASE_PUBLISHING_DOC_PATH = REPO_ROOT / "docs" / "developer" / "release-publishing.md"
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
RELEASE_NOTES_025_PATH = REPO_ROOT / "docs" / "release-notes" / "version-0.0.25.md"
RELEASE_NOTES_025_POST1_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.25.post1.md"
)
RELEASE_NOTES_026_POST1_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.26.post1.md"
)
RELEASE_NOTES_026_POST2_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.26.post2.md"
)
RELEASE_NOTES_026_POST3_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.26.post3.md"
)
RELEASE_NOTES_026_POST4_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.26.post4.md"
)
RELEASE_NOTES_026_POST5_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.26.post5.md"
)
RELEASE_NOTES_026_POST6_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.26.post6.md"
)
RELEASE_NOTES_026_POST7_PATH = (
    REPO_ROOT / "docs" / "release-notes" / "version-0.0.27.md"
)
E2E_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "e2e-docker.yml"
PUBLISH_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "publish-testpypi.yml"
NIGHTLY_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "nightly-contracts.yml"
DOCS_SCREENSHOTS_WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "docs-screenshots.yml"
)
DJANGO_TESTS_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "django-tests.yml"
COMPOSED_PROJECT_INPUT_PATH = (
    REPO_ROOT / "ci" / "netbox-requirements" / "netbox-proxbox-test-py312.in"
)
COMPOSED_PDM_INPUT_PATH = (
    REPO_ROOT / "ci" / "netbox-requirements" / "netbox-pdm-3408441672bf-py312.in"
)
COMPOSED_ALL_COMPANIONS_INPUT_PATH = (
    REPO_ROOT / "ci" / "netbox-requirements" / "netbox-all-companions-py312.in"
)
COMPOSED_OPENBAO_INPUT_PATH = (
    REPO_ROOT / "ci" / "netbox-requirements" / "netbox-openbao-58677ef-py312.in"
)
PAGE_COVERAGE_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "page-coverage.yml"
CERTIFICATION_PATH = REPO_ROOT / "CERTIFICATION.md"
DOCS_CERTIFICATION_PATH = REPO_ROOT / "docs" / "certification.md"
APPLICATION_PACKET_PATH = REPO_ROOT / "docs" / "application-packet.md"

CURRENT_PLUGIN_VERSION = "0.0.27rc17"
CURRENT_RELEASE_VERSION = "0.0.27rc17"
CURRENT_PACKAGE_VERSION = "0.0.27rc17"
CURRENT_PROXBOX_API_PAIRING_LABEL = "v0.0.23.post2"
CURRENT_PAIRING_LINE = (
    "Current backend-runtime pairing: netbox-proxbox 0.0.27rc17 <-> proxbox-api "
    "0.0.23.post2 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST "
    "dependency only and does not provide the semantic MCP bridge."
)
PROXBOX_API_WORKFLOW_DEFAULT_VERSION = "0.0.23.post2"
CURRENT_NETBOX_MIN_VERSION = "4.5.8"
# Ceiling of the backward-compatible stable tier, including NetBox 4.7 GA.
CURRENT_NETBOX_STABLE_MAX_VERSION = "4.7.0"
CURRENT_NETBOX_MAX_VERSION = "4.7.0"
CURRENT_NETBOX_EXPERIMENTAL_TAG = "pre-release"
CURRENT_NETBOX_SUPPORT_LABEL = "4.5.8-4.7.0 GA"
LATEST_CERTIFIED_NETBOX_VERSION = "4.7.0"
NETBOX_GA_SOURCE_REF = "5f06007e4c9bacc93ce17c1e645fc1143d60df3d"
LATEST_CERTIFIED_NETBOX_IMAGE = (
    "netboxcommunity/netbox:v4.7.0-5.1.0@sha256:"
    "73a54ff279461170032b59a57a1930929965e3ba15c195af59f4b5f6d39a84a9"
)
LATEST_CANDIDATE_NETBOX_VERSION = "4.7.0"
LATEST_CANDIDATE_NETBOX_IMAGE = LATEST_CERTIFIED_NETBOX_IMAGE
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
    LATEST_CERTIFIED_NETBOX_IMAGE,
)
E2E_DEFAULT_INSTALL_SOURCES = ("local", "pypi", "container")
E2E_EXPLICIT_INSTALL_SOURCES = (*E2E_DEFAULT_INSTALL_SOURCES, "testpypi")
DJANGO_TESTED_NETBOX_TAGS = (
    "v4.5.8",
    "v4.5.10",
    "v4.6.0",
    "v4.6.6",
    "v4.7.0",
)
DJANGO_TESTED_NETBOX_ROWS = (
    {
        "netbox": "v4.5.8",
        "pdm": False,
        "netbox_ref": "75e1b86613792458b4d4c8d0cbbfc94df16cfaaf",
        "netbox_version": "4.5.8",
        "netbox_designation": "",
        "netbox_requirements_sha256": (
            "646c5bb635d5b9b126c6af4d56664dfde461608bdcaa8a65c1735ac5d8ddde9b"
        ),
        "netbox_input_sha256": "eaa1232512302fd9eaf7c3ca1cee1ea959ba9c7001eb276025b4f4612c9593c3",
        "netbox_lock": "ci/netbox-requirements/v4.5.8-py312-linux-x86_64.txt",
        "netbox_lock_sha256": "7b515f5fd7d4b3fb03afc5b2ec3ed3b20808853de5f635fe2dc5640a1acac9fd",
    },
    {
        "netbox": "v4.5.10",
        "pdm": False,
        "netbox_ref": "b78bd713294564e0421c36c936a909e64da04b8d",
        "netbox_version": "4.5.10",
        "netbox_designation": "",
        "netbox_requirements_sha256": (
            "d68f08fb6167317174be89cda3045ee0e2fa34dd6e18ce19db2a31cf31a26e6f"
        ),
        "netbox_input_sha256": "bdfd166f32c07d4223fe2f105a4b57873923c55b13c76946cb7b56c667fb12b5",
        "netbox_lock": "ci/netbox-requirements/v4.5.10-py312-linux-x86_64.txt",
        "netbox_lock_sha256": "da7e4167ffd9a6d01fd8dbeede148170c5ecc759a798a289308b9d6952c711ba",
    },
    {
        "netbox": "v4.6.0",
        "pdm": False,
        "netbox_ref": "00791344e68213bde942218283dce03cc3941c30",
        "netbox_version": "4.6.0",
        "netbox_designation": "",
        "netbox_requirements_sha256": (
            "0d88cea37b413f22953ead2c2c341c82fe7a5e5d8a01f42632288676db8d66b6"
        ),
        "netbox_input_sha256": "d948640804f4d6f45fa42bd7b5192bd583c08cf3ac5156c2969dc87a6063857d",
        "netbox_lock": "ci/netbox-requirements/v4.6.0-py312-linux-x86_64.txt",
        "netbox_lock_sha256": "7132a376f2cd458840bb55c93268b4d09efd1aad169ff4a5aa203da62fef355b",
    },
    {
        "netbox": "v4.6.6",
        "pdm": False,
        "netbox_ref": "fb8c455ba61b57119a70670612dfdd05e8438b10",
        "netbox_version": "4.6.6",
        "netbox_designation": "",
        "netbox_requirements_sha256": (
            "25eb62e54362568599c7701a528a7ac24dbe0400d5311fc496eab866bd6174b9"
        ),
        "netbox_input_sha256": "2413106d8fd6e3e9023c73071059f7784add9c12309d70c6b349c83819cd37b1",
        "netbox_lock": "ci/netbox-requirements/v4.6.6-py312-linux-x86_64.txt",
        "netbox_lock_sha256": "91453ae85fa951ce8469f508d2304f9eefd5f6f469b1e633b0ba40734c96852f",
    },
    {
        "netbox": "v4.7.0",
        "pdm": False,
        "netbox_ref": "5f06007e4c9bacc93ce17c1e645fc1143d60df3d",
        "netbox_version": "4.7.0",
        "netbox_designation": "",
        "netbox_requirements_sha256": (
            "61589a94b25149765d230d3f33597326c3987faae7cbc20aae4c49e825c2b582"
        ),
        "netbox_input_sha256": "61589a94b25149765d230d3f33597326c3987faae7cbc20aae4c49e825c2b582",
        "netbox_lock": "ci/netbox-requirements/v4.7.0-py312-linux-x86_64.txt",
        "netbox_lock_sha256": "3345dd1b02e944b52ffb67edb05e8a7549b913924297f9ce23f7d2a92c6192c9",
    },
    {
        "netbox": "v4.6.6",
        "pdm": True,
        "netbox_ref": "fb8c455ba61b57119a70670612dfdd05e8438b10",
        "netbox_version": "4.6.6",
        "netbox_designation": "",
        "netbox_requirements_sha256": (
            "25eb62e54362568599c7701a528a7ac24dbe0400d5311fc496eab866bd6174b9"
        ),
        "netbox_input_sha256": "2413106d8fd6e3e9023c73071059f7784add9c12309d70c6b349c83819cd37b1",
        "netbox_lock": "ci/netbox-requirements/v4.6.6-pdm-3408441672bf-py312-linux-x86_64.txt",
        "netbox_lock_sha256": "f1200401205d3e8f3c0f866626d71b8e8381916e0430e5aa23b1245eaa305955",
    },
    {
        "netbox": "v4.7.0",
        "pdm": False,
        "all_companions": True,
        "netbox_ref": "5f06007e4c9bacc93ce17c1e645fc1143d60df3d",
        "netbox_version": "4.7.0",
        "netbox_designation": "",
        "netbox_requirements_sha256": (
            "61589a94b25149765d230d3f33597326c3987faae7cbc20aae4c49e825c2b582"
        ),
        "netbox_input_sha256": "61589a94b25149765d230d3f33597326c3987faae7cbc20aae4c49e825c2b582",
        "netbox_lock": "ci/netbox-requirements/v4.7.0-all-companions-py312-linux-x86_64.txt",
        "netbox_lock_sha256": (
            "e8bda99e3a415e2370973fb5e1082b2e7e0a4fabd092c244fa038851404c5508"
        ),
        "pdm_ref": "c96b425b69677107635749860e240576e91041ee",
        "ceph_ref": "227f386148219522476423a85156a72ab215ece5",
        "pbs_ref": "e00bdcab5fa519f6a2cd22d51fc329e0623af746",
        "packer_ref": "31f9ddf9652dbbbb9b34b83604acd888228caae7",
    },
    {
        "netbox": "v4.7.0",
        "pdm": False,
        "openbao": True,
        "netbox_ref": "5f06007e4c9bacc93ce17c1e645fc1143d60df3d",
        "netbox_version": "4.7.0",
        "netbox_designation": "",
        "netbox_requirements_sha256": (
            "61589a94b25149765d230d3f33597326c3987faae7cbc20aae4c49e825c2b582"
        ),
        "netbox_input_sha256": "61589a94b25149765d230d3f33597326c3987faae7cbc20aae4c49e825c2b582",
        "netbox_lock": "ci/netbox-requirements/v4.7.0-openbao-58677ef-py312-linux-x86_64.txt",
        "netbox_lock_sha256": (
            "f6d37cbf70aece0618adb9845a559fd9af867c4664ef66cf33d5c4fc33e422da"
        ),
        "openbao_ref": "58677efdd595c34cf0d597ca3efa1951b05ea25e",
        "rpc_ref": "eae471d601423195c28ffa8482422b4c1cb4344d",
    },
)
PREVIOUS_PLUGIN_VERSION = "0.0.22"
PREVIOUS_PROXBOX_API_VERSION = "0.0.19.post5"
CURRENT_RELEASE_NOTES_PATH = RELEASE_NOTES_026_POST7_PATH


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


def _combined_companion_triples(workflow: str) -> dict[str, tuple[str, str]]:
    """Return repository -> (immutable ref, pyproject digest) from the workflow."""
    parsed = yaml.safe_load(workflow)
    job = parsed["jobs"]["django-tests"]
    [combined_row] = [
        row for row in job["strategy"]["matrix"]["include"] if row.get("all_companions")
    ]
    ref_keys = {
        "emersonfelipesp/netbox-pdm": "pdm_ref",
        "emersonfelipesp/netbox-ceph": "ceph_ref",
        "emersonfelipesp/netbox-pbs": "pbs_ref",
        "emersonfelipesp/netbox-packer": "packer_ref",
    }
    [verify_step] = [
        step
        for step in job["steps"]
        if step.get("name") == "Verify exact NetBox source identity"
    ]
    digest_matches = re.findall(
        r"printf '%s  %s\\n' ([0-9a-f]{64}) \\\n\s+"
        r"(netbox-(?:pdm|ceph|pbs|packer)/pyproject\.toml)",
        verify_step["run"],
    )
    digests = {
        path.removesuffix("/pyproject.toml"): digest for digest, path in digest_matches
    }
    return {
        repository: (combined_row[ref_key], digests[repository.partition("/")[2]])
        for repository, ref_key in ref_keys.items()
    }


def _combined_registry_oracle_is_intact(source: str) -> bool:
    python_source = source[source.index("from django.apps import apps") :]
    tree = ast.parse(python_source.removesuffix("'\n"))
    installed_assignments = _named_assignments(tree, "installed")
    message_assignments = _named_assignments(tree, "plugin_messages")
    subset_asserts = _matching_asserts(tree, "expected <= installed")
    message_asserts = _matching_asserts(tree, "plugin_messages == []")
    if not all(
        len(nodes) == 1
        for nodes in (
            installed_assignments,
            message_assignments,
            subset_asserts,
            message_asserts,
        )
    ):
        return False
    expected_messages = ast.parse(
        "[message for message in run_checks() "
        'if str(getattr(message, "id", "")).partition(".")[0] in expected]',
        mode="eval",
    ).body
    return (
        ast.dump(installed_assignments[0].value)
        == ast.dump(
            ast.parse('set(registry["plugins"]["installed"])', mode="eval").body
        )
        and ast.dump(message_assignments[0].value) == ast.dump(expected_messages)
        and installed_assignments[0].lineno < subset_asserts[0].lineno
        and message_assignments[0].lineno < message_asserts[0].lineno
    )


def _named_assignments(tree: ast.Module, name: str) -> list[ast.Assign]:
    return [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == name
    ]


def _matching_asserts(tree: ast.Module, expression: str) -> list[ast.Assert]:
    expected = ast.dump(ast.parse(expression, mode="eval").body)
    return [
        node
        for node in tree.body
        if isinstance(node, ast.Assert) and ast.dump(node.test) == expected
    ]


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


def test_ga_netbox_tier_is_documented():
    """The backward-compatible GA range and prerelease advisory are documented."""
    for path in (README_PATH, COMPATIBILITY_PATH, CLAUDE_PATH):
        text = _read(path)
        assert CURRENT_NETBOX_MAX_VERSION in text, f"{path} missing declared ceiling"
        assert "4.7.0" in text, f"{path} missing GA version"
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
    ``4.7.0-beta2`` banner tells them the opposite.
    """
    text = _read(README_PATH)
    beta_marker = "4.7.0-beta2) Proxbox is running on NetBox 4.7.0-beta2"
    assert (
        beta_marker in text or "W001) Proxbox is running on NetBox 4.7.0-beta2" in text
    )
    # Locate the fenced example and check the caveat travels with it.
    start = text.index("W001) Proxbox is running on NetBox 4.7.0-beta2")
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
    parsed = yaml.safe_load(workflow)
    include = parsed["jobs"]["django-tests"]["strategy"]["matrix"]["include"]
    assert tuple(include) == DJANGO_TESTED_NETBOX_ROWS
    assert "ref: ${{ matrix.netbox_ref }}" in workflow


def test_django_netbox_locks_match_reviewed_security_inputs():
    unique_rows = {row["netbox_lock"]: row for row in DJANGO_TESTED_NETBOX_ROWS}
    for row in unique_rows.values():
        lock_path = REPO_ROOT / row["netbox_lock"]
        input_path = lock_path.parent / (f"{row['netbox']}-py312-linux-x86_64.in")
        assert input_path.is_file(), f"missing reviewed matrix input: {input_path}"
        assert lock_path.is_file(), f"missing generated dependency lock: {lock_path}"
        assert (
            hashlib.sha256(input_path.read_bytes()).hexdigest()
            == row["netbox_input_sha256"]
        )
        assert (
            hashlib.sha256(lock_path.read_bytes()).hexdigest()
            == row["netbox_lock_sha256"]
        )
        lock = _read(lock_path)
        assert "--hash=sha256:" in lock
        assert "-e " not in lock


def test_composed_project_input_matches_runtime_and_test_metadata():
    project = tomllib.loads(_read(PYPROJECT_PATH))
    expected = {
        *project["project"]["dependencies"],
        *project["project"]["optional-dependencies"]["test"],
        *project["build-system"]["requires"],
        "editables>=0.3",
    }
    observed = {
        line
        for raw_line in _read(COMPOSED_PROJECT_INPUT_PATH).splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    }
    assert observed == expected

    requirement_names = {
        re.split(r"[<>=!~;\s\[]", requirement, maxsplit=1)[0].lower().replace("_", "-")
        for requirement in observed
    }
    for row in DJANGO_TESTED_NETBOX_ROWS:
        lock = _read(REPO_ROOT / row["netbox_lock"]).lower().replace("_", "-")
        for name in requirement_names:
            assert re.search(rf"(?m)^{re.escape(name)}==", lock), (
                name,
                row["netbox_lock"],
            )


def test_pdm_composed_input_and_lock_pin_companion_runtime_metadata():
    pdm_input = _read(COMPOSED_PDM_INPUT_PATH)
    assert "setuptools>=77.0.3" in pdm_input
    assert "wheel" in pdm_input
    assert "proxmox-sdk>=0.0.12" in pdm_input
    [pdm_row] = [row for row in DJANGO_TESTED_NETBOX_ROWS if row["pdm"]]
    pdm_lock = _read(REPO_ROOT / pdm_row["netbox_lock"])
    assert "proxmox-sdk==" in pdm_lock


def test_all_companions_input_and_lock_pin_reviewed_runtime_metadata():
    companion_input = _read(COMPOSED_ALL_COMPANIONS_INPUT_PATH)
    expected_fragments = {
        "netbox-ceph 227f386148219522476423a85156a72ab215ece5",
        "netbox-pbs e00bdcab5fa519f6a2cd22d51fc329e0623af746",
        "netbox-pdm c96b425b69677107635749860e240576e91041ee",
        "netbox-packer 31f9ddf9652dbbbb9b34b83604acd888228caae7",
        "proxmox-sdk>=0.0.12",
        "setuptools>=77.0.3",
        "wheel",
    }
    for fragment in expected_fragments:
        assert fragment in companion_input
    [combined_row] = [
        row for row in DJANGO_TESTED_NETBOX_ROWS if row.get("all_companions")
    ]
    combined_lock = _read(REPO_ROOT / combined_row["netbox_lock"])
    for package in ("proxmox-sdk==", "setuptools==", "wheel=="):
        assert package in combined_lock


def test_current_ga_evidence_agrees_across_release_docs():
    for path in (
        README_PATH,
        COMPATIBILITY_PATH,
        CERTIFICATION_PATH,
        APPLICATION_PACKET_PATH,
        DOCS_INDEX_PATH,
    ):
        text = _read(path)
        assert "4.7.0" in text, f"{path} missing current GA version"
        assert NETBOX_GA_SOURCE_REF in text, f"{path} missing GA source identity"


def test_django_tests_pin_reviewed_execution_inputs():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    assert "runs-on: ubuntu-24.04" in workflow
    assert (
        workflow.count(
            "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
        )
        == 8
    )
    assert (
        "uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
        in workflow
    )
    assert (
        "uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990" in workflow
    )
    assert 'version: "0.11.28"' in workflow
    assert 'python-version: "3.12.13"' in workflow
    assert "postgres:16-alpine@sha256:cf78e766" in workflow
    assert "redis:7-alpine@sha256:ff02b58f" in workflow


def test_django_tests_use_read_only_nonpersistent_checkout_credentials():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    assert "permissions:\n  contents: read" in workflow
    parsed = yaml.safe_load(workflow)
    checkout_steps = [
        step
        for step in parsed["jobs"]["django-tests"]["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert len(checkout_steps) == 8
    assert all(step["with"]["persist-credentials"] is False for step in checkout_steps)


def test_release_screenshots_validate_the_tag_without_writing_from_tag_events():
    parsed = yaml.safe_load(_read(DOCS_SCREENSHOTS_WORKFLOW_PATH))
    steps = parsed["jobs"]["capture-screenshots"]["steps"]
    checkout = next(step for step in steps if step.get("name") == "Checkout repository")
    publish = next(
        step for step in steps if step.get("name") == "Commit and push screenshots"
    )

    assert checkout["with"]["ref"] == (
        "${{ startsWith(github.ref, 'refs/tags/') && github.sha || github.ref_name }}"
    )
    assert publish["if"] == "github.event_name == 'workflow_dispatch'"
    assert 'git pull --rebase origin "${GITHUB_REF_NAME}"' in publish["run"]
    assert 'git push origin "HEAD:${GITHUB_REF_NAME}"' in publish["run"]


def test_django_tests_isolate_optional_openbao_suites_to_the_companion_cell():
    parsed = yaml.safe_load(_read(DJANGO_TESTS_WORKFLOW_PATH))
    run = next(
        step["run"]
        for step in parsed["jobs"]["django-tests"]["steps"]
        if step.get("name") == "Run NetBox-backed model, view, and integration tests"
    )

    assert 'if [[ "${{ matrix.openbao }}" == "true" ]]' in run
    assert 'selected_tests+=("${openbao_tests[@]}")' in run
    assert '.venv/bin/pytest "${selected_tests[@]}"' in run
    common = run[run.index("common_tests=(") : run.index("openbao_tests=(")]
    isolated = run[run.index("openbao_tests=(") : run.index("selected_tests=(")]
    for suite in (
        "tests/test_openbao_assignments_django.py",
        "tests/test_openbao_node_assignments_django.py",
        "tests/test_openbao_single_secret_django.py",
        "tests/test_openbao_cloudinit_django.py",
        "tests/test_openbao_setup_django.py",
    ):
        assert suite in isolated
        assert suite not in common
    for suite in (
        "tests/test_backend_key_adoption_django.py",
        "tests/test_encryption_key_recovery_django.py",
        "tests/test_detail_view_templates_django.py",
        "tests/test_packer_endpoint_authorization_django.py",
    ):
        assert suite in common


def test_django_tests_pin_source_identity_proof():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    assert "uv venv --python 3.12.13" in workflow
    assert "Verify exact NetBox source identity" in workflow
    assert "git -C netbox rev-parse HEAD" in workflow
    assert "refs/tags/$EXPECTED_NETBOX_TAG:refs/tags/$EXPECTED_NETBOX_TAG" in workflow
    assert 'git -C netbox rev-parse "$EXPECTED_NETBOX_TAG^{commit}"' in workflow
    assert "netbox/netbox/release.yaml" in workflow
    assert "sha256sum --check --strict" in workflow


def test_django_tests_enforce_one_hashed_resolution_and_metadata_check():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    assert "--require-hashes" in workflow
    assert "--default-index https://pypi.org/simple" in workflow
    assert "--index-strategy first-index" in workflow
    assert '-r "${{ matrix.netbox_lock }}"' in workflow
    assert workflow.count("--no-build-isolation --no-deps") == 5
    assert "uv pip check --python .venv/bin/python" in workflow
    assert "../netbox/requirements.txt" not in workflow


def test_django_tests_pin_combined_companion_checkouts():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    parsed = yaml.safe_load(workflow)
    matrix_rows = parsed["jobs"]["django-tests"]["strategy"]["matrix"]["include"]
    [combined_row] = [row for row in matrix_rows if row.get("all_companions")]
    assert {
        key: combined_row[key]
        for key in ("pdm_ref", "ceph_ref", "pbs_ref", "packer_ref")
    } == {
        "pdm_ref": "c96b425b69677107635749860e240576e91041ee",
        "ceph_ref": "227f386148219522476423a85156a72ab215ece5",
        "pbs_ref": "e00bdcab5fa519f6a2cd22d51fc329e0623af746",
        "packer_ref": "31f9ddf9652dbbbb9b34b83604acd888228caae7",
    }
    steps = parsed["jobs"]["django-tests"]["steps"]
    checkout_steps = {
        step["with"]["repository"]: step["with"]
        for step in steps
        if step.get("name", "").startswith("Checkout supported")
    }
    assert checkout_steps["emersonfelipesp/netbox-pdm"]["ref"] == (
        "${{ matrix.all_companions && matrix.pdm_ref || "
        "'3408441672bf849dfaf953d96d6e0ba1561cd576' }}"
    )
    for repository, ref_name in (
        ("emersonfelipesp/netbox-ceph", "ceph_ref"),
        ("emersonfelipesp/netbox-pbs", "pbs_ref"),
        ("emersonfelipesp/netbox-packer", "packer_ref"),
    ):
        assert checkout_steps[repository]["ref"] == f"${{{{ matrix.{ref_name} }}}}"
    assert all(step["persist-credentials"] is False for step in checkout_steps.values())


def test_django_tests_bind_companion_repositories_refs_and_pyproject_digests():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    expected = {
        "emersonfelipesp/netbox-pdm": (
            "c96b425b69677107635749860e240576e91041ee",
            "bf9ff5877ba6a3257d01804b78128510ada750e70aa344316dbf181b71c00b46",
        ),
        "emersonfelipesp/netbox-ceph": (
            "227f386148219522476423a85156a72ab215ece5",
            "407633d87cc6fc096d0a3824e2eaa9efd4ceda7486f70b2b65197c30450e82d9",
        ),
        "emersonfelipesp/netbox-pbs": (
            "e00bdcab5fa519f6a2cd22d51fc329e0623af746",
            "da206270a647fe3bb5a26e3cb1136e39d7344bef8375a5fb20e11637ff318e7e",
        ),
        "emersonfelipesp/netbox-packer": (
            "31f9ddf9652dbbbb9b34b83604acd888228caae7",
            "5f1b95feee604e4f617bffa0bb6efa548c3f12e02b28c57902754f599ab964fe",
        ),
    }
    assert _combined_companion_triples(workflow) == expected
    for repository, (_, digest) in expected.items():
        mutated = workflow.replace(digest, "0" * 64)
        assert _combined_companion_triples(mutated)[repository] != expected[repository]


def test_django_tests_pin_combined_companion_registry_contract():
    parsed = yaml.safe_load(_read(DJANGO_TESTS_WORKFLOW_PATH))
    steps = parsed["jobs"]["django-tests"]["steps"]
    [registry_step] = [
        step
        for step in steps
        if step.get("name") == "Prove the combined NetBox 4.7 companion registry"
    ]
    assert registry_step["if"] == "matrix.all_companions"
    for plugin in (
        "netbox_proxbox",
        "netbox_ceph",
        "netbox_pbs",
        "netbox_pdm",
        "netbox_packer",
    ):
        assert plugin in registry_step["run"]
    oracle = registry_step["run"]
    assert "apps.is_installed(plugin)" in oracle
    assert _combined_registry_oracle_is_intact(oracle)
    assert 'NETBOX_PROXBOX_TEST_ALL_COMPANIONS: "1"' in _read(
        DJANGO_TESTS_WORKFLOW_PATH
    )


def test_django_tests_reject_mutated_combined_registry_oracle():
    parsed = yaml.safe_load(_read(DJANGO_TESTS_WORKFLOW_PATH))
    [registry_step] = [
        step
        for step in parsed["jobs"]["django-tests"]["steps"]
        if step.get("name") == "Prove the combined NetBox 4.7 companion registry"
    ]
    oracle = registry_step["run"]
    mutations = (
        oracle.replace(
            "message for message in run_checks()", "message for message in []"
        ),
        oracle.replace("[0] in expected", "[0] not in expected"),
        oracle.replace("expected <= installed", "installed <= expected"),
        oracle.replace("plugin_messages == []", "plugin_messages != []"),
        oracle.replace("assert expected <= installed, (expected, installed)\n", ""),
    )
    assert all(not _combined_registry_oracle_is_intact(mutant) for mutant in mutations)


def test_django_tests_reject_plugin_messages_shadow_assignment():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    oracle = next(
        step["run"]
        for step in yaml.safe_load(workflow)["jobs"]["django-tests"]["steps"]
        if step.get("name") == "Prove the combined NetBox 4.7 companion registry"
    )
    mutant = oracle.replace(
        "assert plugin_messages == [], plugin_messages",
        "plugin_messages = []\nassert plugin_messages == [], plugin_messages",
    )
    assert not _combined_registry_oracle_is_intact(mutant)


def test_django_tests_reject_installed_shadow_assignment():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    oracle = next(
        step["run"]
        for step in yaml.safe_load(workflow)["jobs"]["django-tests"]["steps"]
        if step.get("name") == "Prove the combined NetBox 4.7 companion registry"
    )
    mutant = oracle.replace(
        "assert expected <= installed, (expected, installed)",
        "installed = set(expected)\nassert expected <= installed, (expected, installed)",
    )
    assert not _combined_registry_oracle_is_intact(mutant)


def test_django_tests_verify_companion_heads_and_metadata():
    workflow = _read(DJANGO_TESTS_WORKFLOW_PATH)
    assert 'git -C "$companion" rev-parse HEAD' in workflow
    for path in (
        "netbox-pdm/pyproject.toml",
        "netbox-ceph/pyproject.toml",
        "netbox-pbs/pyproject.toml",
        "netbox-packer/pyproject.toml",
    ):
        assert path in workflow


def test_django_tests_verify_composed_dependency_artifact_checksums():
    """Pin every binding, consumption, and target in the checksum gate."""
    parsed = yaml.safe_load(_read(DJANGO_TESTS_WORKFLOW_PATH))
    [verify_step] = [
        step
        for step in parsed["jobs"]["django-tests"]["steps"]
        if step.get("name") == "Verify exact NetBox source identity"
    ]
    verify_env = verify_step["env"]
    verify_run = verify_step["run"]
    observed_contract = {
        "bindings": (
            verify_env.get("EXPECTED_REQUIREMENTS_SHA256"),
            verify_env.get("EXPECTED_INPUT_SHA256"),
            verify_env.get("EXPECTED_LOCK_SHA256"),
            verify_env.get("EXPECTED_PROJECT_INPUT_SHA256"),
            verify_env.get("EXPECTED_PDM_INPUT_SHA256"),
            verify_env.get("EXPECTED_PDM_PYPROJECT_SHA256"),
            verify_env.get("EXPECTED_ALL_COMPANIONS_INPUT_SHA256"),
            verify_env.get("EXPECTED_OPENBAO_INPUT_SHA256"),
        ),
        "consumption_counts": (
            verify_run.count("$EXPECTED_REQUIREMENTS_SHA256"),
            verify_run.count("$EXPECTED_INPUT_SHA256"),
            verify_run.count("$EXPECTED_LOCK_SHA256"),
            verify_run.count("sha256sum --check --strict"),
        ),
        "targets_present": (
            '"$EXPECTED_REQUIREMENTS_SHA256" netbox/requirements.txt' in verify_run,
            'input_path="ci/netbox-requirements/${EXPECTED_NETBOX_TAG}-py312-linux-x86_64.in"'
            in verify_run,
            '"$EXPECTED_INPUT_SHA256" "netbox-proxbox/$input_path"' in verify_run,
            '"$EXPECTED_LOCK_SHA256" "netbox-proxbox/$EXPECTED_NETBOX_LOCK"'
            in verify_run,
            '"$EXPECTED_PROJECT_INPUT_SHA256"' in verify_run,
            '"$EXPECTED_PDM_INPUT_SHA256"' in verify_run,
            '"$EXPECTED_PDM_PYPROJECT_SHA256" netbox-pdm/pyproject.toml' in verify_run,
            '"$EXPECTED_ALL_COMPANIONS_INPUT_SHA256"' in verify_run,
            "netbox-all-companions-py312.in" in verify_run,
            '"$EXPECTED_OPENBAO_INPUT_SHA256"' in verify_run,
            "netbox-openbao-58677ef-py312.in" in verify_run,
        ),
    }
    assert observed_contract == {
        "bindings": (
            "${{ matrix.netbox_requirements_sha256 }}",
            "${{ matrix.netbox_input_sha256 }}",
            "${{ matrix.netbox_lock_sha256 }}",
            "54ee51ae82ab1ec26e1de7a5f07634eff981013a8b41e62cced50e8a99d3fd18",
            "424c8807691eaa50c53762e6b1dbddbbe4489fe0b2a9bd15d142acb17699d50e",
            "496d7924629f7aa98452d302a33ce9b47c1533079f4a4320b92ee8b18133cfce",
            "7b277c8c7baf88778fac40258dca059212097e36dede04d1250f920a3ec7994b",
            "5c60d62b4e84eaff3350e37045edc8b208c3b28b144815772c7dda0b2f754d85",
        ),
        "consumption_counts": (1, 1, 1, 14),
        "targets_present": (
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
        ),
    }


def test_page_coverage_pins_latest_certified_netbox():
    workflow = _read(PAGE_COVERAGE_WORKFLOW_PATH)
    assert workflow.count(f"NETBOX_IMAGE: {LATEST_CANDIDATE_NETBOX_IMAGE}") == 1
    assert (
        f"name: Page Coverage / {LATEST_CANDIDATE_NETBOX_IMAGE} / local / pve"
        in workflow
    )
    assert f"PROXBOX_API_VERSION: {PROXBOX_API_WORKFLOW_DEFAULT_VERSION}" in workflow


def test_e2e_harness_does_not_call_removed_custom_fields_route() -> None:
    paths = [*(REPO_ROOT / "tests" / "e2e").glob("*.py")]
    paths.append(REPO_ROOT / "scripts" / "capture_screenshots.py")
    harness = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "extras/extras/custom-fields/create" not in harness
    assert "create_proxbox_custom_fields" not in harness


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
        RELEASE_NOTES_025_PATH,
        RELEASE_NOTES_025_POST1_PATH,
        RELEASE_NOTES_026_POST1_PATH,
        RELEASE_NOTES_026_POST2_PATH,
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


def _assert_release_workflow_e2e_counts(publish_workflow: str) -> None:
    assert "dependency_mode: testpypi-package" not in publish_workflow
    assert publish_workflow.count("dependency_mode: pypi-package") == 3
    assert (
        publish_workflow.count(
            "proxbox_api_version: ${{ needs.prepare-release.outputs.proxbox_api_version }}"
        )
        == 3
    )


def test_release_workflow_uses_matching_package_indexes_for_e2e() -> None:
    # The release workflow pairs each E2E gate with the same package index the
    # plugin is being validated against: the TestPyPI plugin candidate uses the
    # stable proxbox-api from PyPI because proxbox-api 0.0.23.post2 is not published
    # on TestPyPI. PyPI candidate and final gates use that same PyPI source.
    # `dependency_mode: dev` clones
    # proxbox-api main HEAD and must not appear here — main may sit on a
    # different release line than the rc/tag being validated.
    publish_workflow = PUBLISH_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "--skip-existing" not in publish_workflow
    assert "PROXBOX_API_PYPI_VERSION" in publish_workflow

    assert "install_source: testpypi" in publish_workflow
    assert "install_source: local" in publish_workflow
    assert "install_source: pypi" in publish_workflow
    assert "dependency_mode: dev" not in publish_workflow
    _assert_release_workflow_e2e_counts(publish_workflow)


def test_release_workflow_defaults_to_current_proxbox_api() -> None:
    publish_workflow = PUBLISH_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "vars.PROXBOX_API_RELEASE_VERSION || '0.0.23.post2'" in publish_workflow
    assert (
        "vars.PROXBOX_API_PYPI_VERSION || vars.PROXBOX_API_RELEASE_VERSION || '0.0.23.post2'"
        in publish_workflow
    )
    assert "PROXBOX_API_REQUIRED_DEFAULT_VERSION: 0.0.23.post2" in publish_workflow
    assert (
        "from scripts.e2e_backend_selection import resolve_release_version"
        in publish_workflow
    )
    assert "proxbox_api_version = resolve_release_version(" in publish_workflow


def test_operational_docs_pin_current_proxbox_api_default() -> None:
    expected_requirement = f"proxbox-api=={PROXBOX_API_WORKFLOW_DEFAULT_VERSION}"
    ci_e2e_docs = CI_E2E_WORKFLOWS_DOC_PATH.read_text(encoding="utf-8")
    release_docs = RELEASE_PUBLISHING_DOC_PATH.read_text(encoding="utf-8")

    assert expected_requirement in ci_e2e_docs
    assert expected_requirement in release_docs
    assert f"checked-in `{PROXBOX_API_WORKFLOW_DEFAULT_VERSION}` default" in ci_e2e_docs


def test_e2e_defaults_to_exact_published_backend() -> None:
    workflow = E2E_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert workflow.count("default: published") == 2
    assert (
        "PROXBOX_API_DEPENDENCY_MODE_INPUT: ${{ inputs.dependency_mode }}" in workflow
    )
    assert "PROXBOX_API_VERSION_INPUT: ${{ inputs.proxbox_api_version }}" in workflow
    assert "scripts/e2e_backend_selection.py dependency-mode" in workflow
    assert "scripts/e2e_backend_selection.py version" in workflow
    assert 'if [ "${PROXBOX_API_DEPENDENCY_MODE}" = "published" ]; then' in workflow
    assert 'elif [ "${PROXBOX_API_DEPENDENCY_MODE}" = "dev" ]; then' in workflow
    assert (
        "git clone --depth 1 https://github.com/emersonfelipesp/proxbox-api.git"
        in workflow
    )


def test_e2e_installs_backend_selection_dependency_before_use() -> None:
    workflow = yaml.safe_load(E2E_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["e2e-docker-stack"]["steps"]
    step_names = [step["name"] for step in steps]
    install_index = step_names.index("Install test dependencies")
    selection_index = step_names.index("Resolve proxbox-api runtime source")

    assert install_index < selection_index
    assert (
        "python -m pip install 'packaging==26.0' requests"
        in steps[install_index]["run"]
    )


def test_e2e_workflow_supports_proxbox_api_package_index_runtime_modes():
    e2e_workflow = E2E_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "- testpypi" in e2e_workflow
    assert "- testpypi-package" in e2e_workflow
    assert "- pypi-package" in e2e_workflow
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
        CURRENT_NETBOX_SUPPORT_LABEL,
        f"v{CURRENT_RELEASE_VERSION}",
        CURRENT_PROXBOX_API_PAIRING_LABEL,
        "v0.0.13",
        "v0.0.15",
    )
    for path in (README_PATH, DOCS_INDEX_PATH, CURRENT_RELEASE_NOTES_PATH):
        text = _read(path)
        _assert_markdown_table_row(text, current_row)

    compatibility_row = (
        f"v{CURRENT_RELEASE_VERSION}",
        CURRENT_NETBOX_SUPPORT_LABEL,
        ">=3.12",
        CURRENT_PROXBOX_API_PAIRING_LABEL,
        "v0.0.13",
        "v0.0.15",
    )
    _assert_markdown_table_row(_read(COMPATIBILITY_PATH), compatibility_row)
    assert f"Plugin version `{CURRENT_PLUGIN_VERSION}` in source" in _read(
        DOCS_INDEX_PATH
    )

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
