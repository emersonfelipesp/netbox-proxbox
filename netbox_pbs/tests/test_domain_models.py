"""AST-based contract tests for the PR C2 PBS domain models.

The C1 boot tests in ``test_plugin_boots.py`` already prove that PR C1's
migration ``0001_initial`` does NOT contain the domain models. These
tests assert the symmetric property: PR C2's migration ``0002`` DOES
create each of the six expected tables and declares the unique
identity constraints the read-only PBS sync depends on.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "netbox_pbs" / "models"
MIGRATION_C2 = REPO_ROOT / "netbox_pbs" / "migrations" / "0002_pbs_domain_models.py"

DOMAIN_MODELS = (
    "PBSEndpoint",
    "PBSNode",
    "PBSDatastore",
    "PBSBackupGroup",
    "PBSSnapshot",
    "PBSJobStatus",
)


def _module_classes(path: Path) -> set[str]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(module) if isinstance(node, ast.ClassDef)}


def test_each_domain_model_lives_in_its_own_file():
    expected = {
        "PBSEndpoint": "pbs_endpoint.py",
        "PBSNode": "pbs_node.py",
        "PBSDatastore": "pbs_datastore.py",
        "PBSBackupGroup": "pbs_backup_group.py",
        "PBSSnapshot": "pbs_snapshot.py",
        "PBSJobStatus": "pbs_job_status.py",
    }
    for class_name, filename in expected.items():
        path = MODELS_DIR / filename
        assert path.exists(), f"missing {path}"
        assert class_name in _module_classes(path), (
            f"{class_name} not defined in {filename}"
        )


def test_models_init_reexports_domain_classes():
    text = (MODELS_DIR / "__init__.py").read_text(encoding="utf-8")
    for class_name in DOMAIN_MODELS:
        assert class_name in text, f"{class_name} not re-exported from models/__init__"


def test_migration_0002_creates_all_six_models():
    text = MIGRATION_C2.read_text(encoding="utf-8")
    assert (
        'dependencies = [\n        ("extras", "0001_initial"),\n        ("netbox_pbs", "0001_initial"),'
        in text
    )
    for class_name in DOMAIN_MODELS:
        assert f'name="{class_name}"' in text, (
            f"PR C2 migration must CreateModel({class_name})"
        )


def test_migration_0002_pins_identity_constraints():
    text = MIGRATION_C2.read_text(encoding="utf-8")
    for constraint in (
        "netbox_pbs_pbsnode_identity",
        "netbox_pbs_pbsdatastore_identity",
        "netbox_pbs_pbsbackupgroup_identity",
        "netbox_pbs_pbssnapshot_identity",
        "netbox_pbs_pbsjobstatus_identity",
    ):
        assert constraint in text, f"missing identity constraint {constraint}"


def test_pbs_endpoint_carries_credentials_no_allow_writes():
    text = (MODELS_DIR / "pbs_endpoint.py").read_text(encoding="utf-8")
    # Mirror ProxmoxEndpoint pattern: plaintext CharField gated by RBAC.
    assert "token_id" in text
    assert "token_value" in text
    assert "fingerprint" in text
    assert "verify_ssl" in text
    # v1 is read-only PBS → NetBox; no NetBox-side write path to gate.
    # Check for an actual field declaration, not docstring mentions.
    assert "allow_writes = models." not in text, (
        "v1 is read-only — allow_writes belongs on the proxbox-api side"
    )


def test_pbs_snapshot_files_field_is_json():
    text = (MODELS_DIR / "pbs_snapshot.py").read_text(encoding="utf-8")
    assert "files = models.JSONField" in text
    assert "CustomFieldJSONEncoder" in text


def test_pbs_job_status_datastore_link_is_nullable_set_null():
    text = (MODELS_DIR / "pbs_job_status.py").read_text(encoding="utf-8")
    # GC/verify/prune jobs always have a datastore; sync/tape may not.
    assert "datastore = models.ForeignKey" in text
    assert "SET_NULL" in text
    assert "null=True" in text
