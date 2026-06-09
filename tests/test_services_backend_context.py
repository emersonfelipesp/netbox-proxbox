"""Source-contract tests for ``services.backend_context``.

This module is the single source of truth for ``get_fastapi_request_context()``
and ``get_fastapi_endpoint_with_token()``. Both helpers are imported from many
view modules to resolve the active FastAPIEndpoint singleton, so the public
shape of the module must stay stable. We assert it without bootstrapping
NetBox/Django.

What the contract pins down:

* ``get_fastapi_request_context`` accepts an optional ``endpoint_id`` (defaults
  to ``None``) and returns ``BackendRequestContext | None``.
* ``get_fastapi_endpoint_with_token`` falls back from "explicit enabled
  endpoint_id" → "single enabled endpoint" → "first enabled endpoint" — the
  three branches that view code relies on.
* Module imports the ``BackendRequestContext`` schema, and the auth-retry path
  imports ``ensure_backend_key_registered`` lazily to avoid NetBox startup
  import cycles.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_CONTEXT_PATH = REPO_ROOT / "netbox_proxbox" / "services" / "backend_context.py"


def _module() -> ast.Module:
    return ast.parse(BACKEND_CONTEXT_PATH.read_text(encoding="utf-8"))


def _functions_by_name(module: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in module.body if isinstance(n, ast.FunctionDef)}


def test_module_imports_required_collaborators():
    source = BACKEND_CONTEXT_PATH.read_text(encoding="utf-8")
    assert "from netbox_proxbox.models import FastAPIEndpoint" in source
    assert "BackendRequestContext" in source
    assert "ensure_backend_key_registered" in source


def test_backend_auth_import_stays_lazy():
    module = _module()
    for node in module.body:
        if isinstance(node, ast.ImportFrom):
            assert node.module != "netbox_proxbox.services.backend_auth", (
                "backend_auth imports view helpers, so importing it at module load "
                "time can create NetBox startup cycles"
            )

    helper = _functions_by_name(module)["_handle_auth_registration_and_retry"]
    local_imports = [
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.ImportFrom)
        and node.module == "netbox_proxbox.services.backend_auth"
    ]
    assert local_imports, (
        "_handle_auth_registration_and_retry must import backend_auth lazily"
    )


def test_get_fastapi_request_context_signature_is_stable():
    funcs = _functions_by_name(_module())
    assert "get_fastapi_request_context" in funcs, (
        "get_fastapi_request_context is imported by view code; do not rename"
    )
    func = funcs["get_fastapi_request_context"]
    arg_names = [a.arg for a in func.args.args]
    assert arg_names == ["endpoint_id"]
    assert len(func.args.defaults) == 1, (
        "endpoint_id must remain optional so call sites without an id keep working"
    )


def test_get_fastapi_endpoint_with_token_returns_tuple():
    funcs = _functions_by_name(_module())
    assert "get_fastapi_endpoint_with_token" in funcs
    func = funcs["get_fastapi_endpoint_with_token"]

    return_paths: list[ast.AST] = [
        n for n in ast.walk(func) if isinstance(n, ast.Return)
    ]
    assert return_paths, "get_fastapi_endpoint_with_token must return a value"
    for ret in return_paths:
        assert isinstance(ret.value, ast.Tuple), (
            "all return paths must yield a (endpoint, context) tuple — a single value "
            "would silently break unpacking in callers"
        )
        assert len(ret.value.elts) == 2


def test_endpoint_lookup_handles_three_branches():
    """Endpoint resolution must cover: explicit id, single row, multi-row first()."""
    source = BACKEND_CONTEXT_PATH.read_text(encoding="utf-8")
    # explicit id branch (disabled endpoints must not be resolved):
    assert "filter(" in source
    assert "pk=endpoint_id" in source
    assert "enabled=True" in source
    # single-row branch (enabled filter + first):
    assert "filter(enabled=True).first()" in source
    # multi-row branch:
    assert 'order_by("pk")' in source
    # count gate before the multi-row pick (enabled filter + count):
    assert "filter(enabled=True).count()" in source


def test_auth_retry_helper_returns_two_tuple_with_retry_flag():
    funcs = _functions_by_name(_module())
    helper = funcs.get("_handle_auth_registration_and_retry")
    assert helper is not None, (
        "_handle_auth_registration_and_retry is the auth-retry hook used by "
        "backend_proxy; do not delete or rename"
    )
    for ret in ast.walk(helper):
        if isinstance(ret, ast.Return):
            assert isinstance(ret.value, ast.Tuple) and len(ret.value.elts) == 2, (
                "_handle_auth_registration_and_retry must return (headers, retry_flag)"
            )
