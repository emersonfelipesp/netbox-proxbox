"""Source contracts for exposing ``ssh_credential_source`` as a list filter
and table column on ``ProxmoxEndpoint``.

The selector field itself ships with the SSH-credential-source feature; these
tests pin that it is also filterable (UI filter form + REST API via the
filterset) and available as a toggleable table column. They run via
``ast.parse`` / source inspection so they do not require a live Django/NetBox
bootstrap.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "netbox_proxbox"

FORM_PATH = PLUGIN_ROOT / "forms" / "proxmox.py"
FILTERSET_PATH = PLUGIN_ROOT / "filtersets.py"
TABLE_PATH = PLUGIN_ROOT / "tables" / "__init__.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"Class {name!r} not found")


def _meta_fields(cls: ast.ClassDef) -> str:
    for node in cls.body:
        if isinstance(node, ast.ClassDef) and node.name == "Meta":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "fields" for t in stmt.targets
                ):
                    return ast.unparse(stmt.value)
    raise AssertionError(f"Meta.fields not found on class {cls.name}")


def _contains(rendered: str, name: str) -> bool:
    return f"'{name}'" in rendered or f'"{name}"' in rendered


def test_ssh_credential_source_in_filterset_meta_fields() -> None:
    """The REST/UI filterset must allow filtering by ``ssh_credential_source``."""
    cls = _find_class(_parse(FILTERSET_PATH), "ProxmoxEndpointFilterSet")
    assert _contains(_meta_fields(cls), "ssh_credential_source")


def test_ssh_credential_source_filter_form_field_exists() -> None:
    """The filter form must expose ``ssh_credential_source`` as a multi-choice filter."""
    src = FORM_PATH.read_text()
    block = src.split("class ProxmoxEndpointFilterForm", 1)[1]
    assert "ssh_credential_source = forms.MultipleChoiceField(" in block
    assert "SSH_CRED_SOURCE_CHOICES" in block


def test_ssh_credential_source_table_column_and_fields() -> None:
    """The endpoint table must declare a ``ssh_credential_source`` ChoiceFieldColumn
    and include it in ``Meta.fields`` (available/toggleable column)."""
    src = TABLE_PATH.read_text()
    assert "ssh_credential_source = ChoiceFieldColumn()" in src
    cls = _find_class(_parse(TABLE_PATH), "ProxmoxEndpointTable")
    assert _contains(_meta_fields(cls), "ssh_credential_source")
