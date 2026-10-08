"""Database system checks that report insecure transport and legacy key settings.

New endpoints default to HTTPS and TLS verification, but the default change
never rewrites existing rows. These checks tell operators which existing rows
still send credentials in plaintext or accept any certificate, and whether the
stored plugin encryption key is a legacy raw secret. They are registered with
the ``database`` tag, so Django runs them for ``manage.py migrate`` and
``manage.py check --database default`` but not for checks that must work
without a database. Silence individual IDs with ``SILENCED_SYSTEM_CHECKS``.
"""

from __future__ import annotations

from typing import Any

from django.core.checks import Tags
from django.core.checks import Warning as DjangoWarning
from django.core.checks import register as register_check
from django.db import DatabaseError

__all__ = ("insecure_transport_check", "register_security_checks")

_MAX_LISTED_NAMES = 10
_REGISTERED = False


def _names(queryset: Any) -> str:
    names = [
        str(name)
        for name in queryset.values_list("name", flat=True)[: _MAX_LISTED_NAMES + 1]
    ]
    shown = ", ".join(names[:_MAX_LISTED_NAMES])
    return f"{shown}, ..." if len(names) > _MAX_LISTED_NAMES else shown


def _plaintext_backend_warnings() -> list[DjangoWarning]:
    from netbox_proxbox.models import FastAPIEndpoint

    plaintext = FastAPIEndpoint.objects.filter(enabled=True, use_https=False)
    if not plaintext.exists():
        return []
    return [
        DjangoWarning(
            "Enabled ProxBox backend endpoints use plain HTTP: "
            f"{_names(plaintext)}. The backend API key, pushed Proxmox "
            "credentials, and the NetBox token cross this connection in "
            "plaintext.",
            hint="Serve proxbox-api over TLS and enable 'Use HTTPS' on the endpoint.",
            id="netbox_proxbox.W101",
        )
    ]


def _unverified_backend_warnings() -> list[DjangoWarning]:
    from netbox_proxbox.models import FastAPIEndpoint

    unverified = FastAPIEndpoint.objects.filter(
        enabled=True, use_https=True, verify_ssl=False
    )
    if not unverified.exists():
        return []
    return [
        DjangoWarning(
            "Enabled ProxBox backend endpoints do not verify the backend TLS "
            f"certificate: {_names(unverified)}.",
            hint="Install the backend CA in the system trust store and enable 'Verify SSL'.",
            id="netbox_proxbox.W102",
        )
    ]


def _unverified_proxmox_warnings() -> list[DjangoWarning]:
    from netbox_proxbox.models import ProxmoxEndpoint

    unverified = ProxmoxEndpoint.objects.filter(enabled=True, verify_ssl=False)
    if not unverified.exists():
        return []
    return [
        DjangoWarning(
            "Enabled Proxmox endpoints accept any TLS certificate: "
            f"{_names(unverified)}. An attacker on the network path can "
            "intercept the Proxmox credentials.",
            hint="Install the Proxmox CA where proxbox-api runs and enable 'Verify SSL'.",
            id="netbox_proxbox.W103",
        )
    ]


_UNRESOLVED = object()


def _backend_token_user(endpoint: Any) -> Any:
    """Return the user behind an endpoint's backend token.

    Returns ``None`` when no token is configured and ``_UNRESOLVED`` when a
    configured token identity cannot be matched to a NetBox token.
    """
    token = getattr(endpoint, "token", None)
    key = str(getattr(endpoint, "token_key", "") or "").strip()
    if token is None and key:
        from users.models import Token

        # NetBox stores v2 keys without the "nbt_" prefix used in credentials.
        token = Token.objects.filter(key=key.removeprefix("nbt_")).first()
        if token is None:
            return _UNRESOLVED
    return getattr(token, "user", None)


