"""Source contracts for the plugin-owned branch intent surface."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "netbox_proxbox" / "models" / "branch_intent.py"
MIGRATION = ROOT / "netbox_proxbox" / "migrations" / "0090_proxbox_branch_intent.py"
EXTENSION = ROOT / "netbox_proxbox" / "branch_intent_template.py"


def _class(path: Path, name: str) -> ast.ClassDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _field(model: ast.ClassDef, name: str) -> ast.Call:
    assignment = next(
        node
        for node in model.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        )
    )
    assert isinstance(assignment.value, ast.Call)
    return assignment.value


def test_model_uses_soft_reference_and_default_off_gates() -> None:
    model = _class(MODEL, "ProxboxBranchIntent")
    branch_id = _field(model, "branch_id")
    schema_id = _field(model, "branch_schema_id")
    apply = _field(model, "apply_to_proxmox")
    destroy = _field(model, "apply_destroy_confirmed")

    assert isinstance(branch_id.func, ast.Attribute)
    assert branch_id.func.attr == "PositiveBigIntegerField"
    assert isinstance(schema_id.func, ast.Attribute)
    assert schema_id.func.attr == "CharField"
    schema_max_length = next(
        keyword.value for keyword in schema_id.keywords if keyword.arg == "max_length"
    )
    assert isinstance(schema_max_length, ast.Constant)
    assert schema_max_length.value == 8
    for field in (apply, destroy):
        assert isinstance(field.func, ast.Attribute)
        assert field.func.attr == "BooleanField"
        default = next(
            keyword.value for keyword in field.keywords if keyword.arg == "default"
        )
        assert isinstance(default, ast.Constant) and default.value is False

    assert "ForeignKey" not in MODEL.read_text(encoding="utf-8")
    constraint = next(
        node
        for node in ast.walk(model)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "UniqueConstraint"
    )
    fields = next(
        keyword.value for keyword in constraint.keywords if keyword.arg == "fields"
    )
    assert isinstance(fields, ast.Tuple)
    assert [element.value for element in fields.elts] == [
        "branch_id",
        "branch_schema_id",
    ]


def test_additive_migration_uses_idempotent_create_model() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'name="ProxboxBranchIntent"' in source
    assert "operations = [\n        create_model_idempotent(" in source
    assert '("netbox_proxbox", "0089_remove_vm_intent_custom_fields")' in source


def test_model_is_wired_through_ui_and_api_conventions() -> None:
    required = {
        ROOT / "netbox_proxbox" / "models" / "__init__.py": "ProxboxBranchIntent",
        ROOT
        / "netbox_proxbox"
        / "forms"
        / "branch_intent.py": "ProxboxBranchIntentForm",
        ROOT
        / "netbox_proxbox"
        / "tables"
        / "branch_intent.py": "ProxboxBranchIntentTable",
        ROOT / "netbox_proxbox" / "filtersets.py": "ProxboxBranchIntentFilterSet",
        ROOT
        / "netbox_proxbox"
        / "views"
        / "branch_intent.py": "ProxboxBranchIntentListView",
        ROOT / "netbox_proxbox" / "urls.py": '"proxboxbranchintent"',
        ROOT
        / "netbox_proxbox"
        / "api"
        / "serializers"
        / "branch_intent.py": "ProxboxBranchIntentSerializer",
        ROOT / "netbox_proxbox" / "api" / "views.py": "ProxboxBranchIntentViewSet",
        ROOT / "netbox_proxbox" / "api" / "urls.py": '"branch-intents"',
    }
    for path, marker in required.items():
        assert marker in path.read_text(encoding="utf-8"), path


def test_branch_template_extension_registration_is_availability_gated() -> None:
    source = EXTENSION.read_text(encoding="utf-8")
    assert 'models = ("netbox_branching.branch",)' in source
    assert "is_branching_available()" in source
    assert "resolve_branch_intent_flags(branch)" in source
    assert "return []" in source
    template_content = (ROOT / "netbox_proxbox" / "template_content.py").read_text(
        encoding="utf-8"
    )
    assert "branch_intent_template_extensions()" in template_content


@pytest.mark.parametrize(("available", "expected_count"), [(False, 0), (True, 1)])
def test_branch_template_extension_registration_follows_runtime_availability(
    monkeypatch,
    available,
    expected_count,
) -> None:
    django = types.ModuleType("django")
    django.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "django", django)
    django_urls = types.ModuleType("django.urls")
    django_urls.reverse = lambda *_args, **_kwargs: "/"
    monkeypatch.setitem(sys.modules, "django.urls", django_urls)
    django_utils = types.ModuleType("django.utils")
    django_utils.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "django.utils", django_utils)
    safestring = types.ModuleType("django.utils.safestring")
    safestring.mark_safe = lambda value: value
    monkeypatch.setitem(sys.modules, "django.utils.safestring", safestring)

    netbox = types.ModuleType("netbox")
    netbox.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "netbox", netbox)

    class PluginTemplateExtension:
        pass

    plugins = types.ModuleType("netbox.plugins")
    plugins.PluginTemplateExtension = PluginTemplateExtension
    monkeypatch.setitem(sys.modules, "netbox.plugins", plugins)

    utilities = types.ModuleType("utilities")
    utilities.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "utilities", utilities)
    permissions = types.ModuleType("utilities.permissions")
    permissions.get_permission_for_model = lambda *_args: "permission"
    monkeypatch.setitem(sys.modules, "utilities.permissions", permissions)

    models = types.ModuleType("netbox_proxbox.models")
    models.ProxboxBranchIntent = type("ProxboxBranchIntent", (), {})
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    resolver = types.ModuleType("netbox_proxbox.services.branch_intent")
    resolver.resolve_branch_intent_flags = lambda _branch: None
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.branch_intent",
        resolver,
    )

    lifecycle = types.ModuleType("netbox_proxbox.services.branch_lifecycle")
    lifecycle.is_branching_available = lambda: available
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.branch_lifecycle",
        lifecycle,
    )

    name = f"branch_intent_template_test_{available}"
    spec = importlib.util.spec_from_file_location(name, EXTENSION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    extensions = module.branch_intent_template_extensions()

    assert len(extensions) == expected_count
    if available:
        assert extensions == [module.ProxboxBranchIntentTemplateExtension]


def test_branch_card_exposes_both_toggles() -> None:
    template = (
        ROOT
        / "netbox_proxbox"
        / "templates"
        / "netbox_proxbox"
        / "inc"
        / "branch_intent_card.html"
    ).read_text(encoding="utf-8")
    assert "apply_to_proxmox" in template
    assert "apply_destroy_confirmed" in template
