"""UI contracts for editable intent values and safe detail rendering."""

from __future__ import annotations

import ast
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "netbox_proxbox"
FORM = ROOT / "forms" / "vm_intent.py"
CARD = ROOT / "templates" / "netbox_proxbox" / "inc" / "vm_proxmox_intent_card.html"


def test_apply_managed_stamps_are_not_in_the_operator_form():
    module = ast.parse(FORM.read_text(encoding="utf-8"))
    form_class = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "ProxmoxVMIntentForm"
    )
    meta = next(
        node
        for node in form_class.body
        if isinstance(node, ast.ClassDef) and node.name == "Meta"
    )
    fields_assignment = next(
        node
        for node in meta.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "fields"
            for target in node.targets
        )
    )
    fields = set(ast.literal_eval(fields_assignment.value))

    assert "intent_state" not in fields
    assert "last_apply_run_id" not in fields
    assert {
        "target_node",
        "target_storage",
        "iso",
        "template_vmid",
        "swap",
        "rootfs",
        "ostemplate",
        "cloud_init_user",
        "cloud_init_ssh_keys",
        "cloud_init_user_data",
        "cloud_init_network",
    } <= fields


def test_user_data_is_rendered_through_django_autoescape_not_safe_markup():
    source = CARD.read_text(encoding="utf-8")
    payload = '<script>alert("intent-xss")</script>'

    assert "{{ intent.cloud_init_user_data }}" in source
    assert "intent.cloud_init_user_data|safe" not in source
    assert "mark_safe" not in source
    assert html.escape(payload) == (
        "&lt;script&gt;alert(&quot;intent-xss&quot;)&lt;/script&gt;"
    )
