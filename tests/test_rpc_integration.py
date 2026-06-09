"""Tests for the optional netbox-rpc integration (soft dependency).

Source-contract assertions plus an isolated functional check of the
ImportError fallback. ``netbox_proxbox/integrations/rpc.py`` only imports the
stdlib at module level, so it loads standalone without NetBox/Django.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_rpc_integration_is_a_soft_dependency() -> None:
    src = _read("netbox_proxbox/integrations/rpc.py")
    # netbox_rpc must only be imported lazily inside a try/except, never at module top.
    top = src.split("def ", 1)[0]
    assert "import netbox_rpc" not in top, (
        "netbox_rpc must not be imported at module top-level"
    )
    assert "from netbox_rpc" not in top, (
        "netbox_rpc must not be imported at module top-level"
    )
    assert "except ImportError" in src
    assert "from netbox_rpc" in src  # lazy import lives inside a function
    assert 'INSTALL_SSH_KEY_PROCEDURE = "os.linux.ubuntu.24.install_ssh_key"' in src


def test_pyproject_does_not_hard_depend_on_netbox_rpc() -> None:
    pp = _read("pyproject.toml")
    deps = pp.split("[project.optional-dependencies]", 1)[0]
    assert "netbox-rpc" not in deps and "netbox_rpc" not in deps


def test_readme_lists_netbox_rpc_optional_plugin() -> None:
    readme = _read("README.md")
    assert "netbox-rpc" in readme
    assert "`netbox_rpc`" in readme


def _load_rpc_module():
    path = REPO_ROOT / "netbox_proxbox" / "integrations" / "rpc.py"
    spec = importlib.util.spec_from_file_location("nbp_rpc_iso", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_install_ssh_key_via_rpc_returns_none_without_netbox_rpc() -> None:
    mod = _load_rpc_module()
    # netbox_rpc is not installed in the test env → ImportError path → None, no raise.
    result = mod.install_ssh_key_via_rpc(
        target=object(), public_key="ssh-ed25519 AAAA", backend=object()
    )
    assert result is None
    assert mod.INSTALL_SSH_KEY_PROCEDURE == "os.linux.ubuntu.24.install_ssh_key"
