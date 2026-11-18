"""Guard literal CLI routes against the proxbox-api 0.0.32 OpenAPI contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "tests" / "fixtures" / "proxbox_api_0_0_32_routes.json"
FILTERS = ROOT / "tests" / "fixtures" / "proxbox_api_0_0_32_plugin_filters.json"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
BACKEND_PREFIXES = (
    "/admin/",
    "/auth/",
    "/ceph/",
    "/cloud/",
    "/dcim/",
    "/full-update",
    "/intent/",
    "/netbox/",
    "/pbs/",
    "/pdm/",
    "/proxmox/",
    "/ssh/",
    "/sync/",
    "/virtualization/",
)

# These routes are mounted only when their optional backend features are enabled.
CONDITIONAL_ROUTES = {
    ("POST", "/proxmox/viewer/generate"),
}
NON_OPENAPI_ROUTES = {
    # WebSocket relay path; OpenAPI describes HTTP operations only.
    "/proxmox/console/browser-stream",
}


def _literal_cli_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for path in (ROOT / "proxbox_cli").rglob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(module):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            method = node.func.attr.lower()
            if method not in HTTP_METHODS or not node.args:
                continue
            value = node.args[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if value.value.startswith("/"):
                    routes.add((method.upper(), value.value))
    return routes


def _literal_plugin_backend_paths() -> set[str]:
    """Collect exact backend path constants without importing Django or NetBox."""
    paths: set[str] = set()
    for path in (ROOT / "netbox_proxbox").rglob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(module)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(module):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            parent = parents.get(node)
            if isinstance(parent, (ast.Expr, ast.JoinedStr)):
                continue
            value = node.value
            if value.startswith(BACKEND_PREFIXES) and "/api/plugins/" not in value:
                paths.add(value)
    return paths


def test_literal_cli_routes_exist_in_published_backend_contract() -> None:
    operations = json.loads(ROUTES.read_text())
    assert len(operations) == 313
    assert operations == sorted(operations)
    published = {tuple(item) for item in operations}
    missing = _literal_cli_routes() - published - CONDITIONAL_ROUTES
    assert not missing, f"Routes absent from proxbox-api 0.0.32: {sorted(missing)}"


def test_literal_plugin_backend_paths_exist_in_published_backend_contract() -> None:
    published = {item[1] for item in json.loads(ROUTES.read_text())}
    conditional = {path for _method, path in CONDITIONAL_ROUTES}
    missing = (
        _literal_plugin_backend_paths() - published - conditional - NON_OPENAPI_ROUTES
    )
    assert not missing, (
        f"Plugin paths absent from proxbox-api 0.0.32: {sorted(missing)}"
    )


def test_removed_cli_commands_and_routes_are_absent() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "proxbox_cli").rglob("*.py")
    )
    assert "custom-fields-create" not in source
    assert "/extras/extras/custom-fields/create" not in source
    assert '@nodes_app.command("lxc")' not in source
    assert "/proxmox/nodes/{node}/lxc" not in source


def test_backend_query_filters_exist_in_plugin_filtersets() -> None:
    """Pin every filter sent by 0.0.32 for the audited plugin resources."""
    source = (ROOT / "netbox_proxbox" / "filtersets.py").read_text()
    expected = json.loads(FILTERS.read_text())
    for class_name, filter_names in expected.items():
        section = source.split(f"class {class_name}", 1)[1].split(
            "@register_filterset", 1
        )[0]
        for filter_name in filter_names:
            assert f'"{filter_name}"' in section or f"{filter_name} =" in section
