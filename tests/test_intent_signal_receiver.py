"""Sub-PR E (#382): AST contract for the post_merge signal receiver."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RECEIVER_PATH = REPO_ROOT / "netbox_proxbox" / "signal_receivers.py"
CONFIG_PATH = REPO_ROOT / "netbox_proxbox" / "__init__.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _function(module: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} function not found")


def test_signal_receiver_module_exists_and_defines_handler():
    assert RECEIVER_PATH.exists(), "netbox_proxbox/signal_receivers.py must exist"
    module = _parse(RECEIVER_PATH)
    assert _function(module, "handle_branch_merged")


def test_handle_branch_merged_has_receiver_decorator():
    handler = _function(_parse(RECEIVER_PATH), "handle_branch_merged")
    assert any(
        isinstance(deco, ast.Call)
        and isinstance(deco.func, ast.Name)
        and deco.func.id == "receiver"
        for deco in handler.decorator_list
    ), "handle_branch_merged must be decorated with @receiver(...)"


def test_handle_branch_merged_body_has_top_level_try_except():
    handler = _function(_parse(RECEIVER_PATH), "handle_branch_merged")
    top_level_try = next(
        (stmt for stmt in handler.body if isinstance(stmt, ast.Try)),
        None,
    )
    assert top_level_try is not None, (
        "handle_branch_merged body must be wrapped in a top-level try/except"
    )
    assert any(
        isinstance(exc.type, ast.Name) and exc.type.id == "Exception"
        for exc in top_level_try.handlers
    ), "receiver must catch Exception and return rather than re-raise"


def test_netbox_branching_post_merge_import_is_guarded():
    module = _parse(RECEIVER_PATH)
    for node in ast.iter_child_nodes(module):
        if not isinstance(node, ast.Try):
            continue
        imports_post_merge = any(
            isinstance(stmt, ast.ImportFrom)
            and stmt.module == "netbox_branching.signals"
            and any(alias.name == "post_merge" for alias in stmt.names)
            for stmt in node.body
        )
        catches_import_error = any(
            isinstance(handler.type, ast.Name) and handler.type.id == "ImportError"
            for handler in node.handlers
        )
        if imports_post_merge and catches_import_error:
            return
    raise AssertionError(
        "from netbox_branching.signals import post_merge must be inside "
        "try/except ImportError"
    )


def test_plugin_ready_imports_signal_receivers():
    module = _parse(CONFIG_PATH)
    for cls in ast.walk(module):
        if not isinstance(cls, ast.ClassDef) or cls.name != "ProxboxConfig":
            continue
        ready = _function(ast.Module(body=cls.body, type_ignores=[]), "ready")
        imports_receiver = any(
            isinstance(stmt, ast.ImportFrom)
            and stmt.level == 1
            and stmt.module is None
            and any(alias.name == "signal_receivers" for alias in stmt.names)
            for stmt in ready.body
        )
        assert imports_receiver, "ProxboxConfig.ready() must import signal_receivers"
        return
    raise AssertionError("ProxboxConfig class not found")
