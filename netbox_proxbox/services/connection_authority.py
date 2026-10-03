"""Independent connection approval before stored credential transmission."""

from __future__ import annotations

import hashlib
import hmac
import json
from contextvars import ContextVar
from collections.abc import Callable


BINDING_FIELD = "approved_connection_target_fingerprint"
_UNAPPROVED = "Connection target approval is missing or stale. Review and approve the current target before sending credentials."


class ConnectionAuthorityError(ValueError):
    """A secret-free connection approval rejection."""


def _model_name(endpoint: object) -> str:
    return getattr(
        getattr(endpoint, "_meta", None), "model_name", type(endpoint).__name__.lower()
    )


def _ip_value(endpoint: object) -> str:
    value = getattr(endpoint, "ip_address", None)
    return str(getattr(value, "address", value) or "").split("/", 1)[0].strip().lower()


def connection_target_data(endpoint: object) -> dict[str, object]:
    """Describe both the primary and fallback target, without reading material."""
    return {
        "kind": _model_name(endpoint),
        "domain": str(getattr(endpoint, "domain", "") or "")
        .strip()
        .rstrip(".")
        .lower(),
        "ip_address": _ip_value(endpoint),
        "port": int(getattr(endpoint, "port", 0) or 0),
        "verify_ssl": bool(getattr(endpoint, "verify_ssl", True)),
        "username": str(getattr(endpoint, "username", "") or "").strip(),
        "token_name": str(getattr(endpoint, "token_name", "") or "").strip(),
        "token_version": str(getattr(endpoint, "token_version", "") or ""),
    }


def connection_target_fingerprint(endpoint: object) -> str:
    """Hash the target and authentication identity; never hash or resolve secrets."""
    if _model_name(endpoint) == "fastapiendpoint":
        from .backend_key_adoption import backend_key_target_fingerprint

        return backend_key_target_fingerprint(endpoint)
    data = connection_target_data(endpoint)
    if not (data["domain"] or data["ip_address"]) or not 1 <= data["port"] <= 65535:
        raise ConnectionAuthorityError(
            "Configure a valid connection target before approval."
        )
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _live_ip_matches(endpoint: object) -> bool:
    """Detect a changed IPAddress value even when the endpoint FK is unchanged."""
    ip_id = getattr(endpoint, "ip_address_id", None)
    if ip_id is None:
        return True
    from ipam.models import IPAddress

    value = IPAddress.objects.filter(pk=ip_id).values_list("address", flat=True).first()
    return value is not None and str(value).split("/", 1)[0].lower() == _ip_value(
        endpoint
    )


def approved_connection_allows_secrets(endpoint: object) -> bool:
    """Fail closed on blank approval, draft edits, stale instances, or IP drift."""
    if _model_name(endpoint) == "fastapiendpoint":
        from .backend_key_adoption import backend_key_runtime_is_trusted

        return backend_key_runtime_is_trusted(endpoint)
    stored = getattr(endpoint, BINDING_FIELD, None)
    # Existing lightweight transport doubles do not have Django model fields.
    # Every production endpoint has the durable field and takes the strict path.
    if stored is None and not hasattr(endpoint, "_meta"):
        return True
    if not stored or not getattr(endpoint, "enabled", True):
        return False
    from django.db import DatabaseError

    try:
        current = connection_target_fingerprint(endpoint)
        if not hmac.compare_digest(str(stored), current) or not _live_ip_matches(
            endpoint
        ):
            return False
        if hasattr(endpoint, "_meta"):
            persisted = type(endpoint).objects.filter(pk=endpoint.pk).first()
            return (
                persisted is not None
                and persisted.enabled
                and hmac.compare_digest(str(getattr(persisted, BINDING_FIELD)), current)
                and hmac.compare_digest(
                    connection_target_fingerprint(persisted), current
                )
            )
        return True
    except (DatabaseError, TypeError, ValueError):
        return False


def require_approved_connection(endpoint: object) -> None:
    """Reject before any credential resolver or authenticated backend call."""
    if not approved_connection_allows_secrets(endpoint):
        raise ConnectionAuthorityError(_UNAPPROVED)


