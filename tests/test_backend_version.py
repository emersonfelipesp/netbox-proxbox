"""Regression coverage for proxbox-api version advisories."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _backend_version_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox"
        / "services"
        / "backend_version.py"
    )
    spec = importlib.util.spec_from_file_location(
        "backend_version_under_test", module_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_backend_version_accepts_release_prefixes_and_post_releases():
    module = _backend_version_module()

    assert module.parse_backend_version("v0.0.14") == (0, 0, 14, 0)
    assert module.parse_backend_version("0.0.14.post1") == (0, 0, 14, 1)
    assert module.parse_backend_version("0.0.15rc1") == (0, 0, 15, 0)
    assert module.parse_backend_version("not-a-version") is None


def test_backend_version_advisory_blocks_pre_vm_config_fix_backend():
    module = _backend_version_module()
    advisories = module.backend_version_advisories("0.0.12")

    assert [advisory.severity for advisory in advisories] == ["error"]
    assert advisories[0].code == "vm_ip_sync_backend_too_old"
    assert "proxmox_vm_id" in advisories[0].message


def test_backend_version_advisory_warns_for_agent_kv_flag_release_window():
    module = _backend_version_module()
    advisories = module.backend_version_advisories("0.0.14")

    assert [advisory.severity for advisory in advisories] == ["warning"]
    assert advisories[0].code == "qemu_agent_kv_flag_fix_pending"
    assert "PR #156" in advisories[0].message


def test_backend_version_advisory_clears_for_post_fix_release_line():
    module = _backend_version_module()

    assert module.backend_version_advisories("0.0.14.post1") == []
    assert module.backend_version_advisories("0.0.15") == []
