"""Source contracts for Proxmox endpoint bulk enable/disable list actions."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEW_PATH = REPO_ROOT / "netbox_proxbox/views/endpoints/proxmox.py"
TABLE_PATH = REPO_ROOT / "netbox_proxbox/tables/__init__.py"
ENABLE_TEMPLATE = (
    REPO_ROOT
    / "netbox_proxbox/templates/netbox_proxbox/buttons/proxmox_endpoint_bulk_enable.html"
)
DISABLE_TEMPLATE = (
    REPO_ROOT
    / "netbox_proxbox/templates/netbox_proxbox/buttons/proxmox_endpoint_bulk_disable.html"
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def _assignments(class_node: ast.ClassDef) -> dict[str, ast.AST]:
    values: dict[str, ast.AST] = {}
    for node in class_node.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                values[target.id] = node.value
    return values


def _constant(value: ast.AST) -> object:
    assert isinstance(value, ast.Constant)
    return value.value


def _gettext_value(value: ast.AST) -> str:
    assert isinstance(value, ast.Call)
    assert isinstance(value.func, ast.Name)
    assert value.func.id == "_"
    assert len(value.args) == 1
    return str(_constant(value.args[0]))


def _rendered_assign(class_name: str, target_name: str) -> str:
    cls = _find_class(_parse(VIEW_PATH), class_name)
    return ast.unparse(_assignments(cls)[target_name])


def test_table_shows_enabled_column_by_default() -> None:
    """The endpoint inventory list must expose enablement without table config."""
    cls = _find_class(_parse(TABLE_PATH), "ProxmoxEndpointTable")
    meta = next(
        node
        for node in cls.body
        if isinstance(node, ast.ClassDef) and node.name == "Meta"
    )
    defaults = _assignments(meta)["default_columns"]
    rendered = ast.unparse(defaults)

    assert '"enabled"' in rendered or "'enabled'" in rendered


def test_bulk_action_classes_use_change_permission_and_button_templates() -> None:
    module = _parse(VIEW_PATH)

    enable = _assignments(_find_class(module, "ProxmoxEndpointBulkEnableAction"))
    assert _constant(enable["name"]) == "bulk_enable"
    assert _gettext_value(enable["label"]) == "Enable Selected"
    assert _constant(enable["multi"]) is True
    assert ast.unparse(enable["permissions_required"]) == "{'change'}"
    assert (
        _constant(enable["template_name"])
        == "netbox_proxbox/buttons/proxmox_endpoint_bulk_enable.html"
    )

    disable = _assignments(_find_class(module, "ProxmoxEndpointBulkDisableAction"))
    assert _constant(disable["name"]) == "bulk_disable"
    assert _gettext_value(disable["label"]) == "Disable Selected"
    assert _constant(disable["multi"]) is True
    assert ast.unparse(disable["permissions_required"]) == "{'change'}"
    assert (
        _constant(disable["template_name"])
        == "netbox_proxbox/buttons/proxmox_endpoint_bulk_disable.html"
    )


def test_list_view_registers_enable_disable_actions_before_delete() -> None:
    rendered = _rendered_assign("ProxmoxEndpointListView", "actions")

    assert "ProxmoxEndpointBulkEnableAction" in rendered
    assert "ProxmoxEndpointBulkDisableAction" in rendered
    assert rendered.index("ProxmoxEndpointBulkEnableAction") < rendered.index(
        "ProxmoxEndpointBulkDisableAction"
    )
    assert rendered.index("ProxmoxEndpointBulkDisableAction") < rendered.index(
        "BulkDelete"
    )


def test_bulk_enable_disable_views_are_registered_at_selected_routes() -> None:
    module = _parse(VIEW_PATH)
    expected = {
        "ProxmoxEndpointBulkEnableView": ("bulk_enable", "enable-selected"),
        "ProxmoxEndpointBulkDisableView": ("bulk_disable", "disable-selected"),
    }

    for class_name, (action_name, path) in expected.items():
        cls = _find_class(module, class_name)
        decorators = [deco for deco in cls.decorator_list if isinstance(deco, ast.Call)]
        rendered = "\n".join(ast.unparse(deco) for deco in decorators)
        assert repr(action_name) in rendered
        assert f"path={path!r}" in rendered
        assert "detail=False" in rendered


def test_bulk_enabled_view_updates_only_selected_enabled_field() -> None:
    source = VIEW_PATH.read_text(encoding="utf-8")

    assert 'get_permission_for_model(ProxmoxEndpoint, "change")' in source
    assert 'ProxmoxEndpoint.objects.restrict(request.user, "change")' in source
    assert 'request.POST.getlist("pk") or request.POST.getlist("pk[]")' in source
    assert 'request.POST.get("_all")' in source
    assert "ProxmoxEndpointFilterSet(" in source
    assert "request.GET" in source
    assert ".exclude(enabled=self.enabled).update(" in source
    assert "enabled=self.enabled" in source
    assert (
        "requests."
        not in source[
            source.index("class _ProxmoxEndpointBulkEnabledView") : source.index(
                '@register_model_view(ProxmoxEndpoint, "bulk_import"'
            )
        ]
    )


def test_bulk_enable_disable_button_templates_post_to_action_urls() -> None:
    enable = ENABLE_TEMPLATE.read_text(encoding="utf-8")
    disable = DISABLE_TEMPLATE.read_text(encoding="utf-8")

    assert 'name="_bulk_enable"' in enable
    assert "btn btn-green" in enable
    assert "mdi-check-circle-outline" in enable
    assert "{{ label }}" in enable
    assert "{% formaction %}" in enable
    assert "{{ url }}" in enable

    assert 'name="_bulk_disable"' in disable
    assert "btn btn-yellow" in disable
    assert "mdi-close-circle-outline" in disable
    assert "{{ label }}" in disable
    assert "{% formaction %}" in disable
    assert "{{ url }}" in disable
