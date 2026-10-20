"""Fast unit contracts for endpoint-owned SSH application services."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "services"
    / "ssh_service_chain.py"
)
SPEC = importlib.util.spec_from_file_location(
    "_ssh_service_chain_under_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
ssh_service_chain = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ssh_service_chain)

SSH_SERVICE_DESCRIPTION = ssh_service_chain.SSH_SERVICE_DESCRIPTION
SSH_SERVICE_NAME = ssh_service_chain.SSH_SERVICE_NAME
find_ssh_service = ssh_service_chain.find_ssh_service
service_exposes_tcp_port = ssh_service_chain.service_exposes_tcp_port
service_ssh_port = ssh_service_chain.service_ssh_port


class _QuerySet:
    def __init__(self, rows):
        self.rows = list(rows)
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def order_by(self, *_fields):
        return self

    def __getitem__(self, value):
        return self.rows[value]


def test_service_port_helpers_use_fixed_tcp_and_port_contracts() -> None:
    service = SimpleNamespace(protocol="tcp", ports=[2222, 22, 2222])

    assert SSH_SERVICE_NAME == "ssh"
    assert (
        SSH_SERVICE_DESCRIPTION
        == "SSH remote login. Credentials are tied to this service."
    )
    assert service_exposes_tcp_port(service, 22) is True
    assert service_exposes_tcp_port(service, 23) is False
    assert service_ssh_port(service, 22) == 22
    assert service_ssh_port(service, 2022) == 22


def test_service_port_guard_rejects_udp_and_empty_ports() -> None:
    assert (
        service_exposes_tcp_port(SimpleNamespace(protocol="udp", ports=[22]), 22)
        is False
    )
    with pytest.raises(Exception, match="has no ports"):
        service_ssh_port(SimpleNamespace(protocol="tcp", ports=[]))


def test_find_service_scopes_to_endpoint_ip_and_exact_tcp_port() -> None:
    expected = SimpleNamespace(pk=7)
    queryset = _QuerySet([expected])
    endpoint = SimpleNamespace(pk=3)
    ip_address = SimpleNamespace(pk=5)

    result = find_ssh_service(endpoint, ip_address, 2222, queryset)

    assert result is expected
    assert queryset.filters == [
        {
            "endpoint": endpoint,
            "protocol": "tcp",
            "ports__contains": [2222],
            "ipaddresses": ip_address,
        }
    ]


def test_find_service_refuses_ambiguous_matches() -> None:
    queryset = _QuerySet([SimpleNamespace(pk=1), SimpleNamespace(pk=2)])

    with pytest.raises(Exception, match="More than one SSH application service"):
        find_ssh_service(SimpleNamespace(pk=3), SimpleNamespace(pk=4), 22, queryset)


def test_find_service_does_not_query_for_an_unsaved_endpoint() -> None:
    queryset = _QuerySet([SimpleNamespace(pk=1)])

    assert (
        find_ssh_service(SimpleNamespace(pk=None), SimpleNamespace(pk=4), 22, queryset)
        is None
    )
    assert queryset.filters == []


def test_service_openbao_resolution_is_reveal_scoped_and_assignment_bound() -> None:
    source = (
        MODULE_PATH.parents[1] / "integrations" / "openbao_service.py"
    ).read_text()

    assert 'objects.restrict(actor, "reveal")' in source
    assert 'purpose="console"' in source
    assert "enabled=True" in source
    assert "service SSH credential reference cannot be resolved" in source


def test_service_fernet_setters_and_clearers_mark_guarded_fields() -> None:
    source = (
        MODULE_PATH.parents[1] / "models" / "service_ssh_credential.py"
    ).read_text()

    assert source.count('mark_encrypted_fields_for_write(self, "password_enc")') == 2
    assert source.count('mark_encrypted_fields_for_write(self, "private_key_enc")') == 2


def test_release_migration_uses_idempotent_forward_and_owned_reverse() -> None:
    source = (
        MODULE_PATH.parents[1] / "migrations" / "0107_v0_0_30_release.py"
    ).read_text()

    assert source.count("create_model_idempotent(") == 2
    assert source.count("remove_on_reverse=True") == 4
    assert source.count("add_field_idempotent(") == 5
    assert "atomic = False" not in source
    assert 'cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")' in source
    assert "0106_device_sync_scope_and_netbox_token_approval" in source
