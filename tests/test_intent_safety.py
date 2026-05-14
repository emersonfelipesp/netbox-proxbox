"""Static regression tests for the intent Safety Model invariants."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SETTINGS_PATH = REPO_ROOT / "netbox_proxbox" / "models" / "plugin_settings.py"
DELETION_REQUEST_PATH = (
    REPO_ROOT / "netbox_proxbox" / "models" / "deletion_request.py"
)


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{name} class not found")


def _field_call(class_def: ast.ClassDef, field_name: str) -> ast.Call:
    for node in class_def.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == field_name
            for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Call):
            return node.value
    raise AssertionError(f"{field_name} field assignment not found")


def _literal_keyword(call: ast.Call, keyword_name: str) -> object:
    for keyword in call.keywords:
        if keyword.arg == keyword_name and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    raise AssertionError(f"{keyword_name} literal keyword not found")


def _constant_assignment(module: ast.Module, constant_name: str) -> object:
    for node in module.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == constant_name
            for target in node.targets
        ):
            return node.value.value
    raise AssertionError(f"{constant_name} assignment not found")


def test_netbox_to_proxmox_master_flag_defaults_false():
    settings_class = _class(_module(PLUGIN_SETTINGS_PATH), "ProxboxPluginSettings")
    field = _field_call(settings_class, "netbox_to_proxmox_enabled")
    assert _literal_keyword(field, "default") is False


def test_typed_confirmation_phrase_literal_is_pinned():
    module = _module(PLUGIN_SETTINGS_PATH)
    assert (
        _constant_assignment(module, "NETBOX_TO_PROXMOX_TYPED_PHRASE")
        == "allow-edit-and-add-actions"
    )


def test_deletion_request_authorization_permission_is_declared():
    deletion_request = _class(_module(DELETION_REQUEST_PATH), "DeletionRequest")
    meta = next(
        (
            node
            for node in deletion_request.body
            if isinstance(node, ast.ClassDef) and node.name == "Meta"
        ),
        None,
    )
    assert meta is not None, "DeletionRequest.Meta must exist"
    string_literals = {
        node.value
        for node in ast.walk(meta)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "authorize_deletion_request" in string_literals


def test_self_approval_setting_defaults_false():
    settings_class = _class(_module(PLUGIN_SETTINGS_PATH), "ProxboxPluginSettings")
    field = _field_call(
        settings_class,
        "intent_apply_authorization_self_approve_allowed",
    )
    assert _literal_keyword(field, "default") is False


def test_deletion_request_ttl_defaults_seven_days():
    settings_class = _class(_module(PLUGIN_SETTINGS_PATH), "ProxboxPluginSettings")
    field = _field_call(settings_class, "intent_deletion_request_ttl_days")
    assert _literal_keyword(field, "default") == 7
