"""Source contracts for ProxmoxEndpointForm credential clearing (#417).

These pin the form-side fix that complements the proxbox-api auth fix:
- explicit per-credential "clear" checkboxes survive into ``cleaned_data``;
- those clears take precedence over the preserve-on-blank branch;
- the form rejects half-tokens and rows that end up with no credential at all;
- the clear checkboxes are removed when there is nothing stored to clear.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.test_openbao_credential_integration import _load_openbao_module
from tests.test_service_monitoring_model import _load_proxmox_forms


REPO_ROOT = Path(__file__).resolve().parents[1]
FORM_PATH = REPO_ROOT / "netbox_proxbox" / "forms" / "proxmox.py"


def _form_source() -> str:
    return FORM_PATH.read_text()


def _form_class() -> ast.ClassDef:
    module = ast.parse(_form_source())
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "ProxmoxEndpointForm":
            return node
    raise AssertionError("ProxmoxEndpointForm not found in proxmox.py")


def _method(name: str) -> ast.FunctionDef:
    for node in _form_class().body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"ProxmoxEndpointForm.{name} not found")


def _class_attr_names() -> set[str]:
    names: set[str] = set()
    for node in _form_class().body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def test_clear_credential_fields_are_declared() -> None:
    """Both clear-* fields must be declared on the form."""
    attrs = _class_attr_names()
    assert "clear_password" in attrs, "clear_password BooleanField must be declared"
    assert "clear_token" in attrs, "clear_token BooleanField must be declared"


def test_clear_fields_are_boolean_and_optional() -> None:
    """Both clear-* fields are optional BooleanFields (rendered as checkboxes)."""
    src = _form_source()
    for field in ("clear_password", "clear_token"):
        assert f"{field} = forms.BooleanField(" in src, (
            f"{field} must be a forms.BooleanField"
        )
    # The fields are optional so an unchecked checkbox is a valid submission.
    # Both BooleanField declarations include required=False.
    assert src.count("required=False") >= 2


def test_clear_fields_not_in_meta_fields() -> None:
    """clear_* fields are UI-only; they must not leak into ModelForm save()."""
    meta = None
    for node in _form_class().body:
        if isinstance(node, ast.ClassDef) and node.name == "Meta":
            meta = node
            break
    assert meta is not None, "ProxmoxEndpointForm.Meta not found"
    fields_value: ast.AST | None = None
    for stmt in meta.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "fields" for t in stmt.targets
        ):
            fields_value = stmt.value
            break
    assert fields_value is not None, "ProxmoxEndpointForm.Meta.fields not found"
    rendered = ast.unparse(fields_value)
    assert "clear_password" not in rendered
    assert "clear_token" not in rendered


def test_init_pops_clear_fields_when_instance_has_no_credential() -> None:
    """The clear checkboxes must be removed when there is nothing to clear."""
    init_src = FORM_PATH.read_text()
    # The branch that removes clear_password when no stored password exists.
    assert 'self.fields.pop("clear_password"' in init_src
    assert 'self.fields.pop("clear_token"' in init_src
    # Both fields are removed wholesale when the instance is unsaved.
    assert 'getattr(instance, "pk", None)' in init_src


def test_clean_blanks_password_on_explicit_clear() -> None:
    """clear_password=True must zero out password before any restore."""
    src = _form_source()
    assert "clear_password = bool(cleaned_data.get(" in src
    assert 'cleaned_data["password"] = ""' in src


def test_clean_paired_clears_both_token_fields() -> None:
    """clear_token=True must zero out BOTH token_name and token_value (paired clear)."""
    src = _form_source()
    assert "clear_token = bool(cleaned_data.get(" in src
    assert 'cleaned_data["token_name"] = ""' in src
    assert 'cleaned_data["token_value"] = ""' in src


@pytest.mark.parametrize(
    "clear_password,clear_token",
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_clean_preserves_unset_secrets_only_when_not_clearing(
    monkeypatch, clear_password, clear_token
) -> None:
    """Execute preservation and prove cleared fields are never resolved."""
    forms = _load_proxmox_forms(monkeypatch)
    openbao = _load_openbao_module(monkeypatch)
    form = forms.ProxmoxEndpointForm.__new__(forms.ProxmoxEndpointForm)
    form.instance = SimpleNamespace(pk=5)
    form.cleaned_data = {
        "password": "",
        "token_value": "",
        "clear_password": clear_password,
        "clear_token": clear_token,
    }
    with patch.object(
        openbao,
        "resolve_endpoint_api_secret",
        side_effect=lambda endpoint, field, **kwargs: f"stored-{field}",
    ) as resolve:
        form._preserve_primary_secrets()
    assert form.cleaned_data["password"] == (
        "" if clear_password else "stored-password"
    )
    assert form.cleaned_data["token_value"] == (
        "" if clear_token else "stored-token_value"
    )
    assert [call.args[1] for call in resolve.call_args_list] == [
        field
        for field, cleared in (
            ("password", clear_password),
            ("token_value", clear_token),
        )
        if not cleared
    ]


@pytest.mark.parametrize(
    "instance", [None, SimpleNamespace(pk=None), SimpleNamespace(pk=5)]
)
def test_preservation_does_not_resolve_new_or_replaced_secrets(
    monkeypatch, instance
) -> None:
    forms = _load_proxmox_forms(monkeypatch)
    openbao = _load_openbao_module(monkeypatch)
    form = forms.ProxmoxEndpointForm.__new__(forms.ProxmoxEndpointForm)
    form.instance = instance
    form.cleaned_data = {
        "password": "replacement-password",
        "token_value": "replacement-token",
    }
    with patch.object(openbao, "resolve_endpoint_api_secret") as resolve:
        form._preserve_primary_secrets()
    resolve.assert_not_called()


def test_preservation_reports_unresolvable_required_material(monkeypatch) -> None:
    forms = _load_proxmox_forms(monkeypatch)
    openbao = _load_openbao_module(monkeypatch)
    form = forms.ProxmoxEndpointForm.__new__(forms.ProxmoxEndpointForm)
    form.instance = SimpleNamespace(pk=5)
    form.cleaned_data = {"password": "", "token_value": ""}
    errors = []
    form.add_error = lambda field, message: errors.append((field, message))
    # Use the form's imported exception class; the two isolated loaders install
    # independent Django stand-ins, whereas real Django has a single class.
    with patch.object(
        openbao,
        "resolve_endpoint_api_secret",
        side_effect=forms.ValidationError("credential unavailable"),
    ):
        form._preserve_primary_secrets()
    assert errors == [
        ("password", "credential unavailable"),
        ("token_value", "credential unavailable"),
    ]


def test_clean_rejects_half_token_and_empty_credentials() -> None:
    """Invariant: row must end with a password OR a complete (token_name, token_value)."""
    src = _form_source()
    assert "self.add_error(" in src
    assert "Token name is required" in src
    assert "Token value is required" in src
    assert "complete API token" in src


@pytest.mark.parametrize(
    "password,token_name,token_value,expected_fields",
    [
        ("password", "", "", []),
        ("", "name", "token", []),
        ("password", "", "token", ["token_name"]),
        ("password", "name", "", ["token_value"]),
        ("", "", "", ["password", "token_name"]),
    ],
)
def test_primary_invariant_validates_final_material(
    monkeypatch, password, token_name, token_value, expected_fields
) -> None:
    forms = _load_proxmox_forms(monkeypatch)
    form = forms.ProxmoxEndpointForm.__new__(forms.ProxmoxEndpointForm)
    form.cleaned_data = {
        "password": password,
        "token_name": token_name,
        "token_value": token_value,
    }
    errors = []
    form.add_error = lambda field, message: errors.append(field)
    form._validate_primary_credentials()
    assert errors == expected_fields


@pytest.mark.parametrize(
    "kind", ["no_secret", "password", "token", "scalar_error", "field_error"]
)
def test_form_storage_validation_preserves_fail_closed_errors(
    monkeypatch, kind
) -> None:
    forms = _load_proxmox_forms(monkeypatch)
    openbao = _load_openbao_module(monkeypatch)
    form = forms.ProxmoxEndpointForm.__new__(forms.ProxmoxEndpointForm)
    form.instance = object()
    form.cleaned_data = {"credential_storage_backend": "openbao", "allow_writes": True}
    if kind in {"password", "token"}:
        form.cleaned_data["password" if kind == "password" else "token_value"] = (
            "submitted"
        )
    errors = []
    form.add_error = lambda field, message: errors.append((field, message))
    error = None
    if kind in {"scalar_error", "field_error"}:
        error = forms.ValidationError("missing OpenBao prerequisites")
        error.messages = ["missing OpenBao prerequisites"]
        if kind == "field_error":
            error.error_dict = {
                "credential_storage_backend": ["missing OpenBao prerequisites"]
            }
    with (
        patch.object(
            openbao, "validate_write_mode_openbao_requirements", side_effect=error
        ) as validate,
        patch.object(openbao, "validate_openbao_storage_available") as storage,
    ):
        form._validate_storage_prerequisites()
    validate.assert_called_once_with(
        form.instance, allow_writes=True, storage_backend="openbao"
    )
    assert storage.call_count == (1 if kind in {"password", "token"} else 0)
    assert errors == (
        [("credential_storage_backend", "missing OpenBao prerequisites")]
        if error
        else []
    )


def test_clean_invariant_runs_after_clear_and_restore() -> None:
    """The invariant must see the final values, after clears and after restores."""
    src = _form_source()
    clean = ast.get_source_segment(src, _method("clean"))
    assert clean is not None
    restore_idx = clean.index("self._preserve_primary_secrets()")
    invariant_idx = clean.index("self._validate_primary_credentials()")
    assert clean.index('cleaned_data["token_value"] = ""') < restore_idx
    assert invariant_idx > restore_idx, (
        "Credential invariant must run after the clear/restore branch"
    )
