"""Migration and model contracts for the plugin-owned metrics credentials."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_upgrade_migration_clears_legacy_fields_before_constraints():
    source = (
        ROOT / "netbox_proxbox/migrations/0092_proxmox_metrics_plugin_credentials.py"
    ).read_text(encoding="utf-8")
    assert (
        'dependencies = [("netbox_proxbox", "0091_remove_branch_intent_custom_fields")]'
        in source
    )
    assert 'name="query_token_enc"' in source
    assert 'name="writer_token_enc"' not in source
    assert 'name="query_token_secret_ref"' in source
    assert 'name="writer_token_secret_ref"' in source
    assert "migrations.RunPython(_quarantine_legacy_credentials" in source
    assert "_reverse_quarantine" in source
    assert "IrreversibleError" in source
    assert 'name="netbox_proxbox_metrics_influxdb_query_token_configured"' in source
    assert '_URL_RE = r"^[Hh][Tt][Tt][Pp][Ss]://' in source


def test_encrypted_recovery_registry_includes_metrics_family():
    source = (ROOT / "netbox_proxbox/services/encryption_recovery.py").read_text(
        encoding="utf-8"
    )
    assert 'key="influxdb_metrics"' in source
    assert 'model_label="netbox_proxbox.ProxmoxMetricsInfluxDB"' in source
    assert '("query_token_enc",)' in source