def _backend_sensitive_access_warnings() -> list[DjangoWarning]:
    """Report backend token users that cannot receive the runtime key."""
    from netbox_proxbox.models import NetBoxEndpoint
    from netbox_proxbox.sensitive_data import can_access_sensitive_data

    missing: list[str] = []
    endpoints = NetBoxEndpoint.objects.filter(enabled=True).select_related(
        "token__user"
    )
    for endpoint in endpoints:
        user = _backend_token_user(endpoint)
        if user is None or user is _UNRESOLVED:
            continue
        if not can_access_sensitive_data(user):
            missing.append(str(endpoint.name))
    if not missing:
        return []
    return [
        DjangoWarning(
            "The NetBox token that proxbox-api uses has no sensitive-data "
            f"access: {', '.join(missing[:_MAX_LISTED_NAMES])}. That token "
            "cannot read the plugin encryption key. A proxbox-api that relies "
            "on the plugin key, instead of its own key, then fails every "
            "synchronization with HTTP 503.",
            hint=(
                "Prefer giving proxbox-api its own encryption key. If it must "
                "keep using the plugin key, an active superuser can create a "
                "sensitive-data access grant for the token's user "
                "(/api/plugins/proxbox/sensitive-data-access/)."
            ),
            id="netbox_proxbox.W107",
        )
    ]


def _backend_settings_access_warnings() -> list[DjangoWarning]:
    from netbox_proxbox.models import NetBoxEndpoint, ProxboxPluginSettings

    settings_row = ProxboxPluginSettings.objects.order_by("pk").first()
    if settings_row is None:
        return []
    denied: list[str] = []
    endpoints = NetBoxEndpoint.objects.filter(enabled=True).select_related(
        "token__user"
    )
    for endpoint in endpoints:
        user = _backend_token_user(endpoint)
        if user is None:
            continue
        if user is _UNRESOLVED:
            # A configured identity that cannot be verified is reported, never
            # silently treated as healthy.
            denied.append(f"{endpoint.name} (token not found)")
            continue
        readable = (
            ProxboxPluginSettings.objects.restrict(user, "view")
            .filter(pk=settings_row.pk)
            .exists()
        )
        if not readable:
            denied.append(str(endpoint.name))
    if not denied:
        return []
    return [
        DjangoWarning(
            "The NetBox token that proxbox-api uses cannot read the Proxbox "
            f"plugin settings: {', '.join(denied[:_MAX_LISTED_NAMES])}. "
            "proxbox-api then falls back "
            "to its defaults, which can be more permissive than the configured "
            "SSRF policy.",
            hint=(
                "Grant the token's user view permission on Proxbox plugin "
                "settings (netbox_proxbox.view_proxboxpluginsettings)."
            ),
            id="netbox_proxbox.W105",
        )
    ]


def _legacy_key_warnings() -> list[DjangoWarning]:
    from netbox_proxbox.models import ProxboxPluginSettings
    from netbox_proxbox.utils.encryption import is_canonical_fernet_key

    stored_key = (
        ProxboxPluginSettings.objects.values_list("encryption_key", flat=True).first()
        or ""
    )
    if not stored_key.strip() or is_canonical_fernet_key(stored_key):
        return []
    return [
        DjangoWarning(
            "The plugin encryption key is a legacy raw secret, which is used "
            "without key derivation.",
            hint=(
                "Rotate to a generated Fernet key with the verified key-rotation "
                "workflow on the plugin Settings page."
            ),
            id="netbox_proxbox.W104",
        )
    ]


def _unavailable_openbao_storage_warnings() -> list[DjangoWarning]:
    from netbox_proxbox.integrations.openbao import is_netbox_openbao_installed
    from netbox_proxbox.models import ProxboxPluginSettings, ProxmoxEndpoint

    if is_netbox_openbao_installed():
        return []
    settings_selected = ProxboxPluginSettings.objects.filter(
        credential_storage_backend="openbao"
    ).exists()
    endpoints = ProxmoxEndpoint.objects.filter(credential_storage_backend="openbao")
    if not settings_selected and not endpoints.exists():
        return []
    selected_parts = ["plugin settings"] if settings_selected else []
    if endpoints.exists():
        selected_parts.append(f"endpoints: {_names(endpoints)}")
    selected = "; ".join(selected_parts)
    return [
        DjangoWarning(
            "OpenBao credential storage is selected while netbox-openbao is not "
            f"installed and enabled: {selected}.",
            hint=(
                "Select Automatic or Legacy Fernet-encrypted local storage, or "
                "install and enable netbox-openbao."
            ),
            id="netbox_proxbox.W106",
        )
    ]


