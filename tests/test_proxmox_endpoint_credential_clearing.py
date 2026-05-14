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
        if (
            isinstance(stmt, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "fields" for t in stmt.targets)
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


def test_clean_preserves_unset_secrets_only_when_not_clearing() -> None:
    """The preserve-on-blank branch must be guarded by `not clear_*`."""
    src = _form_source()
    assert "not clear_password" in src
    assert "not clear_token" in src
    assert "self.instance.password" in src
    assert "self.instance.token_value" in src


def test_clean_rejects_half_token_and_empty_credentials() -> None:
    """Invariant: row must end with a password OR a complete (token_name, token_value)."""
    src = _form_source()
    assert "self.add_error(" in src
    assert "Token name is required" in src
    assert "Token value is required" in src
    assert "complete API token" in src


def test_clean_invariant_runs_after_clear_and_restore() -> None:
    """The invariant must see the final values, after clears and after restores."""
    src = _form_source()
    restore_idx = src.index("self.instance.token_value")
    invariant_idx = src.index("complete API token")
    assert invariant_idx > restore_idx, (
        "Credential invariant must run after the clear/restore branch"
    )
