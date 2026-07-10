"""Tests for the optional netbox-rpc integration (soft dependency).

Source-contract assertions plus an isolated functional check of the
ImportError fallback. ``netbox_proxbox/integrations/rpc.py`` only imports the
stdlib at module level, so it loads standalone without NetBox/Django.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

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


def test_install_ssh_key_via_rpc_enqueues_with_execution_pk(monkeypatch) -> None:
    """The netbox-rpc job contract is keyword execution_pk, never instance."""
    mod = _load_rpc_module()
    calls = []
    procedure = object()
    execution = SimpleNamespace(pk=123)
    backend = SimpleNamespace(pk=456)
    requested_by = SimpleNamespace(username="operator")
    target = SimpleNamespace(name="pve-01")

    class _ProcedureQuery:
        def first(self):
            return procedure

    class _ProcedureManager:
        def filter(self, **kwargs):
            assert kwargs == {
                "name": mod.INSTALL_SSH_KEY_PROCEDURE,
                "enabled": True,
            }
            return _ProcedureQuery()

    class _ExecutionManager:
        def create(self, **kwargs):
            assert kwargs["procedure"] is procedure
            assert kwargs["assigned_object"] is target
            assert kwargs["backend"] is backend
            assert kwargs["requested_by"] is requested_by
            assert kwargs["params"] == {
                "public_key": "ssh-ed25519 AAAA",
                "username": "root",
            }
            assert kwargs["status"] == "queued"
            return execution

    class _RPCProcedure:
        objects = _ProcedureManager()

    class _RPCExecution:
        objects = _ExecutionManager()

    class _RPCExecutionJob:
        @classmethod
        def enqueue(cls, **kwargs):
            calls.append(kwargs)

    package = types.ModuleType("netbox_rpc")
    package.__path__ = []
    jobs = types.ModuleType("netbox_rpc.jobs")
    jobs.RPCExecutionJob = _RPCExecutionJob
    models = types.ModuleType("netbox_rpc.models")
    models.RPCExecution = _RPCExecution
    models.RPCProcedure = _RPCProcedure

    monkeypatch.setitem(sys.modules, "netbox_rpc", package)
    monkeypatch.setitem(sys.modules, "netbox_rpc.jobs", jobs)
    monkeypatch.setitem(sys.modules, "netbox_rpc.models", models)

    result = mod.install_ssh_key_via_rpc(
        target=target,
        public_key="ssh-ed25519 AAAA",
        backend=backend,
        requested_by=requested_by,
        username="root",
    )

    assert result is execution
    assert calls == [
        {
            "execution_pk": 123,
            "instance": None,
            "user": requested_by,
            "backend_pk": 456,
        }
    ]


def test_rpc_dashboard_context_empty_when_not_installed() -> None:
    mod = _load_rpc_module()
    # is_netbox_rpc_installed() is False in the test env (django settings absent)
    # → the companion card is omitted entirely.
    assert mod.rpc_dashboard_context() == {}


def test_rpc_dashboard_context_installed_without_settings_model(monkeypatch) -> None:
    """Old netbox-rpc (no RpcPluginSettings): card shows, settings unsupported."""
    mod = _load_rpc_module()
    monkeypatch.setattr(mod, "is_netbox_rpc_installed", lambda: True)
    # netbox_rpc present but netbox_rpc.models import fails → ImportError branch.
    package = types.ModuleType("netbox_rpc")  # no __path__ → submodule import fails
    monkeypatch.setitem(sys.modules, "netbox_rpc", package)
    monkeypatch.delitem(sys.modules, "netbox_rpc.models", raising=False)

    ctx = mod.rpc_dashboard_context()
    assert ctx == {
        "rpc_integration": {
            "installed": True,
            "enabled": False,
            "backend_name": "",
            "backend_url": "",
            "home_url": "/plugins/rpc/",
            "settings_supported": False,
        }
    }


def _install_fake_settings(monkeypatch, *, enabled, backend):
    package = types.ModuleType("netbox_rpc")
    package.__path__ = []
    models = types.ModuleType("netbox_rpc.models")

    class _Settings:
        @classmethod
        def get_solo(cls):
            obj = cls()
            obj.enabled = enabled
            obj.backend = backend
            return obj

    models.RpcPluginSettings = _Settings
    monkeypatch.setitem(sys.modules, "netbox_rpc", package)
    monkeypatch.setitem(sys.modules, "netbox_rpc.models", models)


def test_rpc_dashboard_context_reads_enabled_settings(monkeypatch) -> None:
    mod = _load_rpc_module()
    monkeypatch.setattr(mod, "is_netbox_rpc_installed", lambda: True)

    class _Backend:
        backend_url = "https://backend.rpc.nmulti.cloud"

        def __str__(self) -> str:
            return "rpc-prod"

    _install_fake_settings(monkeypatch, enabled=True, backend=_Backend())

    ctx = mod.rpc_dashboard_context()["rpc_integration"]
    assert ctx["installed"] is True
    assert ctx["enabled"] is True
    assert ctx["settings_supported"] is True
    assert ctx["backend_name"] == "rpc-prod"
    assert ctx["backend_url"] == "https://backend.rpc.nmulti.cloud"
    assert ctx["home_url"] == "/plugins/rpc/"


def test_rpc_dashboard_context_disabled_without_backend(monkeypatch) -> None:
    mod = _load_rpc_module()
    monkeypatch.setattr(mod, "is_netbox_rpc_installed", lambda: True)
    _install_fake_settings(monkeypatch, enabled=False, backend=None)

    ctx = mod.rpc_dashboard_context()["rpc_integration"]
    assert ctx["installed"] is True
    assert ctx["enabled"] is False
    assert ctx["settings_supported"] is True
    assert ctx["backend_name"] == ""
    assert ctx["backend_url"] == ""


def test_rpc_dashboard_context_survives_bad_settings_row(monkeypatch) -> None:
    """A raising get_solo() must not break the dashboard."""
    mod = _load_rpc_module()
    monkeypatch.setattr(mod, "is_netbox_rpc_installed", lambda: True)

    package = types.ModuleType("netbox_rpc")
    package.__path__ = []
    models = types.ModuleType("netbox_rpc.models")

    class _Settings:
        @classmethod
        def get_solo(cls):
            raise RuntimeError("db down")

    models.RpcPluginSettings = _Settings
    monkeypatch.setitem(sys.modules, "netbox_rpc", package)
    monkeypatch.setitem(sys.modules, "netbox_rpc.models", models)

    ctx = mod.rpc_dashboard_context()["rpc_integration"]
    assert ctx["installed"] is True
    assert ctx["settings_supported"] is True
    assert ctx["enabled"] is False  # safe default when the row can't be read


def test_rpc_dashboard_context_in_all_exports() -> None:
    src = _read("netbox_proxbox/integrations/rpc.py")
    assert '"rpc_dashboard_context"' in src


def test_home_context_wires_optional_rpc_card() -> None:
    src = _read("netbox_proxbox/views/home_context.py")
    assert "_build_rpc_integration_context" in src
    assert "rpc_dashboard_context" in src


def test_home_template_renders_rpc_card() -> None:
    html = _read("netbox_proxbox/templates/netbox_proxbox/home.html")
    assert "{% if rpc_integration %}" in html
    assert "netbox-rpc" in html
    assert "rpc_integration.home_url" in html
