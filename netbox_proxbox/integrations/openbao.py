"""Optional integration with the **netbox-openbao** plugin.

When enabled, Proxmox API tokens, endpoint passwords, and SSH secrets are stored
in OpenBao through netbox-openbao's audited write path instead of local Fernet
columns. The dependency is *soft*: nothing here imports netbox-openbao at module
load time, and callers degrade cleanly when the plugin is absent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.views.decorators.debug import sensitive_variables

if TYPE_CHECKING:
    from netbox_proxbox.models import (
        NodeSSHCredential,
        ProxmoxEndpoint,
        ProxboxPluginSettings,
    )

from netbox_proxbox.choices import CredentialStorageBackendChoices

logger = logging.getLogger("netbox_proxbox.integrations.openbao")

__all__ = (
    "CredentialStorageBackendChoices",
    "clear_endpoint_openbao_credential",
    "credential_assignment_lookup",
    "credential_assignment_readiness",
    "effective_credential_storage_backend",
    "endpoint_uses_openbao_storage",
    "is_netbox_openbao_installed",
    "node_uses_openbao_storage",
    "node_openbao_assignment_lookup",
    "node_openbao_assignment_readiness",
    "owner_uses_openbao_storage",
    "openbao_prerequisites_met",
    "openbao_prerequisites_errors",
    "register_openbao_assignable_models",
    "reveal_credential_material",
    "resolve_endpoint_api_credentials",
    "resolve_endpoint_api_secret",
    "resolve_endpoint_password",
    "resolve_endpoint_token_value",
    "resolve_endpoint_ssh_password",
    "resolve_endpoint_ssh_private_key",
    "resolve_node_ssh_password",
    "resolve_node_ssh_private_key",
    "store_endpoint_api_token",
    "store_endpoint_password",
    "store_endpoint_ssh_keypair",
    "store_endpoint_ssh_password",
    "store_node_ssh_keypair",
    "store_node_ssh_password",
    "validate_openbao_storage_available",
    "validate_write_mode_openbao_requirements",
)


def owner_uses_openbao_storage(owner: Any) -> bool:
    """Return whether a typed single-secret owner uses OpenBao."""
    from .openbao_single import owner_uses_openbao_storage as selected

    return selected(owner)


def credential_assignment_lookup(owner: Any) -> dict[str, str] | None:
    """Return vendor-neutral selectors for a single-secret owner."""
    from .openbao_single import credential_assignment_lookup as lookup

    return lookup(owner)


def credential_assignment_readiness(owner: Any) -> tuple[bool, str]:
    """Return secret-free assignment readiness for a single-secret owner."""
    from .openbao_single import credential_assignment_readiness as readiness

    return readiness(owner)


def is_netbox_openbao_installed() -> bool:
    """Return ``True`` when netbox-openbao is enabled in this NetBox."""
    try:
        from django.conf import settings
    except Exception:  # noqa: BLE001 - Django not ready
        return False
    return "netbox_openbao" in (getattr(settings, "PLUGINS", []) or [])


def register_openbao_assignable_models() -> None:
    """Register Proxbox object types when the optional companion supports it."""
    if not is_netbox_openbao_installed():
        return
    try:
        from netbox_openbao.registry import register_assignable_models
    except ImportError:
        logger.warning(
            "Proxbox credential assignment registration requires netbox-openbao "
            "0.1.0 or newer. Configure the netbox-openbao assignable_models "
            "allowlist until the companion is upgraded."
        )
        return
    register_assignable_models(
        "netbox_proxbox.proxmoxendpoint",
        "netbox_proxbox.fastapiendpoint",
        "netbox_proxbox.pbsendpoint",
        "netbox_proxbox.pdmendpoint",
        "netbox_proxbox.firecrackerhost",
    )


def _plugin_settings() -> ProxboxPluginSettings | None:
    from netbox_proxbox.models import ProxboxPluginSettings

    return ProxboxPluginSettings.objects.first()


def effective_credential_storage_backend(
    endpoint: ProxmoxEndpoint | None = None,
    *,
    override: str | None = None,
) -> str:
    """Resolve the storage backend for *endpoint* or the plugin default."""
    if override:
        return override
    if endpoint is not None:
        endpoint_backend = getattr(endpoint, "credential_storage_backend", "") or ""
        if endpoint_backend:
            return endpoint_backend
    settings_row = _plugin_settings()
    if settings_row is not None:
        backend = getattr(settings_row, "credential_storage_backend", "") or ""
        if backend:
            return backend
    if is_netbox_openbao_installed():
        return CredentialStorageBackendChoices.OPENBAO
    return CredentialStorageBackendChoices.LEGACY_ENCRYPTED


def endpoint_uses_openbao_storage(endpoint: ProxmoxEndpoint) -> bool:
    return (
        effective_credential_storage_backend(endpoint)
        == CredentialStorageBackendChoices.OPENBAO
    )


def node_uses_openbao_storage(credential: NodeSSHCredential) -> bool:
    """Return whether a node credential follows its endpoint's OpenBao policy."""
    node = getattr(credential, "node", None)
    endpoint = getattr(node, "endpoint", None)
    return (
        effective_credential_storage_backend(endpoint)
        == CredentialStorageBackendChoices.OPENBAO
    )


