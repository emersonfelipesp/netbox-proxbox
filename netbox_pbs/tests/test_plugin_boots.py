"""AST-based smoke tests for the netbox-pbs plugin scaffold.

These tests parse source files with ``ast`` instead of bootstrapping Django,
mirroring the pattern used by ``netbox_proxbox/tests/test_version.py``.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
INIT_PATH = REPO_ROOT / "netbox_pbs" / "__init__.py"
MODELS_PATH = REPO_ROOT / "netbox_pbs" / "models" / "plugin_settings.py"
URLS_PATH = REPO_ROOT / "netbox_pbs" / "urls.py"
NAVIGATION_PATH = REPO_ROOT / "netbox_pbs" / "navigation.py"
MIGRATION_PATH = REPO_ROOT / "netbox_pbs" / "migrations" / "0001_initial.py"

EXPECTED_VERSION = "0.0.1"
EXPECTED_MIN_NETBOX = "4.5.8"
EXPECTED_MAX_NETBOX = "4.6.99"


def _class_constants(path: Path, class_name: str) -> dict[str, object]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            constants: dict[str, object] = {}
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and isinstance(
                    stmt.value, ast.Constant
                ):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            constants[target.id] = stmt.value.value
            return constants
    raise AssertionError(f"class {class_name} not found in {path}")


def test_pyproject_declares_separate_wheel():
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    assert data["project"]["name"] == "netbox-pbs"
    assert data["project"]["version"] == EXPECTED_VERSION
    packages = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert packages == ["netbox_pbs"], (
        "wheel must only ship netbox_pbs, not netbox_proxbox"
    )


def test_pyproject_does_not_depend_on_netbox_proxbox():
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    deps = list(data["project"].get("dependencies", []))
    normalized = [d.lower().replace("_", "-") for d in deps]
    assert not any(d.startswith("netbox-proxbox") for d in normalized), (
        "netbox-pbs must boot standalone — netbox-proxbox is only a soft "
        "(optional) cross-link"
    )


def test_pluginconfig_pins_metadata():
    constants = _class_constants(INIT_PATH, "PBSConfig")
    assert constants["name"] == "netbox_pbs"
    assert constants["version"] == EXPECTED_VERSION
    assert constants["base_url"] == "pbs"
    assert constants["min_version"] == EXPECTED_MIN_NETBOX
    assert constants["max_version"] == EXPECTED_MAX_NETBOX


def test_plugin_settings_singleton_shape():
    text = MODELS_PATH.read_text(encoding="utf-8")
    assert "class PBSPluginSettings" in text
    assert "singleton_key" in text
    assert "get_solo" in text
    assert "branching_enabled" in text
    assert "branch_name_prefix" in text
    assert "branch_on_conflict" in text


def test_urls_register_home_route():
    text = URLS_PATH.read_text(encoding="utf-8")
    assert 'app_name = "netbox_pbs"' in text
    assert 'name="home"' in text


def test_navigation_exposes_top_level_menu():
    text = NAVIGATION_PATH.read_text(encoding="utf-8")
    assert "PluginMenu(" in text
    assert 'label="Proxmox Backup Server"' in text


def test_initial_migration_creates_plugin_settings_only():
    text = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "initial = True" in text
    assert 'name="PBSPluginSettings"' in text
    # PR C1 must not yet create the domain models — they land in PR C2.
    for forbidden in (
        '"PBSEndpoint"',
        '"PBSNode"',
        '"PBSDatastore"',
        '"PBSBackupGroup"',
        '"PBSSnapshot"',
        '"PBSJobStatus"',
    ):
        assert forbidden not in text, (
            f"PR C1 scaffold migration must not yet declare {forbidden}"
        )
