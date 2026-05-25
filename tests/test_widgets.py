"""Tests for the dashboard widgets module.

These tests verify widget structure and registration at the source level,
without importing the full Django/NetBox stack.
"""

from __future__ import annotations

import ast
from pathlib import Path

WIDGETS_PATH = Path(__file__).resolve().parents[1] / "netbox_proxbox" / "widgets.py"


def _parse_widgets_module() -> ast.Module:
    return ast.parse(WIDGETS_PATH.read_text(), filename=str(WIDGETS_PATH))


def _class_names(tree: ast.Module) -> list[str]:
    return [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def _decorated_classes(tree: ast.Module) -> dict[str, list[str]]:
    """Return {class_name: [decorator_names]} for all classes."""
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            decorators = []
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name):
                    decorators.append(dec.id)
                elif isinstance(dec, ast.Attribute):
                    decorators.append(dec.attr)
            result[node.name] = decorators
    return result


def _function_names_in_class(tree: ast.Module, class_name: str) -> list[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [n.name for n in ast.walk(node) if isinstance(n, ast.FunctionDef)]
    return []


class TestWidgetModuleStructure:
    def test_widgets_file_exists(self):
        assert WIDGETS_PATH.exists(), f"Expected widgets.py at {WIDGETS_PATH}"

    def test_three_widget_classes_defined(self):
        tree = _parse_widgets_module()
        names = _class_names(tree)
        expected = {
            "ProxboxSyncStatusWidget",
            "ProxboxObjectCountsWidget",
            "ProxboxEndpointStatusWidget",
        }
        assert expected.issubset(set(names)), (
            f"Missing widget classes: {expected - set(names)}"
        )

    def test_all_widgets_decorated_with_register_widget(self):
        tree = _parse_widgets_module()
        decorated = _decorated_classes(tree)
        for widget_name in (
            "ProxboxSyncStatusWidget",
            "ProxboxObjectCountsWidget",
            "ProxboxEndpointStatusWidget",
        ):
            assert widget_name in decorated, f"{widget_name} not found"
            assert "register_widget" in decorated[widget_name], (
                f"{widget_name} missing @register_widget decorator"
            )

    def test_all_widgets_have_render_method(self):
        tree = _parse_widgets_module()
        for widget_name in (
            "ProxboxSyncStatusWidget",
            "ProxboxObjectCountsWidget",
            "ProxboxEndpointStatusWidget",
        ):
            methods = _function_names_in_class(tree, widget_name)
            assert "render" in methods, f"{widget_name} missing render() method"

    def test_widgets_import_from_extras_dashboard(self):
        source = WIDGETS_PATH.read_text()
        assert "from extras.dashboard.utils import register_widget" in source
        assert "from extras.dashboard.widgets import DashboardWidget" in source

    def test_no_http_calls_in_render(self):
        """Widgets must not make synchronous HTTP calls in render()."""
        source = WIDGETS_PATH.read_text()
        forbidden = ["requests.get", "requests.post", "httpx.", "urllib.request"]
        for pattern in forbidden:
            assert pattern not in source, (
                f"widgets.py contains '{pattern}' — render() must be DB-only"
            )


class TestWidgetTemplates:
    TEMPLATE_DIR = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox"
        / "templates"
        / "netbox_proxbox"
        / "dashboard_widgets"
    )

    def test_template_directory_exists(self):
        assert self.TEMPLATE_DIR.is_dir(), (
            f"Expected template dir at {self.TEMPLATE_DIR}"
        )

    def test_sync_status_template_exists(self):
        assert (self.TEMPLATE_DIR / "sync_status.html").exists()

    def test_object_counts_template_exists(self):
        assert (self.TEMPLATE_DIR / "object_counts.html").exists()

    def test_endpoint_status_template_exists(self):
        assert (self.TEMPLATE_DIR / "endpoint_status.html").exists()


class TestPluginConfigImportsWidgets:
    def test_ready_imports_widgets(self):
        init_path = (
            Path(__file__).resolve().parents[1] / "netbox_proxbox" / "__init__.py"
        )
        source = init_path.read_text()
        assert "from . import widgets" in source, (
            "PluginConfig.ready() must import widgets for registration"
        )
