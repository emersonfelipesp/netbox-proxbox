"""Contract coverage for the overwrite_vm_type flag added for issue #350."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_constants():
    spec = importlib.util.spec_from_file_location(
        "_constants_for_overwrite_vm_type",
        REPO_ROOT / "netbox_proxbox" / "constants.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_overwrite_vm_type_order_matches_backend_contract():
    fields = _load_constants().OVERWRITE_FIELDS

    assert fields[fields.index("overwrite_vm_role") + 1] == "overwrite_vm_type"
    assert fields[fields.index("overwrite_vm_type") + 1] == "overwrite_vm_tags"


def test_overwrite_vm_type_model_fields_exist():
    plugin_settings = (REPO_ROOT / "netbox_proxbox/models/plugin_settings.py").read_text(
        encoding="utf-8"
    )
    proxmox_endpoint = (REPO_ROOT / "netbox_proxbox/models/proxmox_endpoint.py").read_text(
        encoding="utf-8"
    )

    assert "overwrite_vm_type = models.BooleanField(" in plugin_settings
    assert "default=True" in plugin_settings
    assert "overwrite_vm_type = models.BooleanField(" in proxmox_endpoint
    assert "null=True" in proxmox_endpoint
    assert "blank=True" in proxmox_endpoint


def test_overwrite_vm_type_migration_adds_global_and_endpoint_columns():
    path = REPO_ROOT / "netbox_proxbox/migrations/0036_add_overwrite_vm_type.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    source = ast.unparse(tree)

    assert "0035_overwrite_fields_expansion" in source
    assert "netbox_proxbox_proxboxpluginsettings" in source
    assert "netbox_proxbox_proxmoxendpoint" in source
    assert "overwrite_vm_type" in source
    assert "boolean NOT NULL DEFAULT TRUE" in source
    assert "boolean NULL" in source
