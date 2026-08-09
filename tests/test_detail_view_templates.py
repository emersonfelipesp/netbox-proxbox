"""Contracts for templates resolved by registered object detail views."""

from __future__ import annotations

import ast
from pathlib import Path
import re

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWS_ROOT = REPO_ROOT / "netbox_proxbox" / "views"
TEMPLATES_ROOT = REPO_ROOT / "netbox_proxbox" / "templates"


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _registered_model_names(class_node: ast.ClassDef) -> tuple[str, ...]:
    model_names = []
    for decorator in class_node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        decorator_name = _dotted_name(decorator.func)
        if not decorator_name or decorator_name.rsplit(".", 1)[-1] != (
            "register_model_view"
        ):
            continue
        if not decorator.args:
            continue
        model_name = _dotted_name(decorator.args[0])
        if model_name:
            model_names.append(model_name.rsplit(".", 1)[-1])
    return tuple(model_names)


def _is_object_view(class_node: ast.ClassDef) -> bool:
    return any(
        (_dotted_name(base) or "").rsplit(".", 1)[-1] == "ObjectView"
        for base in class_node.bases
    )


def _explicit_template_name(class_node: ast.ClassDef) -> str | None:
    for statement in class_node.body:
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "template_name"
            for target in statement.targets
        ):
            value = statement.value
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "template_name"
        ):
            value = statement.value
        if value is not None:
            template_name = ast.literal_eval(value)
            assert template_name is None or isinstance(template_name, str), (
                f"{class_node.name}.template_name must resolve to a string or None"
            )
            return template_name
    return None


def _registered_object_view_templates() -> tuple[tuple[str, str, Path], ...]:
    registrations = []
    for source_path in sorted(VIEWS_ROOT.rglob("*.py")):
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not _is_object_view(node):
                continue
            for model_name in _registered_model_names(node):
                template_name = _explicit_template_name(node)
                if template_name is None:
                    template_name = f"netbox_proxbox/{model_name.lower()}.html"
                registrations.append(
                    (
                        f"{source_path.relative_to(REPO_ROOT)}::{node.name}",
                        template_name,
                        TEMPLATES_ROOT / template_name,
                    )
                )
    assert registrations, "No registered ObjectView subclasses were discovered"
    return tuple(registrations)


@pytest.mark.parametrize(
    ("view_name", "template_name", "template_path"),
    _registered_object_view_templates(),
)
def test_registered_object_view_template_exists(
    view_name: str,
    template_name: str,
    template_path: Path,
) -> None:
    assert template_path.is_file(), (
        f"{view_name} resolves {template_name!r}, but that template does not exist"
    )


def test_node_ssh_credential_detail_template_never_references_secrets() -> None:
    template = (
        TEMPLATES_ROOT / "netbox_proxbox" / "nodesshcredential.html"
    ).read_text()

    for forbidden_name in (
        "password_enc",
        "private_key_enc",
        "get_password",
        "get_private_key",
    ):
        assert forbidden_name not in template


def test_metrics_detail_template_uses_only_fail_closed_token_displays() -> None:
    template = (
        TEMPLATES_ROOT / "netbox_proxbox" / "proxmoxmetricsinfluxdb.html"
    ).read_text()
    object_attributes = set(re.findall(r"\bobject\.([A-Za-z_]\w*)", template))

    assert "query_token_secret_ref_display" in object_attributes
    assert "writer_token_secret_ref_display" in object_attributes
    assert "query_token_secret_ref" not in object_attributes
    assert "writer_token_secret_ref" not in object_attributes
