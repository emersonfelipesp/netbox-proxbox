"""Source-contract test for the sibling ``netbox-ceph`` wheel metadata.

The Ceph plugin ships as its own wheel from ``netbox_ceph/`` inside this
repository (see issue #429). This module pins the wheel-level metadata
that the docs, install guide, and release notes all reference, without
running ``pip wheel`` or any other build step.
"""

from __future__ import annotations

import pathlib
import tomllib


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CEPH_PYPROJECT = REPO_ROOT / "netbox_ceph" / "pyproject.toml"
CEPH_README = REPO_ROOT / "netbox_ceph" / "README.md"
CEPH_MANIFEST = REPO_ROOT / "netbox_ceph" / "MANIFEST.in"
CEPH_INIT = REPO_ROOT / "netbox_ceph" / "netbox_ceph" / "__init__.py"


def _pyproject() -> dict:
    return tomllib.loads(CEPH_PYPROJECT.read_text(encoding="utf-8"))


def test_ceph_pyproject_exists() -> None:
    assert CEPH_PYPROJECT.is_file()


def test_ceph_package_name_and_version_are_pinned() -> None:
    project = _pyproject()["project"]
    assert project["name"] == "netbox-ceph"
    # v1 ships as 0.0.1 alongside netbox-proxbox 0.0.17.
    assert project["version"] == "0.0.1"


def test_ceph_requires_netbox_proxbox_floor() -> None:
    project = _pyproject()["project"]
    deps = project["dependencies"]
    assert any(d.startswith("netbox-proxbox") for d in deps), deps
    # Must declare a >= floor so installs pull in a compatible netbox-proxbox.
    netbox_proxbox_dep = next(d for d in deps if d.startswith("netbox-proxbox"))
    assert ">=" in netbox_proxbox_dep, netbox_proxbox_dep


def test_ceph_requires_modern_python() -> None:
    project = _pyproject()["project"]
    assert project["requires-python"] == ">=3.11"


def test_ceph_manifest_includes_templates_and_migrations() -> None:
    manifest = CEPH_MANIFEST.read_text(encoding="utf-8")
    assert "recursive-include netbox_ceph/templates *.html" in manifest
    assert "recursive-include netbox_ceph/migrations *.py" in manifest


def test_ceph_readme_documents_v1_readonly_scope() -> None:
    readme = CEPH_README.read_text(encoding="utf-8").lower()
    assert "read-only" in readme
    assert "proxmox" in readme
    assert "v1" in readme


def test_ceph_init_exposes_pluginconfig() -> None:
    source = CEPH_INIT.read_text(encoding="utf-8")
    # Must declare the PluginConfig the test_ceph_version module pins.
    assert "class CephConfig" in source or "CephConfig" in source
    assert 'required_plugins' in source


def test_release_notes_for_0_0_17_mention_ceph_plugin() -> None:
    release_notes = (
        REPO_ROOT / "docs" / "release-notes" / "version-0.0.17.md"
    ).read_text(encoding="utf-8").lower()
    assert "netbox-ceph" in release_notes
    assert "read-only" in release_notes
    # Cross-issue traceability for #424 sub-issues.
    for ref in ("#424", "#428", "#430", "#429"):
        assert ref in release_notes, ref


def test_docs_feature_and_install_pages_exist() -> None:
    assert (REPO_ROOT / "docs" / "features" / "ceph.md").is_file()
    assert (REPO_ROOT / "docs" / "installation" / "ceph-plugin.md").is_file()


def test_mkdocs_nav_links_ceph_pages() -> None:
    mkdocs = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "features/ceph.md" in mkdocs
    assert "installation/ceph-plugin.md" in mkdocs
    assert "release-notes/version-0.0.17.md" in mkdocs
