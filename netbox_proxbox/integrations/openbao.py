"""Optional integration with the **netbox-openbao** plugin.

When enabled, Proxmox API tokens, endpoint passwords, and SSH secrets are stored
in OpenBao through netbox-openbao's audited write path instead of local Fernet
columns. The dependency is *soft*: nothing here imports netbox-openbao at module
load time, and callers degrade cleanly when the plugin is absent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from netbox_proxbox.models import ProxmoxEndpoint, ProxboxPluginSettings

from netbox_proxbox.choices import CredentialStorageBackendChoices

logger = logging.getLogger("netbox_proxbox.integrations.openbao")

__all__ = (
    "CredentialStorageBackendChoices",
    "clear_endpoint_openbao_credential",
    "effective_credential_storage_backend",
    "endpoint_uses_openbao_storage",
    "is_netbox_openbao_installed",
    "openbao_prerequisites_met",
    "openbao_prerequisites_errors",
    "reveal_credential_material",
    "resolve_endpoint_password",
    "resolve_endpoint_token_value",
    "resolve_endpoint_ssh_password",
    "resolve_endpoint_ssh_private_key",
    "store_endpoint_api_token",
    "store_endpoint_password",
    "store_endpoint_ssh_keypair",
    "store_endpoint_ssh_password",
    "validate_openbao_storage_available",
    "validate_write_mode_openbao_requirements",
)


def is_netbox_openbao_installed() -> bool:
    """Return ``True`` when netbox-openbao is enabled in this NetBox."""
    try:
        from django.conf import settings
    except Exception:  # noqa: BLE001 - Django not ready
        return False
    return "netbox_openbao" in (getattr(settings, "PLUGINS", []) or [])


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
    return CredentialStorageBackendChoices.OPENBAO


def endpoint_uses_openbao_storage(endpoint: ProxmoxEndpoint) -> bool:
    return (
        effective_credential_storage_backend(endpoint)
        == CredentialStorageBackendChoices.OPENBAO
    )


def openbao_prerequisites_met() -> bool:
    return not openbao_prerequisites_errors()


def openbao_prerequisites_errors() -> list[str]:
    """Return human-readable blockers when OpenBao storage cannot be used."""
    errors: list[str] = []
    if not is_netbox_openbao_installed():
        errors.append(_("The netbox-openbao plugin must be installed and enabled."))
        return errors

    try:
        from netbox_openbao.models import CredentialPolicy, SecretEngine
        from netbox_openbao.utils import get_default_engine
    except ImportError:
        errors.append(_("The netbox-openbao plugin is not available."))
        return errors

    engine = get_default_engine()
    if engine is None:
        errors.append(
            _(
                "Configure a default OpenBao SecretEngine in netbox-openbao "
                "before using OpenBao credential storage."
            )
        )
        return errors

    if not CredentialPolicy.objects.filter(engine=engine).exists():
        errors.append(
            _(
                "Configure at least one CredentialPolicy on the default "
                "OpenBao SecretEngine."
            )
        )
    return errors


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
    """Remove an endpoint's OpenBao credential reference and delete the inventory row."""
    credential_uuid = getattr(endpoint, field_name, None)
    setattr(endpoint, field_name, None)
    if not credential_uuid or not is_netbox_openbao_installed():
        return
    credential = _credential_for_uuid(credential_uuid)
    if credential is None:
        return
    _openbao_actor(user)
    credential.delete()


def _default_policy():
    from netbox_openbao.models import CredentialPolicy
    from netbox_openbao.utils import get_default_engine

    engine = get_default_engine()
    if engine is None:
        raise ValidationError(_("No default OpenBao SecretEngine is configured."))
    policy = CredentialPolicy.objects.filter(engine=engine).order_by("pk").first()
    if policy is None:
        raise ValidationError(
            _("No CredentialPolicy exists on the default OpenBao SecretEngine.")
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
    from netbox_openbao.models import Credential
    from netbox_openbao.services import write_material

    existing_uuid = getattr(endpoint, field_name, None)
    credential = _credential_for_uuid(existing_uuid)
    if credential is None:
        policy = _default_policy()
        credential = Credential(
            name=_credential_name(endpoint, purpose),
            credential_type=credential_type,
            policy=policy,
            engine=policy.engine,
        )
    write_material(
        credential,
        payload,
        user=_openbao_actor(user),
        request=request,
    )
    setattr(endpoint, field_name, credential.uuid)


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


def reveal_credential_material(credential: Any, *, user: Any | None = None) -> dict:
    from netbox_openbao.services import reveal_material

    actor = _openbao_actor(user)
    payload, _ttl = reveal_material(
        credential,
        actor,
        reason="netbox-proxbox credential access",
    )
    return payload if isinstance(payload, dict) else {}


def resolve_endpoint_password(
    endpoint: ProxmoxEndpoint,
    *,
    user: Any | None = None,
) -> str:
    if not endpoint_uses_openbao_storage(endpoint):
        from netbox_proxbox.models.primary_secrets import decrypt_primary_secret

        return decrypt_primary_secret(endpoint.password_enc)
    credential = _credential_for_uuid(
        getattr(endpoint, "openbao_password_credential_uuid", None)
    )
    if credential is None:
        return ""
    payload = reveal_credential_material(credential, user=user)
    return str(payload.get("password") or "")


def resolve_endpoint_token_value(
    endpoint: ProxmoxEndpoint,
    *,
    user: Any | None = None,
) -> str:
    if not endpoint_uses_openbao_storage(endpoint):
        from netbox_proxbox.models.primary_secrets import decrypt_primary_secret

        return decrypt_primary_secret(endpoint.token_value_enc)
    credential = _credential_for_uuid(
        getattr(endpoint, "openbao_token_credential_uuid", None)
    )
    if credential is None:
        return ""
    payload = reveal_credential_material(credential, user=user)
    return str(payload.get("token") or "")


def resolve_endpoint_ssh_password(
    endpoint: ProxmoxEndpoint,
    *,
    user: Any | None = None,
) -> str:
    if not endpoint_uses_openbao_storage(endpoint):
        from netbox_proxbox.utils import encryption as enc_helpers

        return enc_helpers.decrypt(endpoint.ssh_password_enc)
    credential = _credential_for_uuid(
        getattr(endpoint, "openbao_ssh_password_credential_uuid", None)
    )
    if credential is None:
        return ""
    payload = reveal_credential_material(credential, user=user)
    return str(payload.get("password") or "")


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
    credential = _credential_for_uuid(
        getattr(endpoint, "openbao_ssh_keypair_credential_uuid", None)
    )
    if credential is None:
        return ""
    payload = reveal_credential_material(credential, user=user)
    return str(payload.get("private_key") or "")