def node_openbao_assignment_lookup(
    credential: NodeSSHCredential,
) -> dict[str, str] | None:
    """Return secret-free selectors accepted by netbox-openbao-ansible."""
    node = getattr(credential, "node", None)
    device_id = getattr(node, "netbox_device_id", None)
    if device_id is None:
        return None
    return {
        "assigned_object_type": "dcim.device",
        "assigned_object_id": str(device_id),
        "purpose": "login",
    }


def node_openbao_assignment_readiness(
    credential: NodeSSHCredential,
) -> tuple[bool, str]:
    """Check selected assignment metadata without revealing provider material."""
    if not node_uses_openbao_storage(credential):
        return True, "Legacy storage does not require an OpenBao assignment."
    lookup = node_openbao_assignment_lookup(credential)
    if lookup is None:
        return False, "The Proxmox node is not linked to a NetBox device."
    from .openbao_node_assignments import _selected_reference

    reference = getattr(credential, _selected_reference(credential), None)
    if reference is None:
        return False, "The selected OpenBao node credential is not configured."
    try:
        from netbox_openbao.models import CredentialAssignment
    except ImportError:
        return False, "netbox-openbao is unavailable; restore it before use."
    matches = CredentialAssignment.objects.filter(
        credential__uuid=reference,
        assigned_object_type__app_label="dcim",
        assigned_object_type__model="device",
        assigned_object_id=int(lookup["assigned_object_id"]),
        purpose="login",
        is_primary=True,
        enabled=True,
    ).count()
    if matches != 1:
        return False, "The selected OpenBao node credential assignment is not ready."
    return True, "The selected OpenBao node credential assignment is ready."


def openbao_prerequisites_met() -> bool:
    return not openbao_prerequisites_errors()


def openbao_prerequisites_errors() -> list[str]:
    """Return human-readable blockers when OpenBao storage cannot be used."""
    from netbox_proxbox.services.openbao_readiness import openbao_storage_readiness

    return [_(message) for message in openbao_storage_readiness().errors]


def validate_openbao_storage_available(
    endpoint: ProxmoxEndpoint | None = None,
    *,
    storage_backend: str | None = None,
) -> None:
    """Fail closed when OpenBao storage is selected but prerequisites are missing."""
    backend = effective_credential_storage_backend(endpoint, override=storage_backend)
    if backend != CredentialStorageBackendChoices.OPENBAO:
        return
    errors = openbao_prerequisites_errors()
    if errors:
        raise ValidationError(errors[0])


