"""Adversarial connection approval and credential transmission contracts."""

from __future__ import annotations

from contextlib import nullcontext
from copy import copy
import ast
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_sensitive_data_policy import (
    policy,
)  # The real grant policy with storage-only stubs.
from tests.test_backend_sync_placement import _load_backend_sync_module
from tests.test_backend_key_adoption import adoption_modules

ROOT = Path(__file__).resolve().parents[1]

_DOC_CIDR_200 = ".".join(("192", "0", "2", "200")) + "/32"
_DOC_CIDR_4 = ".".join(("192", "0", "2", "4")) + "/32"


@pytest.fixture
def authority(monkeypatch, policy) -> tuple[object, object]:  # noqa: F811 - shared pytest fixture
    monkeypatch.setitem(sys.modules, "netbox_proxbox.sensitive_data", policy[0])
    name = "netbox_proxbox.services.connection_authority"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "netbox_proxbox/services/connection_authority.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    sys.modules["django.core.exceptions"].ValidationError = type(
        "ValidationError", (Exception,), {}
    )
    sys.modules["django.db"].router = SimpleNamespace(
        db_for_write=lambda *args, **kwargs: "default"
    )
    sys.modules["django.db"].transaction = SimpleNamespace(
        atomic=lambda **kwargs: nullcontext()
    )
    return module, policy[1]


def _endpoint(authority, kind="proxmoxendpoint") -> tuple[object, object, object]:
    module, _ = authority
    model = type(
        "ProxmoxEndpoint" if kind == "proxmoxendpoint" else "NetBoxEndpoint", (), {}
    )
    endpoint = model()
    endpoint._meta = SimpleNamespace(model_name=kind)
    endpoint._state = SimpleNamespace(db="default")
    endpoint.pk = 11
    endpoint.enabled = True
    endpoint.domain = "pve.example.test"
    endpoint.ip_address = None
    endpoint.ip_address_id = None
    endpoint.port = 8006
    endpoint.verify_ssl = True
    endpoint.username = "root@pam"
    endpoint.token_name = "api"
    endpoint.token_version = "v2"
    endpoint.approved_connection_target_fingerprint = (
        module.connection_target_fingerprint(endpoint)
    )
    endpoint.snapshot = Mock()
    endpoint.save = Mock()
    persisted = copy(endpoint)
    manager = Mock()
    manager.filter.return_value.first.return_value = persisted
    manager.using.return_value = manager
    manager.restrict.return_value = manager
    manager.select_for_update.return_value = manager
    manager.get.return_value = persisted
    model.objects = manager
    return endpoint, persisted, manager


