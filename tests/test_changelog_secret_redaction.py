"""Sensitive-field inventory and pure snapshot redaction contracts."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_redaction(monkeypatch) -> object:
    name = "netbox_proxbox.models.changelog_redaction"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "netbox_proxbox/models/changelog_redaction.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def redaction(monkeypatch) -> object:
    return load_redaction(monkeypatch)


@pytest.mark.parametrize(
    "model",
    [
        "proxboxpluginsettings",
        "proxmoxendpoint",
        "netboxendpoint",
        "fastapiendpoint",
        "pbsendpoint",
        "pdmendpoint",
        "nodesshcredential",
        "firecrackerhost",
        "proxmoxvmcloudinit",
        "proxmoxmetricsinfluxdb",
    ],
)
def test_every_registered_field_is_masked_without_mutating_original(
    redaction, model
) -> None:
    fields = redaction.SENSITIVE_OBJECTCHANGE_FIELDS[model]
    snapshot = dict.fromkeys(fields, "synthetic-material-marker")
    snapshot["name"] = "Visible inventory"
    snapshot["port"] = 443
    result = redaction.redact_snapshot_data(f"netbox_proxbox.{model}", snapshot)
    assert {result[field] for field in fields} == {redaction.MASKED_SECRET}
    assert result["name"] == snapshot["name"]
    assert result["port"] == 443
    assert {snapshot[field] for field in fields} == {"synthetic-material-marker"}


@pytest.mark.parametrize("empty", ["", None])
def test_empty_and_excluded_fields_remain_empty_or_absent(redaction, empty) -> None:
    result = redaction.redact_snapshot_data(
        "proxboxpluginsettings", {"encryption_key": empty}
    )
    assert result == {"encryption_key": empty}
    assert redaction.redact_snapshot_data(
        "proxboxpluginsettings", {"name": "settings"}
    ) == {"name": "settings"}


def test_registry_covers_every_owned_ciphertext_and_provider_reference(
    redaction,
) -> None:
    for path in (ROOT / "netbox_proxbox/models").glob("*.py"):
        for cls in ast.parse(path.read_text()).body:
            if not isinstance(cls, ast.ClassDef):
                continue
            fields = redaction.SENSITIVE_OBJECTCHANGE_FIELDS.get(cls.name.lower(), ())
            for node in cls.body:
                if not isinstance(node, ast.Assign) or not isinstance(
                    node.value, ast.Call
                ):
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name) and (
                        target.id.endswith("_enc")
                        or target.id.endswith("_credential_uuid")
                    ):
                        assert target.id in fields, (
                            f"{path.name}: {cls.name}.{target.id} lacks redaction"
                        )


def test_changelog_hooks_cover_the_registry_models() -> None:
    files = (
        "base",
        "plugin_settings",
        "ssh_credential",
        "firecracker",
        "vm_cloudinit",
        "proxmox_metrics",
    )
    for name in files:
        tree = ast.parse((ROOT / "netbox_proxbox/models" / f"{name}.py").read_text())
        hooks = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "serialize_object"
        ]
        assert hooks, name
        assert any(
            isinstance(node, ast.Name) and node.id == "redact_snapshot_data"
            for node in ast.walk(hooks[0])
        )