def validate_write_mode_openbao_requirements(
    endpoint: ProxmoxEndpoint | None,
    *,
    allow_writes: bool,
    storage_backend: str | None = None,
) -> None:
    """Fail closed when Write mode needs OpenBao but prerequisites are missing."""
    backend = effective_credential_storage_backend(endpoint, override=storage_backend)
    if not allow_writes or backend != CredentialStorageBackendChoices.OPENBAO:
        return
    try:
        validate_openbao_storage_available(endpoint, storage_backend=backend)
    except ValidationError as exc:
        message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        raise ValidationError({"allow_writes": message}) from exc


def _openbao_actor(user: Any | None = None) -> Any:
    """Return the NetBox user that may read or write OpenBao material."""
    if user is not None and getattr(user, "is_authenticated", False):
        return user

    settings_row = _plugin_settings()
    username = (getattr(settings_row, "openbao_service_username", "") or "").strip()
    if not username:
        raise ValidationError(
            _(
                "Configure OpenBao service username in Proxbox plugin settings "
                "before automated OpenBao credential access."
            )
        )

    from django.contrib.auth import get_user_model

    actor = get_user_model().objects.filter(username=username, is_active=True).first()
    if actor is None:
        raise ValidationError(
            _(
                "Configured OpenBao service username does not match an active "
                "NetBox user."
            )
        )
    return actor


def _credential_for_uuid(credential_uuid: object | None) -> Any | None:
    if not credential_uuid or not is_netbox_openbao_installed():
        return None
    from netbox_openbao.models import Credential

    return Credential.objects.filter(uuid=credential_uuid).first()


def clear_endpoint_openbao_credential(
    endpoint: ProxmoxEndpoint,
    field_name: str,
    *,
    user: Any | None = None,
    request: Any | None = None,
) -> None:
    """Queue an owner-only unlink; shared credential material remains intact."""
    from .openbao_pending import queue_credential

    queue_credential(endpoint, field_name, None, user=user, request=request)
    if user is not None:
        endpoint._openbao_actor_user = user


def _default_policy() -> Any:
    from netbox_openbao.models import CredentialPolicy
    from netbox_openbao.utils import get_default_engine

    engine = get_default_engine()
    if engine is None:
        raise ValidationError(_("No default OpenBao SecretEngine is configured."))
    settings_row = _plugin_settings()
    slug = getattr(settings_row, "openbao_policy_slug", "proxbox") or "proxbox"
    policy = CredentialPolicy.objects.filter(engine=engine, slug=slug).first()
    if policy is None:
        raise ValidationError(
            _(
                "Proxbox setting openbao_policy_slug expects policy '%(slug)s' "
                "on the default OpenBao SecretEngine. Configure that exact policy; "
                "the proxbox_openbao_setup command creates it."
            )
            % {"slug": slug}
        )
    return policy


def _credential_name(endpoint: ProxmoxEndpoint, purpose: str) -> str:
    label = (getattr(endpoint, "name", "") or "Proxmox endpoint").strip()
    endpoint_id = getattr(endpoint, "pk", None)
    suffix = f" (nb:{endpoint_id})" if endpoint_id else ""
    return f"Proxbox {label}{suffix} — {purpose}"


def _upsert_endpoint_credential(
    endpoint: ProxmoxEndpoint,
    *,
    field_name: str,
    credential_type: str,
    payload: dict[str, object],
    user: Any | None,
    request: Any | None,
    purpose: str,
) -> None:
    validate_openbao_storage_available(endpoint)
    from .openbao_pending import SLOTS, queue_credential

    if SLOTS[field_name].credential_type != credential_type:
        raise ValidationError(
            "Endpoint credential type does not match its storage slot."
        )
    queue_credential(endpoint, field_name, payload, user=user, request=request)
    if user is not None:
        endpoint._openbao_actor_user = user


def store_endpoint_password(
    endpoint: ProxmoxEndpoint,
    password: str,
    *,
    user: Any | None = None,
    request: Any | None = None,
) -> None:
    _upsert_endpoint_credential(
        endpoint,
        field_name="openbao_password_credential_uuid",
        credential_type="password",
        payload={"password": password},
        user=user,
        request=request,
        purpose="Proxmox password",
    )
    endpoint.password_enc = ""


