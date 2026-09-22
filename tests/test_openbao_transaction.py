"""Pure admission tests for the provider-owned transaction adapter."""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_openbao_credential_integration import _load_openbao_module


@pytest.fixture
def admission(monkeypatch):
    _load_openbao_module(monkeypatch)
    monkeypatch.delitem(
        sys.modules,
        "netbox_proxbox.integrations.openbao_transaction",
        raising=False,
    )
    module = importlib.import_module("netbox_proxbox.integrations.openbao_transaction")
    provider = ModuleType("netbox_openbao.material_transactions")
    provider.MATERIAL_TRANSACTION_CONTRACT_VERSION = 1
    events = []

    @contextmanager
    def owner():
        events.append("owner-enter")
        try:
            yield
        finally:
            events.append("owner-exit")

    provider.material_transaction = owner
    monkeypatch.setitem(sys.modules, "netbox_openbao.material_transactions", provider)
    return module, provider, events


def _context(module, *, endpoints=None, allow_new=False):
    return module.EndpointMaterialContext(
        settings=None,
        endpoints=endpoints or {},
        credentials={},
        policy=None,
        content_type=None,
        allow_new=allow_new,
    )


def test_new_owner_remains_admitted_after_insert(admission) -> None:
    module, _, _ = admission
    context = _context(module, allow_new=True)
    endpoint = SimpleNamespace(pk=None, _state=SimpleNamespace(adding=True))
    context.admit(endpoint)
    endpoint.pk = 41
    endpoint._state.adding = False

    context.admit(endpoint)

    assert context.new_instances == {id(endpoint): endpoint}


@pytest.mark.parametrize(("pk", "adding"), [(1, False), (None, False), (1, True)])
def test_new_admission_refuses_inconsistent_owner(admission, pk, adding) -> None:
    module, _, _ = admission
    context = _context(module, allow_new=True)

    with pytest.raises(module.ValidationError, match="ownership was not declared"):
        context.admit(SimpleNamespace(pk=pk, _state=SimpleNamespace(adding=adding)))


def test_provider_owner_precedes_declaration_and_context_resets(
    admission,
    monkeypatch,
) -> None:
    module, _, events = admission
    context = _context(module)

    def declare(endpoints, *, allow_new):
        assert events == ["owner-enter"]
        assert endpoints == [] and allow_new is False
        events.append("declared")
        return context

    monkeypatch.setattr(module, "_declare_context", declare)
    with module.endpoint_material_transaction([]) as active:
        assert active is module.current_endpoint_material_context() is context
        events.append("native-save")

    assert events == ["owner-enter", "declared", "native-save", "owner-exit"]
    assert module.current_endpoint_material_context() is None


def test_nested_calls_cannot_extend_owner_graph(admission, monkeypatch) -> None:
    module, _, _ = admission
    context = _context(module, endpoints={1: object()})
    declaration = Mock(return_value=context)
    monkeypatch.setattr(module, "_declare_context", declaration)

    with module.endpoint_material_transaction([]):
        with module.endpoint_material_transaction([SimpleNamespace(pk=1)]):
            pass
        with pytest.raises(module.ValidationError, match="ownership was not declared"):
            with module.endpoint_material_transaction([SimpleNamespace(pk=2)]):
                pass

    declaration.assert_called_once_with([], allow_new=False)


def test_unknown_provider_contract_fails_before_declaration(
    admission,
    monkeypatch,
) -> None:
    module, provider, events = admission
    provider.MATERIAL_TRANSACTION_CONTRACT_VERSION = 2
    declaration = Mock()
    monkeypatch.setattr(module, "_declare_context", declaration)

    with pytest.raises(module.ValidationError, match="compatible OpenBao"):
        with module.endpoint_material_transaction([]):
            pass

    declaration.assert_not_called()
    assert events == []


def test_missing_provider_transaction_module_has_actionable_error(
    admission,
    monkeypatch,
) -> None:
    module, _, _ = admission
    monkeypatch.setitem(
        sys.modules,
        "netbox_openbao.material_transactions",
        ModuleType("netbox_openbao.material_transactions"),
    )

    with pytest.raises(module.ValidationError) as caught:
        with module.endpoint_material_transaction([]):
            pass

    message = str(caught.value)
    assert "netbox-openbao 0.1.0 or newer" in message
    assert "contract version 1" in message
