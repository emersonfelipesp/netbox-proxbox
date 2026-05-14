"""AST-only contracts for Sub-PR K Cloud-Init intent payload wiring."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "payload.py"


def _source() -> str:
    return PAYLOAD_PATH.read_text(encoding="utf-8")


def test_payload_source_references_cloud_init_custom_fields():
    text = _source()
    for field_name in (
        "cloud_init_user",
        "cloud_init_ssh_keys",
        "cloud_init_user_data",
        "cloud_init_network",
    ):
        assert f'"{field_name}"' in text


def test_payload_source_emits_cloud_init_key():
    text = _source()
    assert '"cloud_init"' in text
    assert '"ssh_keys"' in text
    assert "splitlines" in text