def store_endpoint_api_token(
    endpoint: ProxmoxEndpoint,
    token_value: str,
    *,
    user: Any | None = None,
    request: Any | None = None,
) -> None:
    _upsert_endpoint_credential(
        endpoint,
        field_name="openbao_token_credential_uuid",
        credential_type="api-token",
        payload={"token": token_value},
        user=user,
        request=request,
        purpose="Proxmox API token",
    )
    endpoint.token_value_enc = ""


def store_endpoint_ssh_password(
    endpoint: ProxmoxEndpoint,
    password: str,
    *,
    user: Any | None = None,
    request: Any | None = None,
) -> None:
    _upsert_endpoint_credential(
        endpoint,
        field_name="openbao_ssh_password_credential_uuid",
        credential_type="ssh-password",
        payload={"password": password},
        user=user,
        request=request,
        purpose="SSH password",
    )
    endpoint.ssh_password_enc = ""


def store_endpoint_ssh_keypair(
    endpoint: ProxmoxEndpoint,
    *,
    private_key: str,
    public_key: str = "",
    passphrase: str = "",
    user: Any | None = None,
    request: Any | None = None,
) -> None:
    payload: dict[str, object] = {"private_key": private_key}
    if public_key:
        payload["public_key"] = public_key
    if passphrase:
        payload["passphrase"] = passphrase
    _upsert_endpoint_credential(
        endpoint,
        field_name="openbao_ssh_keypair_credential_uuid",
        credential_type="ssh-keypair",
        payload=payload,
        user=user,
        request=request,
        purpose="SSH key pair",
    )
    endpoint.ssh_private_key_enc = ""


@sensitive_variables()
def store_node_ssh_password(
    credential: NodeSSHCredential,
    password: str,
    *,
    key: str,
    user: Any | None = None,
    request: Any | None = None,
) -> None:
    """Store a node password in its selected credential backend."""
    if not node_uses_openbao_storage(credential):
        _store_legacy_node_secret(credential, "password_enc", password, key=key)
        return
    validate_openbao_storage_available(_node_endpoint(credential))
    from .openbao_node_pending import queue_credential

    queue_credential(
        credential,
        "openbao_password_credential_uuid",
        {"password": password},
        user=user,
        request=request,
    )
    credential.password_enc = ""


@sensitive_variables()
def store_node_ssh_keypair(
    credential: NodeSSHCredential,
    private_key: str,
    *,
    key: str,
    public_key: str = "",
    passphrase: str = "",
    user: Any | None = None,
    request: Any | None = None,
) -> None:
    """Store node key-pair material in its selected credential backend."""
    if not node_uses_openbao_storage(credential):
        _store_legacy_node_secret(credential, "private_key_enc", private_key, key=key)
        return
    validate_openbao_storage_available(_node_endpoint(credential))
    from .openbao_node_pending import queue_credential

    payload = {"private_key": private_key}
    if public_key:
        payload["public_key"] = public_key
    if passphrase:
        payload["passphrase"] = passphrase
    queue_credential(
        credential,
        "openbao_keypair_credential_uuid",
        payload,
        user=user,
        request=request,
    )
    credential.private_key_enc = ""


def _node_endpoint(credential: NodeSSHCredential) -> ProxmoxEndpoint | None:
    node = getattr(credential, "node", None)
    return getattr(node, "endpoint", None)


@sensitive_variables()
def _store_legacy_node_secret(
    credential: NodeSSHCredential,
    field_name: str,
    plaintext: str,
    *,
    key: str,
) -> None:
    from netbox_proxbox.services.encryption_recovery import (
        mark_encrypted_fields_for_write,
    )
    from netbox_proxbox.utils import encryption as enc_helpers

    mark_encrypted_fields_for_write(credential, field_name)
    setattr(credential, field_name, enc_helpers.encrypt(plaintext, key=key))


