"""Pure one-use endpoint material intent contracts."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from tests.test_openbao_credential_integration import _load_openbao_module


@pytest.fixture
def pending(monkeypatch):
    _load_openbao_module(monkeypatch)
    return importlib.import_module("netbox_proxbox.integrations.openbao_pending")


@pytest.mark.parametrize(
    ("reference", "credential_type", "purpose", "material_field"),
    [
        ("openbao_password_credential_uuid", "password", "login", "password"),
        ("openbao_token_credential_uuid", "api-token", "api", "token"),
        ("openbao_ssh_password_credential_uuid", "ssh-password", "console", "password"),
        (
            "openbao_ssh_keypair_credential_uuid",
            "ssh-keypair",
            "console",
            "private_key",
        ),
    ],
)
def test_fixed_slots(
    pending, reference, credential_type, purpose, material_field
) -> None:
    slot = pending.SLOTS[reference]
    assert (slot.credential_type, slot.purpose, slot.material_field) == (
        credential_type,
        purpose,
        material_field,
    )
    assert len(pending.SLOTS) == 4


def test_queue_is_detached_and_does_not_change_reference(pending) -> None:
    endpoint = SimpleNamespace(openbao_password_credential_uuid="original")
    source = {"password": "canary-password"}
    actor, request = object(), object()
    pending.queue_credential(
        endpoint,
        "openbao_password_credential_uuid",
        source,
        user=actor,
        request=request,
    )
    source["password"] = "changed-by-caller"

    intent = pending.pending_credential(endpoint, "openbao_password_credential_uuid")

    assert intent.payload == {"password": "canary-password"}
    assert (
        intent.expected_uuid == endpoint.openbao_password_credential_uuid == "original"
    )
    assert intent.user is actor and intent.request is request
    assert "canary-password" not in repr(intent)


def test_replacing_intent_keeps_first_observed_reference(pending) -> None:
    endpoint = SimpleNamespace(openbao_password_credential_uuid="original")
    pending.queue_credential(
        endpoint,
        "openbao_password_credential_uuid",
        {"password": "first"},
    )
    endpoint.openbao_password_credential_uuid = "rebound"
    pending.queue_credential(
        endpoint,
        "openbao_password_credential_uuid",
        {"password": "second"},
    )

    intent = pending.pending_credential(endpoint, "openbao_password_credential_uuid")

    assert intent.expected_uuid == "original"
    assert intent.payload == {"password": "second"}


def test_consumption_is_one_use(pending) -> None:
    endpoint = SimpleNamespace()
    pending.queue_credential(
        endpoint,
        "openbao_password_credential_uuid",
        {"password": "one-use"},
    )

    consumed = pending.consume_credentials(endpoint)

    assert consumed["openbao_password_credential_uuid"].payload == {
        "password": "one-use"
    }
    assert pending.consume_credentials(endpoint) == {}
    assert (
        pending.pending_credential(endpoint, "openbao_password_credential_uuid") is None
    )
    assert "one-use" not in repr(endpoint)


def test_unknown_slot_does_not_create_state(pending) -> None:
    endpoint = SimpleNamespace()

    with pytest.raises(ValueError, match="Unsupported endpoint credential reference"):
        pending.queue_credential(endpoint, "unknown", {"password": "never-retained"})

    assert endpoint.__dict__ == {}
