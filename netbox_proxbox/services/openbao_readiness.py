"""Secret-free OpenBao setup readiness shared by UI and automation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OpenBaoReadinessItem:
    """One structural prerequisite and its operator remedy."""

    key: str
    label: str
    ready: bool
    detail: str
    remedy: str


@dataclass(frozen=True, slots=True)
class OpenBaoReadiness:
    """Complete, secret-free readiness snapshot."""

    items: tuple[OpenBaoReadinessItem, ...]

    @property
    def ready(self) -> bool:
        return all(item.ready for item in self.items)

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(item.detail for item in self.items if not item.ready)


def _item(
    key: str,
    label: str,
    ready: bool,
    detail: str,
    remedy: str,
) -> OpenBaoReadinessItem:
    return OpenBaoReadinessItem(key, label, ready, detail, remedy)


def _enabled_plugins() -> set[str]:
    try:
        from django.conf import settings

        return set(getattr(settings, "PLUGINS", ()) or ())
    except Exception:  # noqa: BLE001 - readiness must survive unconfigured Django
        return set()


def _plugin_item(plugins: set[str], plugin: str, label: str) -> OpenBaoReadinessItem:
    ready = plugin in plugins
    return _item(
        plugin,
        label,
        ready,
        f"{label} is enabled." if ready else f"{label} is not installed and enabled.",
        f"Install {label}, add {plugin} to PLUGINS, and restart NetBox.",
    )


def _settings_values() -> tuple[str, str]:
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        row = ProxboxPluginSettings.objects.first()
    except Exception:  # noqa: BLE001 - report missing structure without traceback
        return "proxbox", ""
    if row is None:
        return "proxbox", ""
    return (
        (getattr(row, "openbao_policy_slug", "") or "proxbox").strip(),
        (getattr(row, "openbao_service_username", "") or "").strip(),
    )


def _provider_state(
    provider_enabled: bool,
    policy_slug: str,
) -> tuple[Any | None, bool, str | None]:
    if not provider_enabled:
        return None, False, None
    try:
        from netbox_openbao.models import CredentialPolicy
        from netbox_openbao.utils import get_default_engine

        engine = get_default_engine()
        policy_exists = bool(
            engine
            and CredentialPolicy.objects.filter(
                engine=engine, slug=policy_slug
            ).exists()
        )
        return engine, policy_exists, None
    except Exception as exc:  # noqa: BLE001 - broken optional plugin stays diagnostic
        return None, False, type(exc).__name__


def _service_user_state(username: str) -> tuple[bool, str]:
    if not username:
        return False, "The OpenBao service username is not configured."
    try:
        from django.contrib.auth import get_user_model

        active = (
            get_user_model()
            .objects.filter(
                username=username,
                is_active=True,
            )
            .exists()
        )
    except Exception as exc:  # noqa: BLE001 - readiness remains diagnostic
        return (
            False,
            f"The configured OpenBao service user could not be checked ({type(exc).__name__}).",
        )
    if active:
        return True, f"The configured OpenBao service user {username!r} is active."
    return (
        False,
        f"The configured OpenBao service username {username!r} is not an active NetBox user.",
    )


def openbao_storage_readiness() -> OpenBaoReadiness:
    """Return prerequisites required by interactive provider storage writes."""
    plugins = _enabled_plugins()
    provider = _plugin_item(plugins, "netbox_openbao", "netbox-openbao")
    policy_slug, _username = _settings_values()
    engine, policy_exists, provider_error = _provider_state(provider.ready, policy_slug)
    engine_ready = engine is not None
    engine_detail = (
        f"Default SecretEngine {engine.slug!r} is configured."
        if engine_ready
        else "No default OpenBao SecretEngine is configured."
    )
    if provider_error:
        engine_detail = (
            f"The netbox-openbao model API is unavailable ({provider_error})."
        )
    return OpenBaoReadiness(
        (
            provider,
            _item(
                "default_engine",
                "Default SecretEngine",
                engine_ready,
                engine_detail,
                "Create a SecretEngine with an explicit API URL and mark it as default.",
            ),
            _item(
                "credential_policy",
                "Proxbox CredentialPolicy",
                policy_exists,
                (
                    f"CredentialPolicy {policy_slug!r} exists on the default engine."
                    if policy_exists
                    else f"CredentialPolicy {policy_slug!r} is missing from the default engine."
                ),
                f"Create CredentialPolicy {policy_slug!r} on the default engine.",
            ),
        )
    )


def openbao_readiness() -> OpenBaoReadiness:
    """Return complete composed-stack setup readiness for operators."""
    storage = openbao_storage_readiness()
    plugins = _enabled_plugins()
    rpc = _plugin_item(plugins, "netbox_rpc", "netbox-rpc")
    _policy_slug, username = _settings_values()
    user_ready, user_detail = _service_user_state(username)
    service_user = _item(
        "service_user",
        "OpenBao service user",
        user_ready,
        user_detail,
        "Set openbao_service_username to an existing active NetBox user; this command never creates users.",
    )
    return OpenBaoReadiness((storage.items[0], rpc, *storage.items[1:], service_user))
