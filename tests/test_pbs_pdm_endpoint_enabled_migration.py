"""Regression coverage for PBS/PDM endpoint ``enabled`` migration repair."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SQUASH_MIGRATION = (
    REPO_ROOT
    / "netbox_proxbox/migrations/0039_squashed_0039_0042_pve_9_2_firewall_sdn.py"
)
REPAIR_MIGRATION = (
    REPO_ROOT / "netbox_proxbox/migrations/0045_repair_pbs_pdm_endpoint_enabled.py"
)


def test_squashed_migration_adds_enabled_to_pbs_and_pdm_endpoints():
    content = SQUASH_MIGRATION.read_text()

    assert '"pbsendpoint"' in content
    assert '"pdmendpoint"' in content
    assert content.count('"enabled",') >= 5


def test_repair_migration_targets_pbs_and_pdm_enabled_columns():
    content = REPAIR_MIGRATION.read_text()

    assert 'MODEL_NAMES = ("PBSEndpoint", "PDMEndpoint")' in content
    assert 'model._meta.get_field("enabled")' in content
    assert "schema_editor.add_field(model, field)" in content
    assert "0044_merge_reconciliation_engine_settings" in content


def test_repair_migration_is_database_only():
    content = REPAIR_MIGRATION.read_text()

    assert "migrations.AddField" not in content
    assert "migrations.RunPython(" in content
