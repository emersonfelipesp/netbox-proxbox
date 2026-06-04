"""Type-contract tests for ``services.sync_firewall`` annotations."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNC_FIREWALL_PATH = REPO_ROOT / "netbox_proxbox" / "services" / "sync_firewall.py"

EXPECTED_DICT_PARAMETERS = {
    "_upsert_security_group": {"raw": dict[str, object]},
    "_upsert_rule": {"raw": dict[str, object]},
    "_upsert_ipset": {"raw": dict[str, object]},
    "_upsert_alias": {"raw": dict[str, object]},
    "_upsert_options": {"raw": dict[str, object] | None},
    "_sync_one_endpoint": {"summary_entry": dict[str, object]},
    "sync_firewall": {"auth_headers": dict[str, str] | None},
    "sync_node_firewall": {"auth_headers": dict[str, str]},
    "sync_vm_firewall": {"auth_headers": dict[str, str]},
}


def _stub_model(name: str) -> type:
    return type(name, (), {})


def _load_sync_firewall(monkeypatch):
    """Import sync_firewall.py with the minimal NetBox/Django stubs it needs."""
    package = types.ModuleType("netbox_proxbox")
    package.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", package)

    services_package = types.ModuleType("netbox_proxbox.services")
    services_package.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_package)

    choices = types.ModuleType("netbox_proxbox.choices")
    choices.FirewallSyncStatusChoices = SimpleNamespace(ACTIVE="active", STALE="stale")
    choices.FirewallZoneChoices = SimpleNamespace(
        DATACENTER="datacenter",
        NODE="node",
        VM_QEMU="vm_qemu",
        VM_LXC="vm_lxc",
        SECURITY_GROUP="security_group",
    )
    choices.FirewallScopeChoices = SimpleNamespace(DATACENTER="datacenter")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices)

    models = types.ModuleType("netbox_proxbox.models")
    for name in (
        "ProxmoxEndpoint",
        "ProxmoxFirewallAlias",
        "ProxmoxFirewallIPSet",
        "ProxmoxFirewallIPSetEntry",
        "ProxmoxFirewallOptions",
        "ProxmoxFirewallRule",
        "ProxmoxFirewallSecurityGroup",
    ):
        setattr(models, name, _stub_model(name))
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    backend_proxy = types.ModuleType("netbox_proxbox.services.backend_proxy")
    backend_proxy.get_fastapi_request_context = lambda: None
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_proxy", backend_proxy
    )

    requests = types.ModuleType("requests")
    requests.RequestException = Exception
    monkeypatch.setitem(sys.modules, "requests", requests)

    django = types.ModuleType("django")
    db = types.ModuleType("django.db")
    db.transaction = SimpleNamespace(atomic=lambda: None)
    django.db = db
    monkeypatch.setitem(sys.modules, "django", django)
    monkeypatch.setitem(sys.modules, "django.db", db)

    module_name = "netbox_proxbox.services.sync_firewall"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    spec = importlib.util.spec_from_file_location(module_name, SYNC_FIREWALL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def test_sync_firewall_dict_parameters_are_parameterized(monkeypatch):
    module = _load_sync_firewall(monkeypatch)

    for function_name, expected_parameters in EXPECTED_DICT_PARAMETERS.items():
        function = getattr(module, function_name)
        signature = inspect.signature(function)
        hints = get_type_hints(function)

        for parameter_name, expected_type in expected_parameters.items():
            assert parameter_name in signature.parameters
            assert hints[parameter_name] == expected_type


def _has_bare_dict_annotation(annotation: ast.AST) -> bool:
    if isinstance(annotation, ast.Name):
        return annotation.id == "dict"
    if isinstance(annotation, ast.Subscript):
        return _has_bare_dict_annotation(annotation.slice)
    return any(
        _has_bare_dict_annotation(child) for child in ast.iter_child_nodes(annotation)
    )


def _annotation_nodes(module: ast.Module) -> list[ast.AST]:
    annotations: list[ast.AST] = []
    for node in ast.walk(module):
        if isinstance(node, ast.arg) and node.annotation is not None:
            annotations.append(node.annotation)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                annotations.append(node.returns)
    return annotations


def test_sync_firewall_module_has_no_bare_dict_annotations():
    module = ast.parse(SYNC_FIREWALL_PATH.read_text(encoding="utf-8"))
    offenders = [
        f"line {annotation.lineno}: {ast.unparse(annotation)}"
        for annotation in _annotation_nodes(module)
        if _has_bare_dict_annotation(annotation)
    ]

    assert not offenders, "Bare dict annotations found:\n" + "\n".join(offenders)
