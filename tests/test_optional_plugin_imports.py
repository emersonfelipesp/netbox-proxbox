"""Source contracts for companion plugins that may be installed but disabled."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _guarded_import(path: Path, *, app_name: str, module_name: str) -> bool:
    module = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(module):
        if not isinstance(node, ast.If):
            continue
        if not (
            isinstance(node.test, ast.Call)
            and isinstance(node.test.func, ast.Attribute)
            and node.test.func.attr == "is_installed"
            and node.test.args
            and isinstance(node.test.args[0], ast.Constant)
            and node.test.args[0].value == app_name
        ):
            continue
        return any(
            isinstance(child, (ast.Import, ast.ImportFrom))
            and (
                any(alias.name == module_name for alias in child.names)
                if isinstance(child, ast.Import)
                else child.module == module_name
            )
            for child in ast.walk(node)
        )
    return False


def _app_guard(path: Path, *, app_name: str) -> ast.If:
    module = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(module)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Call)
        and isinstance(node.test.func, ast.Attribute)
        and node.test.func.attr == "is_installed"
        and node.test.args
        and isinstance(node.test.args[0], ast.Constant)
        and node.test.args[0].value == app_name
    )


def test_pdm_url_registration_requires_enabled_django_app() -> None:
    assert _guarded_import(
        ROOT / "netbox_proxbox" / "urls.py",
        app_name="netbox_pdm",
        module_name="netbox_pdm.views",
    )


def test_enabled_pdm_import_failure_is_not_suppressed() -> None:
    guard = _app_guard(ROOT / "netbox_proxbox" / "urls.py", app_name="netbox_pdm")

    assert not any(isinstance(node, ast.Try) for node in guard.body)
