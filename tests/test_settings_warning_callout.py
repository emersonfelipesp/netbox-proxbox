"""Sub-PR B (#379): warning-callout block on the Settings page.

The red callout introduced on ``origin/develop`` for the v0.0.15 release warns
operators about the netbox_to_proxmox_enabled master flag. This contract test
pins its presence and the four required pieces of language so a careless
template refactor cannot silently strip the warning. Migration 0037 already
adds the underlying form fields; this test focuses on the rendered template.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_TEMPLATE = (
    REPO_ROOT
    / "netbox_proxbox"
    / "templates"
    / "netbox_proxbox"
    / "settings.html"
)


def _read() -> str:
    return SETTINGS_TEMPLATE.read_text()


def test_red_warning_block_present():
    """The callout must use ``text-danger`` so it visibly renders red."""
    html = _read()
    assert 'text-danger' in html, (
        "Settings template must keep the red 'text-danger' warning class on "
        "the NetBox → Proxmox intent callout."
    )


def test_advanced_heading_present():
    html = _read()
    assert "NetBox → Proxmox intent direction (advanced)" in html, (
        "Settings template must keep the 'advanced' warning heading verbatim."
    )


def test_apply_to_proxmox_phrase_present():
    """The body must explain ``apply_to_proxmox=True`` triggers writes."""
    html = _read()
    assert "apply_to_proxmox=True" in html


def test_delete_requires_authorization_chain():
    """The body must explain DELETE goes through a DeletionRequest chain."""
    html = _read()
    assert "DeletionRequest" in html


def test_three_intent_fields_rendered():
    html = _read()
    for field in (
        "form.netbox_to_proxmox_enabled",
        "form.netbox_to_proxmox_typed_confirmation",
        "form.apply_destroy_confirmed",
    ):
        assert field in html, f"Settings template must render {field}"
