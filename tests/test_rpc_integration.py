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
