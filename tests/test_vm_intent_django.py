"""Real-Django rendering coverage for the VM intent card."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

loader = pytest.importorskip("django.template.loader")


def test_cloud_init_user_data_is_autoescaped_in_the_intent_card():
    payload = '<script>alert("intent-xss")</script>'
    intent = SimpleNamespace(
        target_node="",
        target_storage="",
        iso="",
        template_vmid=None,
        swap=None,
        rootfs="",
        ostemplate="",
        cloud_init_user="",
        cloud_init_ssh_keys="",
        cloud_init_user_data=payload,
        cloud_init_network="",
        intent_state="",
        last_apply_run_id="",
    )

    rendered = loader.render_to_string(
        "netbox_proxbox/inc/vm_proxmox_intent_card.html",
        {"intent": intent, "edit_url": None},
    )

    assert payload not in rendered
    assert "&lt;script&gt;alert(&quot;intent-xss&quot;)&lt;/script&gt;" in rendered
