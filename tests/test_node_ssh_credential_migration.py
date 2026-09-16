"""Contracts for migration to local node SSH credentials."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_missing_node_credential_returns_actionable_not_found() -> None:
    source = (ROOT / "netbox_proxbox/api/ssh_credentials.py").read_text()
    assert "No local NodeSSHCredential is registered for this node" in source
    assert "status=status.HTTP_404_NOT_FOUND" in source


def test_pre_upgrade_audit_lists_missing_local_credentials() -> None:
    source = (
        ROOT / "netbox_proxbox/management/commands/audit_node_ssh_credentials.py"
    ).read_text()
    assert "ssh_credential__isnull=True" in source
    assert "endpoint__enabled=True" in source
    assert "ProxmoxAccessMethodChoices.API_SSH" in source
    assert 'parser.add_argument("--fail-on-missing"' in source
    assert "blocking_missing_local_credentials=" in source
    assert "informational_missing_local_credentials=" in source
    assert "CommandError" in source


def test_upgrade_guide_requires_a_clean_local_credential_audit() -> None:
    guide = (ROOT / "docs/configuration/hardware-discovery.md").read_text()
    assert "audit_node_ssh_credentials --fail-on-missing" in guide
    assert "blocking_missing_local_credentials=0" in guide