def _is_missing_plugin_table(exc: DatabaseError) -> bool:
    """Return whether ``exc`` only means a plugin table is not migrated yet.

    A missing *column* (schema drift) is not this case and must be reported,
    because it can hide insecure rows that the warnings exist to surface.
    """
    message = str(exc).lower()
    return (
        "netbox_proxbox_" in message
        and (
            ("relation" in message and "does not exist" in message)
            or "no such table" in message
        )
        and "column" not in message
    )


def _pending_plugin_columns(databases: Any) -> set[str]:
    """Return ``table.column`` names that unapplied plugin migrations add.

    ``migrate`` runs database-tagged checks before it applies migrations, so an
    upgrade queries columns that a pending plugin migration has not added yet.
    Only those exact columns are expected to be missing; any other database
    failure still raises a W100 warning.
    """
    from django.db import connections
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.operations import AddField

    columns: set[str] = set()
    try:
        for alias in databases:
            executor = MigrationExecutor(connections[alias])
            targets = [
                node
                for node in executor.loader.graph.leaf_nodes()
                if node[0] == "netbox_proxbox"
            ]
            for migration, backwards in executor.migration_plan(targets):
                if backwards or migration.app_label != "netbox_proxbox":
                    continue
                for operation in migration.operations:
                    if isinstance(operation, AddField):
                        table = f"netbox_proxbox_{operation.model_name_lower}"
                        column = operation.field.db_column or operation.name
                        columns.add(f"{table}.{column}".lower())
    except DatabaseError:
        return set()
    return columns


def _is_pending_plugin_column(exc: DatabaseError, databases: Any) -> bool:
    """Return whether ``exc`` only reports a column a pending migration adds."""
    message = str(exc).lower()
    if "column" not in message or "does not exist" not in message:
        return False
    return any(
        f"column {name} does not exist" in message
        for name in _pending_plugin_columns(databases)
    )


def _run_check(check: Any, databases: Any = ()) -> list[Any]:
    """Run one inspection; report failures instead of hiding the result."""
    try:
        return check()
    except DatabaseError as exc:
        if _is_missing_plugin_table(exc) or _is_pending_plugin_column(exc, databases):
            # Before the plugin migrations run there is nothing to inspect.
            return []
        return [
            DjangoWarning(
                "Proxbox could not inspect endpoint transport or key settings, so "
                "insecure configuration may be unreported.",
                hint=f"Database error: {type(exc).__name__}",
                id="netbox_proxbox.W100",
            )
        ]


def insecure_transport_check(app_configs: Any = None, **kwargs: Any) -> list[Any]:
    """Return warnings for insecure endpoint transport and legacy keys."""
    databases = kwargs.get("databases")
    if not databases:
        return []
    # Each warning has its own inspection, so one failure never discards the
    # warnings another inspection already produced.
    inspections = (
        _plaintext_backend_warnings,
        _unverified_backend_warnings,
        _unverified_proxmox_warnings,
        _legacy_key_warnings,
        _backend_settings_access_warnings,
        _backend_sensitive_access_warnings,
        _unavailable_openbao_storage_warnings,
    )
    results: list[Any] = []
    for check in inspections:
        results.extend(_run_check(check, databases))
    return results


def register_security_checks() -> None:
    """Register the database-tagged security checks once per process."""
    global _REGISTERED
    if _REGISTERED:
        return
    register_check(insecure_transport_check, Tags.database)
    _REGISTERED = True