def _actor(**overrides) -> SimpleNamespace:
    fields = dict(
        pk=17,
        is_active=True,
        is_authenticated=True,
        is_superuser=False,
        has_perm=lambda permission: True,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.mark.parametrize("kind", ["proxmoxendpoint", "netboxendpoint"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("domain", "attacker.example.test"),
        ("ip_address", _DOC_CIDR_200),
        ("port", 8443),
        ("verify_ssl", False),
        ("username", "other@pam"),
        ("token_name", "other-token"),
        ("token_version", "v1"),
    ],
)
def test_draft_target_edits_invalidate_approval(authority, kind, field, value) -> None:
    module, _ = authority
    endpoint, _, _ = _endpoint(authority, kind)
    assert module.approved_connection_allows_secrets(endpoint)
    setattr(endpoint, field, value)
    assert not module.approved_connection_allows_secrets(endpoint)
    with pytest.raises(module.ConnectionAuthorityError, match="missing or stale"):
        module.require_approved_connection(endpoint)


@pytest.mark.parametrize("approval", ["", None, "malformed", "f" * 64])
def test_blank_unapproved_and_forged_bindings_fail_closed(authority, approval) -> None:
    module, _ = authority
    endpoint, _, _ = _endpoint(authority)
    endpoint.approved_connection_target_fingerprint = approval
    assert not module.approved_connection_allows_secrets(endpoint)


def test_target_metadata_edits_preserve_approval(authority) -> None:
    module, _ = authority
    endpoint, _, _ = _endpoint(authority)
    endpoint.name = "A new display name"
    endpoint.description = "Inventory annotation"
    assert module.approved_connection_allows_secrets(endpoint)


def test_persisted_draft_change_blocks_a_stale_loaded_instance(authority) -> None:
    module, _ = authority
    endpoint, persisted, _ = _endpoint(authority)
    persisted.domain = "attacker.example.test"
    assert not module.approved_connection_allows_secrets(endpoint)


def test_persisted_approval_revocation_blocks_loaded_instance(authority) -> None:
    module, _ = authority
    endpoint, persisted, _ = _endpoint(authority)
    persisted.approved_connection_target_fingerprint = ""
    assert not module.approved_connection_allows_secrets(endpoint)


def test_in_place_ip_change_blocks_cached_related_object(
    authority, monkeypatch
) -> None:
    module, _ = authority
    endpoint, persisted, _ = _endpoint(authority)
    endpoint.ip_address = SimpleNamespace(pk=9, address=_DOC_CIDR_4)
    endpoint.ip_address_id = 9
    endpoint.approved_connection_target_fingerprint = (
        module.connection_target_fingerprint(endpoint)
    )
    persisted.ip_address = endpoint.ip_address
    persisted.ip_address_id = 9
    persisted.approved_connection_target_fingerprint = (
        endpoint.approved_connection_target_fingerprint
    )
    ipam = ModuleType("ipam.models")
    ipam.IPAddress = SimpleNamespace(objects=Mock())
    ipam.IPAddress.objects.filter.return_value.values_list.return_value.first.return_value = _DOC_CIDR_200
    monkeypatch.setitem(sys.modules, "ipam.models", ipam)
    assert not module.approved_connection_allows_secrets(endpoint)


def test_disabled_endpoint_never_has_transmission_authority(authority) -> None:
    module, _ = authority
    endpoint, _, _ = _endpoint(authority)
    endpoint.enabled = False
    assert not module.approved_connection_allows_secrets(endpoint)


@pytest.mark.parametrize("kind", ["proxmoxendpoint", "netboxendpoint"])
def test_existing_backend_row_cannot_override_missing_approval(
    authority, monkeypatch, kind
) -> None:
    module, _ = authority
    endpoint, persisted, _ = _endpoint(authority, kind)
    endpoint.approved_connection_target_fingerprint = ""
    persisted.approved_connection_target_fingerprint = ""
    backend = _load_backend_sync_module(monkeypatch)
    currency_check = Mock(
        side_effect=AssertionError("unapproved target must not inspect secret currency")
    )
    monkeypatch.setattr(backend, "_proxmox_row_is_current", currency_check)
    monkeypatch.setattr(backend, "_netbox_row_is_current", currency_check)
    predicate = (
        backend.backend_holds_proxmox_endpoint
        if kind == "proxmoxendpoint"
        else backend.backend_holds_netbox_endpoint
    )
    assert not predicate(endpoint, [{"name": "previously approved row"}])
    currency_check.assert_not_called()


def test_unavailable_binding_storage_fails_closed(authority) -> None:
    module, _ = authority
    endpoint, _, manager = _endpoint(authority)
    manager.filter.side_effect = sys.modules["django.db"].DatabaseError("unavailable")
    assert not module.approved_connection_allows_secrets(endpoint)


def test_only_explicit_review_can_approve_current_persisted_target(authority) -> None:
    module, grants = authority
    grants.filter.return_value.exists.return_value = True
    endpoint, persisted, manager = _endpoint(authority)
    endpoint.domain = persisted.domain = "new.example.test"
    fingerprint = module.connection_target_fingerprint(persisted)
    assert not module.approved_connection_allows_secrets(endpoint)
    actor = _actor()
    module.approve_connection_target(endpoint, user=actor, fingerprint=fingerprint)
    assert module.approved_connection_allows_secrets(endpoint)
    assert manager.restrict.call_args_list[0].args == (actor, "view")
    assert manager.restrict.call_args_list[1].args == (actor, "change")
    persisted.save.assert_called_once_with(update_fields=[module.BINDING_FIELD])


def test_stale_review_cannot_approve_new_target(authority) -> None:
    module, grants = authority
    grants.filter.return_value.exists.return_value = True
    endpoint, persisted, _ = _endpoint(authority)
    reviewed = module.connection_target_fingerprint(endpoint)
    persisted.domain = "changed-after-review.example.test"
    with pytest.raises(
        sys.modules["django.core.exceptions"].ValidationError, match="changed"
    ):
        module.approve_connection_target(endpoint, user=_actor(), fingerprint=reviewed)
    persisted.save.assert_not_called()


def test_ordinary_change_permission_cannot_approve_without_sensitive_grant(
    authority,
) -> None:
    module, _ = authority
    endpoint, persisted, _ = _endpoint(authority)
    with pytest.raises(sys.modules["django.core.exceptions"].PermissionDenied):
        module.approve_connection_target(
            endpoint,
            user=_actor(),
            fingerprint=module.connection_target_fingerprint(endpoint),
        )
    persisted.save.assert_not_called()


def test_sensitive_grant_does_not_supply_endpoint_change_permission(authority) -> None:
    module, grants = authority
    grants.filter.return_value.exists.return_value = True
    endpoint, persisted, _ = _endpoint(authority)
    with pytest.raises(sys.modules["django.core.exceptions"].PermissionDenied):
        module.approve_connection_target(
            endpoint,
            user=_actor(has_perm=lambda permission: False),
            fingerprint=module.connection_target_fingerprint(endpoint),
        )
    persisted.save.assert_not_called()


@pytest.mark.parametrize("kind", ["proxmoxendpoint", "netboxendpoint"])
def test_backend_payload_denies_before_secret_read_or_network(
    authority, monkeypatch, kind
) -> None:
    module, _ = authority
    endpoint, _, _ = _endpoint(authority, kind)
    endpoint.domain = "attacker.example.test"
    backend = _load_backend_sync_module(monkeypatch)
    secret_resolver = Mock(
        side_effect=AssertionError("must not resolve stored secrets")
    )
    monkeypatch.setattr(
        sys.modules["netbox_proxbox.integrations.openbao"],
        "resolve_endpoint_api_credentials",
        secret_resolver,
    )
    model = type(endpoint)
    model.effective_token_version = property(lambda self: secret_resolver())
    model.effective_token_value = property(lambda self: secret_resolver())
    builder = (
        backend._proxmox_backend_payload
        if kind == "proxmoxendpoint"
        else backend._netbox_endpoint_backend_payload
    )
    with pytest.raises(module.ConnectionAuthorityError):
        builder(endpoint)
    network = Mock(side_effect=AssertionError("must not contact backend"))
    monkeypatch.setattr(backend.requests, "get", network)
    push = (
        backend.sync_proxmox_endpoint_to_backend
        if kind == "proxmoxendpoint"
        else backend.sync_netbox_endpoint_to_backend
    )
    assert push(endpoint, base_url="https://backend.example.test") == (
        False,
        "Connection target approval is missing or stale.",
        None,
    )
    secret_resolver.assert_not_called()
    network.assert_not_called()


def test_migration_has_no_automatic_approval_backfill() -> None:
    source = (ROOT / "netbox_proxbox/migrations/0104_security_hardening.py").read_text()
    assert 'default=""' in source
    assert "editable=False" in source
    # The release migration's only data step is the settings-read grant; it
    # must never write an approval fingerprint.
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            segment = ast.get_source_segment(source, node) or ""
            assert "approved_connection_target" not in segment


@pytest.mark.parametrize("value", [None, "", "☃" * 64, [], {"fingerprint": "fake"}])
def test_malformed_review_does_not_approve(authority, value) -> None:
    module, grants = authority
    grants.filter.return_value.exists.return_value = True
    endpoint, persisted, _ = _endpoint(authority)
    with pytest.raises(sys.modules["django.core.exceptions"].ValidationError):
        module.approve_connection_target(endpoint, user=_actor(), fingerprint=value)
    persisted.save.assert_not_called()


def test_sensitive_grant_does_not_bypass_object_restrictions(authority) -> None:
    module, grants = authority
    grants.filter.return_value.exists.return_value = True
    endpoint, persisted, manager = _endpoint(authority)
    denied = sys.modules["django.core.exceptions"].PermissionDenied("object denied")
    manager.restrict.side_effect = denied
    with pytest.raises(type(denied), match="object denied"):
        module.approve_connection_target(
            endpoint,
            user=_actor(),
            fingerprint=module.connection_target_fingerprint(endpoint),
        )
    persisted.save.assert_not_called()


def test_hidden_approval_target_returns_permission_denial(authority) -> None:
    module, grants = authority
    grants.filter.return_value.exists.return_value = True
    endpoint, persisted, manager = _endpoint(authority)
    manager.filter.return_value.first.return_value = None
    with pytest.raises(
        sys.modules["django.core.exceptions"].PermissionDenied,
        match="not authorized",
    ):
        module.approve_connection_target(
            endpoint,
            user=_actor(),
            fingerprint=module.connection_target_fingerprint(endpoint),
        )
    persisted.save.assert_not_called()


@pytest.mark.parametrize("kind", ["proxmoxendpoint", "netboxendpoint"])
def test_approval_revoked_during_backend_listing_blocks_secret_push(
    authority, monkeypatch, kind
) -> None:
    module, _ = authority
    endpoint, persisted, _ = _endpoint(authority, kind)
    endpoint.name = "endpoint"
    endpoint.password = "synthetic-password"
    endpoint.token_value = "synthetic-token"
    endpoint.effective_connection_tuning = lambda: {
        "timeout": 5,
        "max_retries": 0,
        "retry_backoff": 0.5,
    }
    endpoint.effective_token_version = "v2"
    endpoint.token_secret = "synthetic-secret"
    endpoint.token_key = "key"
    backend = _load_backend_sync_module(monkeypatch)

    def revoke(*args, **kwargs) -> None:
        persisted.approved_connection_target_fingerprint = ""
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(backend.requests, "get", revoke)
    monkeypatch.setattr(
        backend, "parse_requests_response_json", lambda *args, **kwargs: ([], None)
    )
    put = Mock(side_effect=AssertionError("revoked material must not be transmitted"))
    post = Mock(side_effect=AssertionError("revoked material must not be transmitted"))
    monkeypatch.setattr(backend.requests, "put", put)
    monkeypatch.setattr(backend.requests, "post", post)
    push = (
        backend.sync_proxmox_endpoint_to_backend
        if kind == "proxmoxendpoint"
        else backend.sync_netbox_endpoint_to_backend
    )
    assert push(endpoint, base_url="https://backend.example.test") == (
        False,
        "Connection target approval is missing or stale.",
        None,
    )
    put.assert_not_called()
    post.assert_not_called()


@pytest.fixture
def backend_draft(
    authority,
    adoption_modules,  # noqa: F811 - shared pytest fixture
    monkeypatch,
) -> tuple[object, object, object, object]:
    from tests.test_backend_key_adoption import _endpoint as backend_endpoint
    from contextvars import ContextVar

    module, grants = authority
    adoption, _ = adoption_modules
    model = type("FastAPIEndpoint", (), {})
    endpoint = model()
    endpoint.__dict__.update(backend_endpoint().__dict__)
    endpoint._meta = SimpleNamespace(model_name="fastapiendpoint")
    endpoint.backend_key_target_fingerprint = adoption.backend_key_target_fingerprint(
        endpoint
    )
    previous = copy(endpoint)
    manager = Mock()
    manager.filter.return_value.first.return_value = previous
    manager.restrict.return_value = manager
    manager.filter.return_value.exists.return_value = True
    model.objects = manager
    context = ModuleType("netbox.context")
    context.current_request = ContextVar("authority_test_request", default=None)
    monkeypatch.setitem(sys.modules, "netbox.context", context)
    context.current_request.set(SimpleNamespace(user=_actor()))
    return endpoint, previous, manager, context


@pytest.mark.parametrize(
    "field,value",
    [
        ("domain", "attacker.example.test"),
        ("verify_ssl", True),
        ("ip_address", _DOC_CIDR_200),
        ("websocket_domain", "attacker.example.test"),
    ],
)
def test_backend_draft_cannot_reauthenticate_stored_key_without_sensitive_authority(
    authority, backend_draft, field, value
) -> None:
    module, _ = authority
    endpoint, _, _, _ = backend_draft
    if field == "websocket_domain":
        endpoint.use_websocket = True
    setattr(endpoint, field, value)
    with pytest.raises(sys.modules["django.core.exceptions"].PermissionDenied):
        module.require_backend_target_edit_authority(endpoint)


def test_backend_ip_drift_needs_approval_even_when_both_instances_see_new_ip(
    authority, backend_draft
) -> None:
    module, _ = authority
    endpoint, previous, _, _ = backend_draft
    endpoint.ip_address = previous.ip_address = _DOC_CIDR_200
    with pytest.raises(sys.modules["django.core.exceptions"].PermissionDenied):
        module.require_backend_target_edit_authority(endpoint)


def test_backend_target_edit_authority_is_independent_from_authentication_proof(
    authority, backend_draft
) -> None:
    module, grants = authority
    endpoint, _, manager, _ = backend_draft
    endpoint.domain = "new.backend.example.test"
    grants.filter.return_value.exists.return_value = True
    module.require_backend_target_edit_authority(endpoint)
    assert [call.args[1] for call in manager.restrict.call_args_list] == [
        "view",
        "change",
    ]
    assert not module.approved_connection_allows_secrets(endpoint)


def test_disabled_backend_target_edits_remain_drafts(authority, backend_draft) -> None:
    module, _ = authority
    endpoint, _, _, _ = backend_draft
    endpoint.enabled = False
    endpoint.domain = "draft.backend.example.test"
    module.require_backend_target_edit_authority(endpoint)
    assert not module.approved_connection_allows_secrets(endpoint)


def test_backend_object_denial_is_not_overridden_by_sensitive_grant(
    authority, backend_draft
) -> None:
    module, grants = authority
    endpoint, _, manager, _ = backend_draft
    endpoint.domain = "new.backend.example.test"
    grants.filter.return_value.exists.return_value = True
    manager.filter.return_value.exists.return_value = False
    with pytest.raises(sys.modules["django.core.exceptions"].PermissionDenied):
        module.require_backend_target_edit_authority(endpoint)


def test_full_save_cannot_restore_a_revoked_approval(authority) -> None:
    module, _ = authority
    endpoint, persisted, _ = _endpoint(authority)
    persisted.approved_connection_target_fingerprint = ""
    persist = Mock()
    module.save_bound_endpoint(endpoint, persist)
    persist.assert_called_once_with()
    assert endpoint.approved_connection_target_fingerprint == ""


def test_full_save_cannot_forge_approval_for_a_draft_target(authority) -> None:
    module, _ = authority
    endpoint, persisted, _ = _endpoint(authority)
    endpoint.domain = "attacker.example.test"
    endpoint.approved_connection_target_fingerprint = (
        module.connection_target_fingerprint(endpoint)
    )
    module.save_bound_endpoint(endpoint, Mock())
    assert (
        endpoint.approved_connection_target_fingerprint
        == persisted.approved_connection_target_fingerprint
    )
    assert not module.approved_connection_allows_secrets(endpoint)


def test_partial_save_cannot_write_internal_approval(authority) -> None:
    module, _ = authority
    endpoint, _, _ = _endpoint(authority)
    persist = Mock()
    with pytest.raises(
        sys.modules["django.core.exceptions"].ValidationError,
        match="protected approval",
    ):
        module.save_bound_endpoint(
            endpoint, persist, update_fields=[module.BINDING_FIELD]
        )
    persist.assert_not_called()


def test_new_row_cannot_arrive_preapproved(authority) -> None:
    module, _ = authority
    endpoint, _, _ = _endpoint(authority)
    endpoint.pk = None
    module.save_bound_endpoint(endpoint, Mock())
    assert endpoint.approved_connection_target_fingerprint == ""


def test_approval_write_permit_cannot_authorize_another_instance(authority) -> None:
    module, _ = authority
    endpoint, persisted, _ = _endpoint(authority)
    permit = module._APPROVAL_WRITE.set(
        (persisted, module.connection_target_fingerprint(persisted))
    )
    try:
        with pytest.raises(
            sys.modules["django.core.exceptions"].ValidationError,
            match="protected approval",
        ):
            module.save_bound_endpoint(
                endpoint, Mock(), update_fields=[module.BINDING_FIELD]
            )
    finally:
        module._APPROVAL_WRITE.reset(permit)


def test_exact_approval_save_preserves_the_approved_stamp(authority) -> None:
    module, _ = authority
    endpoint, _, _ = _endpoint(authority)
    permit = module._APPROVAL_WRITE.set(
        (endpoint, module.connection_target_fingerprint(endpoint))
    )
    persist = Mock()
    try:
        module.save_bound_endpoint(
            endpoint, persist, update_fields=[module.BINDING_FIELD]
        )
    finally:
        module._APPROVAL_WRITE.reset(permit)
    persist.assert_called_once_with(update_fields=[module.BINDING_FIELD])


def test_exact_approval_permit_cannot_widen_field_writes(authority) -> None:
    module, _ = authority
    endpoint, _, _ = _endpoint(authority)
    permit = module._APPROVAL_WRITE.set(
        (endpoint, module.connection_target_fingerprint(endpoint))
    )
    persist = Mock()
    try:
        with pytest.raises(
            sys.modules["django.core.exceptions"].ValidationError,
            match="only the approval",
        ):
            module.save_bound_endpoint(
                endpoint, persist, update_fields=[module.BINDING_FIELD, "domain"]
            )
    finally:
        module._APPROVAL_WRITE.reset(permit)
    persist.assert_not_called()


def test_approval_permit_refuses_target_drift_under_the_save_lock(authority) -> None:
    module, _ = authority
    endpoint, persisted, _ = _endpoint(authority)
    permit = module._APPROVAL_WRITE.set(
        (endpoint, module.connection_target_fingerprint(endpoint))
    )
    persisted.domain = "raced.example.test"
    persist = Mock()
    try:
        with pytest.raises(
            sys.modules["django.core.exceptions"].ValidationError,
            match="changed before approval",
        ):
            module.save_bound_endpoint(
                endpoint, persist, update_fields=[module.BINDING_FIELD]
            )
    finally:
        module._APPROVAL_WRITE.reset(permit)
    persist.assert_not_called()
