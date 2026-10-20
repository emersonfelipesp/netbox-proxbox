"""Source contracts for the Cloud Image SSH binding surfaces."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _class(path: str, name: str) -> ast.ClassDef:
    tree = ast.parse((ROOT / path).read_text())
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _model_field(name: str) -> ast.Call:
    model = _class("netbox_proxbox/models/proxmox_endpoint.py", "ProxmoxEndpoint")
    fields = {
        target.id: value
        for node in model.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance((target := node.targets[0]), ast.Name)
        and isinstance((value := node.value), ast.Call)
    }

    return fields[name]


def _assert_constant(keywords: dict[str | None, ast.expr], name: str, expected) -> None:
    value = keywords[name]
    assert isinstance(value, ast.Constant)
    assert value.value == expected


@pytest.mark.parametrize(
    ("name", "max_length"),
    (
        ("cloud_image_ssh_target_node", 255),
        ("cloud_image_ssh_identity_file", 4096),
        ("cloud_image_ssh_binding_fingerprint", 64),
    ),
)
def test_model_declares_plain_blank_cloud_image_binding_fields(
    name: str, max_length: int
) -> None:
    field = _model_field(name)
    keywords = {keyword.arg: keyword.value for keyword in field.keywords}

    assert ast.unparse(field.func).endswith("CharField")
    _assert_constant(keywords, "max_length", max_length)
    _assert_constant(keywords, "blank", True)
    _assert_constant(keywords, "default", "")
    _assert_constant(keywords, "db_default", "")
    if name == "cloud_image_ssh_binding_fingerprint":
        _assert_constant(keywords, "editable", False)


def test_consolidated_migration_adds_binding_fields_from_published_boundary() -> None:
    source = (ROOT / "netbox_proxbox/migrations/0107_v0_0_30_release.py").read_text()

    assert (
        '("netbox_proxbox", "0106_device_sync_scope_and_netbox_token_approval")'
        in source
    )
    assert '"cloud_image_ssh_target_node"' in source
    assert '"cloud_image_ssh_identity_file"' in source
    assert '"cloud_image_ssh_binding_fingerprint"' in source
    assert source.count("remove_on_reverse=True") == 4