@sensitive_variables()
def reveal_credential_material(credential: Any, *, user: Any | None = None) -> dict:
    from netbox_openbao.services import reveal_material

    actor = _openbao_actor(user)
    payload, _ttl = reveal_material(
        credential,
        actor,
        reason="netbox-proxbox credential access",
    )
    return payload if isinstance(payload, dict) else {}


def resolve_endpoint_api_credentials(endpoint: ProxmoxEndpoint) -> dict[str, str]:
    """Read API material while omitting only an unselected authentication method.

    A token name selects token authentication. Missing required material must
    still raise; an absent optional password must not break a token-only endpoint.
    Existing references are always resolved, so a stale reference is never hidden.
    """
    return {
        "password": resolve_endpoint_api_secret(endpoint, "password"),
        "token_value": resolve_endpoint_api_secret(endpoint, "token_value"),
    }


def resolve_endpoint_api_secret(
    endpoint: ProxmoxEndpoint,
    field: Literal["password", "token_value"],
    *,
    token_selected: bool | None = None,
) -> str:
    """Read stored material using the current or explicitly submitted auth mode.

    The override selects which absent counterpart is optional, never the store
    used for preservation. Existing references must still resolve successfully.
    """
    if field not in ("password", "token_value"):
        raise ValueError("Unsupported endpoint API credential field.")
    if not endpoint_uses_openbao_storage(endpoint):
        return getattr(endpoint, field) or ""
    if token_selected is None:
        token_selected = bool((endpoint.token_name or "").strip())
    return _resolve_openbao_api_secret(endpoint, field, token_selected=token_selected)


def _resolve_openbao_api_secret(
    endpoint: ProxmoxEndpoint,
    field: Literal["password", "token_value"],
    *,
    token_selected: bool,
) -> str:
    if field == "password":
        if not token_selected or _has_openbao_reference(
            endpoint, "openbao_password_credential_uuid"
        ):
            return resolve_endpoint_password(endpoint)
        return ""
    if token_selected or _has_openbao_reference(
        endpoint, "openbao_token_credential_uuid"
    ):
        return resolve_endpoint_token_value(endpoint)
    return ""


def _has_openbao_reference(endpoint: ProxmoxEndpoint, reference_field: str) -> bool:
    from .openbao_pending import pending_credential

    return bool(
        getattr(endpoint, reference_field, None)
        or pending_credential(endpoint, reference_field)
    )


def resolve_endpoint_password(
    endpoint: ProxmoxEndpoint,
    *,
    user: Any | None = None,
) -> str:
    if not endpoint_uses_openbao_storage(endpoint):
        from netbox_proxbox.models.primary_secrets import decrypt_primary_secret

        return decrypt_primary_secret(endpoint.password_enc)
    return _resolve_endpoint_secret(
        endpoint, "openbao_password_credential_uuid", "password", user=user
    )


def resolve_endpoint_token_value(
    endpoint: ProxmoxEndpoint,
    *,
    user: Any | None = None,
) -> str:
    if not endpoint_uses_openbao_storage(endpoint):
        from netbox_proxbox.models.primary_secrets import decrypt_primary_secret

        return decrypt_primary_secret(endpoint.token_value_enc)
    return _resolve_endpoint_secret(
        endpoint, "openbao_token_credential_uuid", "token", user=user
    )


def resolve_endpoint_ssh_password(
    endpoint: ProxmoxEndpoint,
    *,
    user: Any | None = None,
) -> str:
    if not endpoint_uses_openbao_storage(endpoint):
        from netbox_proxbox.models import ProxboxPluginSettings
        from netbox_proxbox.utils import encryption as enc_helpers

        key = ProxboxPluginSettings.get_solo().encryption_key or ""
        return enc_helpers.decrypt(endpoint.ssh_password_enc, key=key)
    return _resolve_endpoint_secret(
        endpoint, "openbao_ssh_password_credential_uuid", "password", user=user
    )


