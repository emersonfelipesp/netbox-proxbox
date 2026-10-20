"""Transport refusal when a Cloud Image ownership receipt cannot commit."""

from contextlib import nullcontext
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_backend_sync_placement import _load_backend_sync_module

_DOC_SSH_HOST = ".".join(("192", "0", "2", "177"))


def binding_payload() -> dict[str, object]:
    return {
        "enabled": True,
        "allow_packer_template_builds": True,
        "ssh_target_node": "synthetic-node",
        "ssh_host": _DOC_SSH_HOST,
        "ssh_username": "root",
        "ssh_port": 22,
        "ssh_identity_file": "/srv/proxbox/ssh/image-builder",
        "ssh_known_host_fingerprint": "SHA256:synthetic-host-key",
    }


def send_binding(
    backend: object, endpoint: object
) -> tuple[bool, str | None, int | None]:
    return backend._send_approved_proxmox_payload(
        endpoint,
        payload=binding_payload(),
        fingerprint="synthetic-credential-fingerprint",
        existing={"id": 1},
        binding_receipt="",
        list_url="http://127.0.0.1:1/proxmox/endpoints",
        base_url="http://127.0.0.1:1",
        headers={},
        backend_verify_ssl=True,
        timeout=1.0,
        deadline=None,
    )


@pytest.fixture
def receipt_case(monkeypatch) -> tuple[object, object, Mock, object]:
    backend = _load_backend_sync_module(monkeypatch)
    manager = Mock()
    manager.using.return_value = manager
    manager.filter.return_value = manager
    manager.update.return_value = 1
    endpoint = type("Endpoint", (), {"objects": manager})()
    endpoint.pk = 1
    endpoint.cloud_image_ssh_binding_fingerprint = ""
    connection = SimpleNamespace(
        in_atomic_block=False, get_autocommit=Mock(return_value=True)
    )
    monkeypatch.setattr(
        sys.modules["django.db"],
        "router",
        SimpleNamespace(db_for_write=Mock(return_value="default")),
        raising=False,
    )
    monkeypatch.setattr(
        sys.modules["django.db"],
        "transaction",
        SimpleNamespace(
            get_connection=Mock(return_value=connection),
            atomic=Mock(return_value=nullcontext()),
        ),
        raising=False,
    )
    monkeypatch.setattr(backend.requests, "put", Mock())
    monkeypatch.setattr(backend.requests, "post", Mock())
    return backend, endpoint, manager, connection


@pytest.mark.parametrize("updated", (0, 2, True))
def test_receipt_requires_exactly_one_integer_row(receipt_case, updated) -> None:
    backend, endpoint, manager, _connection = receipt_case
    manager.update.return_value = updated
    result = send_binding(backend, endpoint)
    assert result[0] is False
    assert "ownership receipt" in result[1]
    backend.requests.put.assert_not_called()
    backend.requests.post.assert_not_called()
    assert endpoint.cloud_image_ssh_binding_fingerprint == ""


def test_database_failure_does_not_disclose_details_or_send(receipt_case) -> None:
    backend, endpoint, manager, _connection = receipt_case
    manager.update.side_effect = backend.DatabaseError(
        "synthetic-private-database-detail"
    )
    result = send_binding(backend, endpoint)
    assert result[0] is False
    assert "could not be committed" in result[1]
    assert "synthetic-private-database-detail" not in result[1]
    backend.requests.put.assert_not_called()
    backend.requests.post.assert_not_called()


def test_unsaved_owner_does_not_send(receipt_case) -> None:
    backend, endpoint, manager, _connection = receipt_case
    endpoint.pk = None
    assert send_binding(backend, endpoint)[0] is False
    manager.update.assert_not_called()
    backend.requests.put.assert_not_called()


def test_database_connection_failure_does_not_send(receipt_case) -> None:
    backend, endpoint, manager, connection = receipt_case
    connection.get_autocommit.side_effect = backend.DatabaseError(
        "synthetic-connect-failure"
    )
    result = send_binding(backend, endpoint)
    assert result[0] is False
    assert "could not be committed" in result[1]
    assert "synthetic-connect-failure" not in result[1]
    manager.update.assert_not_called()
    backend.requests.put.assert_not_called()


def test_selected_service_username_populates_binding(monkeypatch) -> None:
    backend = _load_backend_sync_module(monkeypatch)
    endpoint = SimpleNamespace(
        access_methods="api_ssh",
        cloud_image_ssh_binding_fingerprint="",
        cloud_image_ssh_target_node="synthetic-node",
        cloud_image_ssh_identity_file="/srv/proxbox/ssh/image-builder",
        ssh_host=_DOC_SSH_HOST,
        ssh_username="",
        effective_ssh_username="root",
        ssh_port=22,
        ssh_known_host_fingerprint="SHA256:synthetic-host-key",
    )
    monkeypatch.setattr(
        backend, "_packer_template_builds_effectively_allowed", Mock(return_value=True)
    )
    monkeypatch.setattr(
        backend, "cloud_image_ssh_target_matches_host", Mock(return_value=True)
    )
    binding, revoke = backend._cloud_image_ssh_binding(endpoint)
    assert revoke is False
    assert binding["ssh_username"] == "root"


@pytest.mark.parametrize("in_atomic,autocommit", ((True, True), (False, False)))
def test_uncommitted_outer_transaction_does_not_send(
    receipt_case, in_atomic, autocommit
) -> None:
    backend, endpoint, manager, connection = receipt_case
    connection.in_atomic_block = in_atomic
    connection.get_autocommit.return_value = autocommit
    result = send_binding(backend, endpoint)
    assert result[0] is False
    assert "committed transaction" in result[1]
    manager.update.assert_not_called()
    backend.requests.put.assert_not_called()