def approve_connection_target(
    endpoint: object, *, user: object, fingerprint: str
) -> None:
    """Approve only the exact reviewed persisted target within object permissions."""
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.db import transaction
    from netbox_proxbox.sensitive_data import require_sensitive_data_access

    require_sensitive_data_access(user)
    model = type(endpoint)
    if not user.has_perm(f"netbox_proxbox.change_{endpoint._meta.model_name}"):
        raise PermissionDenied(
            "Endpoint change permission is required for connection approval."
        )
    using = endpoint._state.db or "default"
    with transaction.atomic(using=using):
        current = (
            model.objects.using(using)
            .restrict(user, "view")
            .restrict(user, "change")
            .select_for_update()
            .filter(pk=endpoint.pk)
            .first()
        )
        if current is None:
            raise PermissionDenied(
                "Connection approval is not authorized for this endpoint."
            )
        expected = connection_target_fingerprint(current)
        if (
            not isinstance(fingerprint, str)
            or not fingerprint.isascii()
            or not hmac.compare_digest(fingerprint, expected)
        ):
            raise ValidationError(
                "The reviewed connection target changed. Read its current fingerprint and review it again."
            )
        current.snapshot()
        setattr(current, BINDING_FIELD, expected)
        # A normal save retains NetBox's changelog and existing provider guards.
        permit = _APPROVAL_WRITE.set((current, expected))
        try:
            current.save(update_fields=[BINDING_FIELD])
        finally:
            _APPROVAL_WRITE.reset(permit)
        setattr(endpoint, BINDING_FIELD, expected)


def require_backend_target_edit_authority(endpoint: object) -> None:
    """Keep ordinary FastAPI edits from reusing a stored key at a new target."""
    from django.core.exceptions import PermissionDenied
    from netbox_proxbox.sensitive_data import require_sensitive_data_access

    if endpoint.pk is None or not endpoint.enabled:
        return
    previous = type(endpoint).objects.filter(pk=endpoint.pk).first()
    if previous is None:
        return
    target = connection_target_fingerprint(endpoint)
    if connection_target_fingerprint(previous) == target and hmac.compare_digest(
        str(previous.backend_key_target_fingerprint or ""), target
    ):
        return
    from netbox.context import current_request

    request = current_request.get()
    actor = getattr(request, "user", None)
    if actor is None:
        from netbox_proxbox.integrations.openbao_single_transaction import (
            current_single_secret_actor,
        )

        actor = current_single_secret_actor()
    require_sensitive_data_access(actor)
    if not actor.has_perm("netbox_proxbox.change_fastapiendpoint"):
        raise PermissionDenied(
            "Backend change permission is required to approve a new target."
        )
    if (
        not type(endpoint)
        .objects.restrict(actor, "view")
        .restrict(actor, "change")
        .filter(pk=endpoint.pk)
        .exists()
    ):
        raise PermissionDenied(
            "Backend target approval is not authorized for this endpoint."
        )


# An exact, in-process approval write permit. It is never accepted from model
# fields, request data, or a serializer and cannot authorize another instance.
_APPROVAL_WRITE: ContextVar[tuple[object, str] | None] = ContextVar(
    "proxbox_connection_approval_write", default=None
)


def _approval_write_is_exact(endpoint: object) -> bool:
    permit = _APPROVAL_WRITE.get()
    return (
        permit is not None
        and permit[0] is endpoint
        and hmac.compare_digest(permit[1], str(getattr(endpoint, BINDING_FIELD)))
        and hmac.compare_digest(permit[1], connection_target_fingerprint(endpoint))
    )


def save_bound_endpoint(
    endpoint: object, persist: Callable[..., object], *args: object, **kwargs: object
) -> object:
    """Prevent draft and stale saves from forging or resurrecting approval."""
    from django.core.exceptions import ValidationError
    from django.db import router, transaction

    using = kwargs.get("using") or router.db_for_write(
        type(endpoint), instance=endpoint
    )
    with transaction.atomic(using=using):
        current = (
            type(endpoint)
            .objects.using(using)
            .select_for_update()
            .filter(pk=endpoint.pk)
            .first()
            if endpoint.pk is not None
            else None
        )
        if _approval_write_is_exact(endpoint):
            if set(kwargs.get("update_fields") or ()) != {BINDING_FIELD}:
                raise ValidationError(
                    "An approval write may update only the approval field."
                )
            if current is None or connection_target_fingerprint(
                current
            ) != connection_target_fingerprint(endpoint):
                raise ValidationError(
                    "The reviewed connection target changed before approval was saved."
                )
        else:
            update_fields = kwargs.get("update_fields")
            if update_fields is not None and BINDING_FIELD in update_fields:
                raise ValidationError(
                    "Connection approval requires the protected approval action."
                )
            # Full model saves otherwise write editable=False fields too. Read
            # under the row lock so a stale instance cannot revive a revoked stamp.
            setattr(endpoint, BINDING_FIELD, getattr(current, BINDING_FIELD, ""))
        return persist(*args, **kwargs)