def resolve_endpoint_ssh_private_key(
    endpoint: ProxmoxEndpoint,
    *,
    user: Any | None = None,
) -> str:
    if not endpoint_uses_openbao_storage(endpoint):
        from netbox_proxbox.models import ProxboxPluginSettings
        from netbox_proxbox.utils import encryption as enc_helpers

        key = ProxboxPluginSettings.get_solo().encryption_key or ""
        return enc_helpers.decrypt(endpoint.ssh_private_key_enc, key=key)
    return _resolve_endpoint_secret(
        endpoint, "openbao_ssh_keypair_credential_uuid", "private_key", user=user
    )


@sensitive_variables()
def resolve_node_ssh_password(
    credential: NodeSSHCredential,
    *,
    key: str,
    user: Any | None = None,
) -> str:
    """Resolve a node password without falling back from selected OpenBao storage."""
    if not node_uses_openbao_storage(credential):
        from netbox_proxbox.utils import encryption as enc_helpers

        return enc_helpers.decrypt(credential.password_enc, key=key)
    return _resolve_node_secret(
        credential,
        "openbao_password_credential_uuid",
        "password",
        user=user,
    )


@sensitive_variables()
def resolve_node_ssh_private_key(
    credential: NodeSSHCredential,
    *,
    key: str,
    user: Any | None = None,
) -> str:
    """Resolve a node private key without a legacy or unrelated-provider fallback."""
    if not node_uses_openbao_storage(credential):
        from netbox_proxbox.utils import encryption as enc_helpers

        return enc_helpers.decrypt(credential.private_key_enc, key=key)
    return _resolve_node_secret(
        credential,
        "openbao_keypair_credential_uuid",
        "private_key",
        user=user,
    )


@sensitive_variables()
def _resolve_node_secret(
    credential: NodeSSHCredential,
    reference_field: str,
    material_field: str,
    *,
    user: Any | None = None,
) -> str:
    """Resolve required node material while hiding provider errors and secrets."""
    message = _(
        "Node SSH credential %(pk)s cannot resolve OpenBao field %(field)s. "
        "Verify the reference, plugin configuration, and access."
    ) % {"pk": getattr(credential, "pk", None), "field": reference_field}
    from .openbao_node_pending import pending_credential

    try:
        pending = pending_credential(credential, reference_field)
        if pending is not None:
            payload = pending.payload
        else:
            reference = getattr(credential, reference_field, None)
            provider_credential = _credential_for_uuid(reference)
            if provider_credential is None:
                raise ValidationError(message)
            payload = reveal_credential_material(provider_credential, user=user)
    except Exception:  # noqa: BLE001 - never expose provider errors or material
        raise ValidationError(message) from None
    value = payload.get(material_field) if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value:
        raise ValidationError(message)
    return value


def _resolve_endpoint_secret(
    endpoint: ProxmoxEndpoint,
    reference_field: str,
    material_field: str,
    *,
    user: Any | None = None,
) -> str:
    """Resolve required OpenBao material without masking failure as an empty secret."""
    message = _(
        "Endpoint %(endpoint)s (id=%(pk)s): cannot resolve OpenBao credential "
        "field %(field)s. Verify the reference, plugin configuration, and access."
    ) % {
        "endpoint": getattr(endpoint, "name", "") or "Proxmox endpoint",
        "pk": getattr(endpoint, "pk", None),
        "field": reference_field,
    }
    from .openbao_pending import pending_credential

    try:
        pending = pending_credential(endpoint, reference_field)
        if pending is not None:
            payload = pending.payload
        else:
            credential = _credential_for_uuid(getattr(endpoint, reference_field, None))
            if credential is None:
                raise ValidationError(message)
            payload = reveal_credential_material(credential, user=user)
    except Exception:  # noqa: BLE001 - never expose provider errors or material
        raise ValidationError(message) from None
    value = payload.get(material_field) if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value:
        raise ValidationError(message)
    return value
