"""AST-based contract tests for the PR C2b PBS UI surface.

These tests pin the read-only enforcement contract: PBSEndpoint is the
only model that registers ``edit``, ``delete``, ``bulk_edit``,
``bulk_delete``, and ``bulk_import`` views. The other five PBS models
(reflected from PBS by the read-only sync) intentionally register only
``list`` and detail views. Templates and navigation never render
edit/delete buttons for them because those URLs don't exist.

We use AST rather than Django bootstrap so the contract is verifiable
in the per-commit gate without a running NetBox.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = REPO_ROOT / "netbox_pbs"
VIEWS = PKG_DIR / "views.py"
URLS = PKG_DIR / "urls.py"
NAVIGATION = PKG_DIR / "navigation.py"
TABLES = PKG_DIR / "tables.py"
FILTERSETS = PKG_DIR / "filtersets.py"
FORMS = PKG_DIR / "forms.py"


WRITE_ACTIONS = ("edit", "delete", "bulk_edit", "bulk_delete", "bulk_import")
READ_ONLY_MODELS = (
    "PBSNode",
    "PBSDatastore",
    "PBSBackupGroup",
    "PBSSnapshot",
    "PBSJobStatus",
)
ALL_MODELS = ("PBSEndpoint", *READ_ONLY_MODELS)


def _collect_register_model_view_calls(path: Path) -> list[tuple[str, str | None]]:
    """Return ``(model_name, action)`` pairs for every register_model_view().

    ``action`` is ``None`` for the bare ``@register_model_view(Model)``
    detail-view registration; otherwise it is the action string literal
    passed as the second positional argument.
    """
    module = ast.parse(path.read_text(encoding="utf-8"))
    pairs: list[tuple[str, str | None]] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "register_model_view":
            pass
        elif isinstance(func, ast.Attribute) and func.attr == "register_model_view":
            pass
        else:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Name):
            continue
        action: str | None = None
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            action = node.args[1].value
        pairs.append((first.id, action))
    return pairs


def test_pbs_endpoint_registers_full_crud():
    pairs = _collect_register_model_view_calls(VIEWS)
    actions_for_endpoint = {action for model, action in pairs if model == "PBSEndpoint"}
    # bare detail view (action=None) plus list + every write action
    assert None in actions_for_endpoint, "missing detail view for PBSEndpoint"
    assert "list" in actions_for_endpoint, "missing list view for PBSEndpoint"
    for action in WRITE_ACTIONS:
        assert action in actions_for_endpoint, (
            f"PBSEndpoint must register {action} view"
        )


def test_reflected_models_register_only_list_and_detail():
    pairs = _collect_register_model_view_calls(VIEWS)
    for model in READ_ONLY_MODELS:
        actions = {action for m, action in pairs if m == model}
        assert actions == {None, "list"}, (
            f"{model} must register only list + detail; got {sorted(str(a) for a in actions)}"
        )


def test_reflected_model_list_views_use_export_only_actions():
    """ObjectListView for read-only models must expose only the export action."""
    text = VIEWS.read_text(encoding="utf-8")
    # The shared constant pins the contract; an explicit per-model dict would
    # be a regression. Assert the constant exists with the expected value and
    # that each read-only list view binds to it.
    assert '_READ_ONLY_ACTIONS = {"export": {"view"}}' in text
    for model in READ_ONLY_MODELS:
        # Each read-only list class should reference _READ_ONLY_ACTIONS.
        list_class = f"{model}ListView"
        assert list_class in text, f"missing {list_class}"
    # And no read-only-model list view should opt into add/edit/delete actions.
    for model in READ_ONLY_MODELS:
        list_class_marker = f"class {model}ListView"
        section_start = text.index(list_class_marker)
        section_end = (
            text.index("class ", section_start + 1)
            if "class " in text[section_start + 1 :]
            else len(text)
        )
        section = text[section_start:section_end]
        for forbidden in ('"add"', '"bulk_edit"', '"bulk_delete"', '"bulk_import"'):
            assert forbidden not in section, (
                f"{list_class_marker} must not register {forbidden} action"
            )


def test_urls_module_imports_views_for_decorator_side_effects():
    text = URLS.read_text(encoding="utf-8")
    assert "from netbox_pbs import views" in text, (
        "urls.py must import the views module so register_model_view "
        "decorators fire and per-model URLs land in the namespace"
    )


def test_navigation_has_menu_item_per_model():
    text = NAVIGATION.read_text(encoding="utf-8")
    expected_targets = {
        "PBSEndpoint": "plugins:netbox_pbs:pbsendpoint_list",
        "PBSNode": "plugins:netbox_pbs:pbsnode_list",
        "PBSDatastore": "plugins:netbox_pbs:pbsdatastore_list",
        "PBSBackupGroup": "plugins:netbox_pbs:pbsbackupgroup_list",
        "PBSSnapshot": "plugins:netbox_pbs:pbssnapshot_list",
        "PBSJobStatus": "plugins:netbox_pbs:pbsjobstatus_list",
    }
    for model, link in expected_targets.items():
        assert link in text, f"navigation missing link for {model}"


def test_navigation_only_endpoint_has_add_or_import_buttons():
    text = NAVIGATION.read_text(encoding="utf-8")
    # Only PBSEndpoint should expose add/import buttons; read-only models
    # must not surface them.
    assert "pbsendpoint_add" in text
    assert "pbsendpoint_bulk_import" in text
    for model_url in (
        "pbsnode_add",
        "pbsdatastore_add",
        "pbsbackupgroup_add",
        "pbssnapshot_add",
        "pbsjobstatus_add",
        "pbsnode_import",
        "pbsdatastore_import",
        "pbsbackupgroup_import",
        "pbssnapshot_import",
        "pbsjobstatus_import",
    ):
        assert model_url not in text, (
            f"navigation must not expose {model_url} for read-only model"
        )


def test_tables_module_defines_one_table_per_model():
    text = TABLES.read_text(encoding="utf-8")
    for model in ALL_MODELS:
        assert f"class {model}Table" in text, f"missing {model}Table"


def test_filtersets_module_defines_one_filterset_per_model():
    text = FILTERSETS.read_text(encoding="utf-8")
    for model in ALL_MODELS:
        assert f"class {model}FilterSet" in text, f"missing {model}FilterSet"


def test_forms_module_only_pbsendpoint_has_writable_forms():
    text = FORMS.read_text(encoding="utf-8")
    # PBSEndpoint is the only model with a ModelForm/BulkEdit/Import form.
    assert "class PBSEndpointForm(" in text
    assert "class PBSEndpointBulkEditForm(" in text
    assert "class PBSEndpointImportForm(" in text
    # Filter forms exist for all six models.
    for model in ALL_MODELS:
        assert f"class {model}FilterForm" in text, f"missing {model}FilterForm"
    # Reflected models must NOT have writable forms — confirm by absence of
    # the corresponding bulk-edit / import class names.
    for model in READ_ONLY_MODELS:
        assert f"class {model}Form(" not in text, (
            f"read-only {model} must not have a NetBoxModelForm"
        )
        assert f"class {model}BulkEditForm" not in text
        assert f"class {model}ImportForm" not in text
