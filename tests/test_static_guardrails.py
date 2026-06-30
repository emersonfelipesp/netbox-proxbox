"""Static contract tests for LLM agent safety guardrails.

Read-only file assertions — no Django/NetBox setup required.
These tests pin the presence of machine-readable LLM safety policy and the
read-only DeletionRequest viewset constraint so accidental degradation is
caught immediately by CI.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AGENTS.md guardrails presence
# ---------------------------------------------------------------------------


def test_agents_md_contains_llm_guardrails_section():
    content = _read("AGENTS.md")
    assert "LLM Agent Safety Guardrails" in content, (
        "AGENTS.md must contain '## LLM Agent Safety Guardrails' section"
    )


def test_agents_md_documents_five_lock_chain():
    content = _read("AGENTS.md")
    assert "apply_destroy_confirmed" in content, (
        "AGENTS.md must document apply_destroy_confirmed as part of the five-lock chain"
    )


def test_agents_md_documents_deletion_request_read_only():
    content = _read("AGENTS.md")
    assert "DeletionRequest" in content and "read-only" in content.lower(), (
        "AGENTS.md must document DeletionRequest REST endpoint as read-only"
    )


def test_agents_md_documents_self_approve_restriction():
    content = _read("AGENTS.md")
    assert "self_approve_allowed" in content or "self_approve" in content, (
        "AGENTS.md must document self_approve_allowed=False four-eyes invariant"
    )


def test_agents_md_forbids_autonomous_confirmation_phrase():
    content = _read("AGENTS.md")
    assert "allow-edit-and-add-actions" in content, (
        "AGENTS.md must document the confirmation phrase and forbid LLM agents from submitting it"
    )


def test_agents_md_forbids_autonomous_apply_destroy():
    content = _read("AGENTS.md")
    assert "MUST NOT" in content or "Never autonomously" in content, (
        "AGENTS.md must explicitly prohibit autonomous intent apply with destroy confirmation"
    )


# ---------------------------------------------------------------------------
# CLAUDE.md safety blockquote
# ---------------------------------------------------------------------------


def test_claude_md_contains_safety_blockquote():
    content = _read("CLAUDE.md")
    assert "LLM Agent Safety" in content, (
        "CLAUDE.md must contain an LLM Agent Safety blockquote near the top"
    )


def test_claude_md_references_agents_md_guardrails():
    content = _read("CLAUDE.md")
    assert "AGENTS.md" in content and "Guardrails" in content, (
        "CLAUDE.md safety blockquote must reference AGENTS.md §'LLM Agent Safety Guardrails'"
    )


# ---------------------------------------------------------------------------
# DeletionRequest viewset: enforces read-only http_method_names
# ---------------------------------------------------------------------------


def test_deletion_request_viewset_is_read_only():
    content = _read("netbox_proxbox/api/views.py")
    # The viewset class for DeletionRequest must restrict http_method_names to
    # read-only methods (no POST, PUT, PATCH, DELETE allowed via REST API).
    assert 'http_method_names = ["get", "head", "options"]' in content, (
        'DeletionRequest viewset must set http_method_names=["get","head","options"] '
        "to prevent REST-driven creation, update, or deletion"
    )


# ---------------------------------------------------------------------------
# Security: no forbidden patterns in plugin source
# ---------------------------------------------------------------------------


def test_models_contain_no_exec():
    # Security assertion: scans source text to ensure exec() is absent.
    content = _read("netbox_proxbox/models/__init__.py")
    assert "exec(" not in content, (
        "netbox_proxbox/models/__init__.py must not use exec()"
    )


def test_views_contain_no_innerHTML():
    # Security assertion: scans source text to ensure XSS sink is absent.
    content = _read("netbox_proxbox/api/views.py")
    assert "innerHTML" not in content, (
        "netbox_proxbox/api/views.py must not use innerHTML"
    )
