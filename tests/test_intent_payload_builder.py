"""Sub-PR F (#383): AST contract for intent payload builders."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "payload.py"


def _parse() -> ast.Module:
    return ast.parse(PAYLOAD_PATH.read_text(encoding="utf-8"))


def _function(module: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} function not found")


def test_payload_module_exposes_public_builders():
    module = _parse()
    assert _function(module, "build_vm_payload")
    assert _function(module, "build_lxc_payload")


def test_payload_builders_accept_one_positional_argument():
    module = _parse()
    for name in ("build_vm_payload", "build_lxc_payload"):
        function = _function(module, name)
        positional = function.args.posonlyargs + function.args.args
        assert len(positional) == 1
        assert not function.args.kwonlyargs
        assert function.args.vararg is None
        assert function.args.kwarg is None


def test_payload_builder_is_pure_no_requests_import():
    text = PAYLOAD_PATH.read_text(encoding="utf-8")
    assert "import requests" not in text


def test_payload_builders_contain_backend_contract_keys():
    text = PAYLOAD_PATH.read_text(encoding="utf-8")
    for key in (
        "vmid",
        "name",
        "node",
        "cores",
        "memory",
        "disk_gb",
        "storage",
        "iso",
        "template_vmid",
        "tags",
        "description",
        "swap",
        "rootfs",
        "ostemplate",
    ):
        assert f'"{key}"' in text
