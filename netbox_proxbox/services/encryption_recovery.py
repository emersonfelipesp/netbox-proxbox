"""Atomic recovery operations for plugin-owned encrypted database fields.

The registry in this module is the single inventory of ciphertext protected by
``ProxboxPluginSettings.encryption_key``.  Rotation verifies every non-empty
value before writing any replacement.  Destructive recovery is deliberately a
separate operation and uses queryset updates so endpoint save signals cannot
send incomplete credentials to proxbox-api.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from hmac import compare_digest
import logging
from typing import Final
from uuid import UUID

import requests
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connections, router, transaction
from django.db.models import Q
from django.views.decorators.debug import sensitive_variables

from netbox_proxbox.utils import encryption as enc_helpers


RESET_CONFIRMATION_PHRASE: Final = "RESET PROXBOX ENCRYPTED SECRETS"
logger = logging.getLogger(__name__)


class EncryptionRecoveryError(Exception):
    """Base class for secret-safe recovery failures."""


class EncryptionKeyMutationBlocked(EncryptionRecoveryError):
    """Raised when an ordinary save would orphan existing ciphertext."""


class OldEncryptionKeyRejected(EncryptionRecoveryError):
    """Raised when a rotation does not prove possession of the current key."""


class CiphertextVerificationFailed(EncryptionRecoveryError):
    """Raised when any registered ciphertext cannot be decrypted."""


class DestructiveResetRejected(EncryptionRecoveryError):
    """Raised when a destructive reset lacks a valid selection or confirmation."""


class EncryptionRecoveryConfigurationError(EncryptionRecoveryError):
    """Raised when an installed encrypted-field owner cannot be resolved."""


class BackendEncryptionDependencyError(EncryptionRecoveryError):
    """Raised when proxbox-api still depends on the plugin encryption key."""


@dataclass(frozen=True, slots=True)
class EncryptedFieldFamily:
    """One independently selectable set of ciphertext and associated trust state."""

    key: str
    label: str
    model_label: str
    encrypted_fields: tuple[str, ...]
    trust_fields: tuple[str, ...] = ()
    operational_reset_values: tuple[tuple[str, object], ...] = ()
    optional_app_label: str | None = None
    dormant_db_table: str | None = None


@dataclass(frozen=True, slots=True)
class EncryptedFamilyStatus:
    """Secret-free aggregate status suitable for forms and dashboards."""

    key: str
    label: str
    rows_with_ciphertext: int
    recovery_required: bool


@dataclass(frozen=True, slots=True)
class RotationResult:
    """Aggregate result of a successful key rotation."""

    rows_rotated: int
    ciphertext_values_rotated: int


@dataclass(frozen=True, slots=True)
class ResetResult:
    """Aggregate result of a successful destructive reset."""

    families_reset: tuple[str, ...]
    rows_matched: int


@dataclass(frozen=True, slots=True)
class _BackendTargetSnapshot:
    """One immutable backend target captured before authenticated attestation."""

    domain: str
    ip_address: object | None
    port: int
    use_https: bool
    verify_ssl: bool
    use_websocket: bool
    server_side_websocket: bool
    websocket_domain: str | None
    websocket_port: int | None


ENCRYPTED_FIELD_FAMILIES: Final = (
    EncryptedFieldFamily(
        key="proxmox_api",
        label="Proxmox API credentials",
        model_label="netbox_proxbox.ProxmoxEndpoint",
        encrypted_fields=("password_enc", "token_value_enc"),
        trust_fields=("pushed_credential_fingerprint",),
        operational_reset_values=(("enabled", False),),
    ),
    EncryptedFieldFamily(
        key="proxmox_ssh",
        label="Proxmox endpoint SSH credentials",
        model_label="netbox_proxbox.ProxmoxEndpoint",
        encrypted_fields=("ssh_password_enc", "ssh_private_key_enc"),
        trust_fields=("ssh_known_host_fingerprint",),
        operational_reset_values=(("enabled", False),),
    ),
    EncryptedFieldFamily(
        key="fastapi_backend_key",
        label="ProxBox API authentication key",
        model_label="netbox_proxbox.FastAPIEndpoint",
        encrypted_fields=("token_enc",),
        trust_fields=("backend_key_target_fingerprint",),
        operational_reset_values=(("enabled", False),),
    ),
    EncryptedFieldFamily(
        key="pbs_api",
        label="Proxmox Backup Server API credentials",
        model_label="netbox_proxbox.PBSEndpoint",
        encrypted_fields=("token_secret_enc",),
        trust_fields=("fingerprint",),
        operational_reset_values=(("enabled", False),),
    ),
    EncryptedFieldFamily(
        key="pbs_fallback_api",
        label="netbox-pbs fallback ProxBox API key",
        model_label="netbox_pbs.PBSPluginSettings",
        encrypted_fields=("proxbox_api_key_enc",),
        optional_app_label="netbox_pbs",
        dormant_db_table="netbox_pbs_pbspluginsettings",
    ),
    EncryptedFieldFamily(
        key="pdm_api",
        label="Proxmox Datacenter Manager API credentials",
        model_label="netbox_proxbox.PDMEndpoint",
        encrypted_fields=("token_secret_enc",),
        trust_fields=("fingerprint",),
        operational_reset_values=(("enabled", False),),
    ),
    EncryptedFieldFamily(
        key="node_ssh",
        label="Per-node SSH credentials",
        model_label="netbox_proxbox.NodeSSHCredential",
        encrypted_fields=("password_enc", "private_key_enc"),
        trust_fields=("known_host_fingerprint",),
    ),
    EncryptedFieldFamily(
        key="cloud_init_ssh_keys",
        label="Cloud-init SSH public-key bundles",
        model_label="netbox_proxbox.ProxmoxVMCloudInit",
        encrypted_fields=("sshkeys_enc",),
    ),
    EncryptedFieldFamily(
        key="firecracker_agent",
        label="Firecracker host-agent tokens",
        model_label="netbox_proxbox.FirecrackerHost",
        encrypted_fields=("agent_token_enc",),
        operational_reset_values=(("status", "offline"),),
    ),
)

_FAMILY_BY_KEY: Final = {family.key: family for family in ENCRYPTED_FIELD_FAMILIES}
_EXPLICIT_WRITE_MARKER: Final = "_proxbox_encryption_expected_ciphertexts"


class _SetterProducedCiphertext(str):
    """Tag ciphertext produced by a registered companion model's public setter."""


def mark_encrypted_fields_for_write(instance: object, *field_names: str) -> None:
    """Remember the persisted values an explicit secret assignment is replacing."""

    expected = dict(getattr(instance, _EXPLICIT_WRITE_MARKER, {}))
    for field_name in field_names:
        expected.setdefault(field_name, str(getattr(instance, field_name, "") or ""))
    setattr(instance, _EXPLICIT_WRITE_MARKER, expected)


def _model_for(family: EncryptedFieldFamily) -> type | None:
    """Resolve a family model, omitting only a genuinely absent optional app."""

    if family.optional_app_label is not None:
        try:
            apps.get_app_config(family.optional_app_label)
        except LookupError:
            return None
    try:
        model = apps.get_model(family.model_label)
    except LookupError as exc:
        raise EncryptionRecoveryConfigurationError(
            "Encrypted-secret recovery is unavailable because the installed "
            f"owner of {family.label} could not resolve its registered model."
        ) from exc
    if model is None:  # pragma: no cover - defensive Django registry contract
        raise EncryptionRecoveryConfigurationError(
            "Encrypted-secret recovery is unavailable because the installed "
            f"owner of {family.label} did not register its expected model."
        )
    try:
        for field_name in (
            *family.encrypted_fields,
            *family.trust_fields,
            *(name for name, _value in family.operational_reset_values),
        ):
            model._meta.get_field(field_name)
    except (AttributeError, FieldDoesNotExist) as exc:
        raise EncryptionRecoveryConfigurationError(
            "Encrypted-secret recovery is unavailable because the installed "
            f"owner of {family.label} does not provide the registered schema."
        ) from exc
    return model


def _dormant_optional_tables(
    *, using: str = "default"
) -> tuple[tuple[EncryptedFieldFamily, str], ...]:
    """Resolve unloaded optional-owner tables whose ciphertext may survive."""

    connection = connections[using]
    try:
        with connection.cursor() as cursor:
            existing_tables = set(connection.introspection.table_names(cursor))
            dormant: list[tuple[EncryptedFieldFamily, str]] = []
            for family in ENCRYPTED_FIELD_FAMILIES:
                if family.optional_app_label is None or family.dormant_db_table is None:
                    continue
                try:
                    apps.get_app_config(family.optional_app_label)
                except LookupError:
                    pass
                else:
                    continue
                if family.dormant_db_table not in existing_tables:
                    continue
                description = connection.introspection.get_table_description(
                    cursor, family.dormant_db_table
                )
                column_names = {column.name for column in description}
                missing = set(family.encrypted_fields) - column_names
                if missing:
                    raise EncryptionRecoveryConfigurationError(
                        "Encryption-key mutation is unavailable because a dormant "
                        f"{family.label} table has an incompatible schema. Re-enable "
                        "and migrate its owning companion before recovery."
                    )
                dormant.append((family, family.dormant_db_table))
            return tuple(dormant)
    except EncryptionRecoveryConfigurationError:
        raise
    except DatabaseError as exc:
        raise EncryptionRecoveryConfigurationError(
            "Encryption-key mutation could not inspect dormant optional-companion "
            "tables. Key mutation remains blocked until the database is repaired."
        ) from exc


def _dormant_optional_ciphertext_exists(
    dormant_tables: tuple[tuple[EncryptedFieldFamily, str], ...],
    *,
    using: str = "default",
) -> bool:
    """Return whether any unloaded optional owner retains shared-key ciphertext."""

    connection = connections[using]
    try:
        with connection.cursor() as cursor:
            for family, table_name in dormant_tables:
                predicates = " OR ".join(
                    f"COALESCE({connection.ops.quote_name(field_name)}, '') <> ''"
                    for field_name in family.encrypted_fields
                )
                cursor.execute(
                    "SELECT 1 FROM "
                    f"{connection.ops.quote_name(table_name)} "
                    f"WHERE ({predicates}) LIMIT 1"
                )
                if cursor.fetchone() is not None:
                    return True
    except DatabaseError as exc:
        raise EncryptionRecoveryConfigurationError(
            "Encryption-key mutation could not verify dormant optional-companion "
            "ciphertext. Key mutation remains blocked until the database is repaired."
        ) from exc
    return False


def available_encrypted_field_families() -> tuple[EncryptedFieldFamily, ...]:
    """Return families whose owning app is installed and model is resolvable."""

    return tuple(
        family for family in ENCRYPTED_FIELD_FAMILIES if _model_for(family) is not None
    )


def _available_family_models() -> tuple[tuple[EncryptedFieldFamily, type], ...]:
    """Resolve the active registry once for one recovery operation."""

    resolved: list[tuple[EncryptedFieldFamily, type]] = []
    for family in ENCRYPTED_FIELD_FAMILIES:
        model = _model_for(family)
        if model is not None:
            resolved.append((family, model))
    return tuple(resolved)


def install_encrypted_writer_guards() -> None:
    """Serialize every registered model save with key selection and rotation."""

    from netbox_proxbox.models import ProxboxPluginSettings

    fields_by_model: dict[type, set[str]] = {}
    for family in ENCRYPTED_FIELD_FAMILIES:
        try:
            model = _model_for(family)
        except EncryptionRecoveryConfigurationError:
            if family.optional_app_label is None:
                raise
            logger.critical(
                "Encrypted-secret recovery is disabled until the installed %s "
                "companion is upgraded to the required encrypted-field schema.",
                family.optional_app_label,
            )
            continue
        if model is None:
            continue
        fields_by_model.setdefault(model, set()).update(family.encrypted_fields)

    for model, field_names in fields_by_model.items():
        if getattr(model, "_proxbox_encryption_writer_guard_installed", False):
            continue
        original_save = model.save
        encrypted_fields = frozenset(field_names)

        optional_secret_setter = getattr(model, "set_proxbox_api_key", None)
        if callable(optional_secret_setter) and not getattr(
            optional_secret_setter, "_proxbox_encryption_marks_write", False
        ):

            @wraps(optional_secret_setter)
            def guarded_secret_setter(
                instance: object,
                *args: object,
                _original_setter: object = optional_secret_setter,
                **kwargs: object,
            ) -> object:
                mark_encrypted_fields_for_write(instance, "proxbox_api_key_enc")
                result = _original_setter(instance, *args, **kwargs)  # type: ignore[operator]
                ciphertext = getattr(instance, "proxbox_api_key_enc", "")
                if ciphertext:
                    # netbox-pbs validates its write-only API key on a temporary
                    # model and copies this value into the persisted instance.
                    # Preserve that setter provenance across the copy so the
                    # save guard can distinguish it from a direct field write.
                    setattr(
                        instance,
                        "proxbox_api_key_enc",
                        _SetterProducedCiphertext(str(ciphertext)),
                    )
                return result

            guarded_secret_setter._proxbox_encryption_marks_write = True
            model.set_proxbox_api_key = guarded_secret_setter

        @wraps(original_save)
        @sensitive_variables()
        def guarded_save(
            instance: object,
            *args: object,
            _original_save: object = original_save,
            _encrypted_fields: frozenset[str] = encrypted_fields,
            **kwargs: object,
        ) -> object:
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                normalized_update_fields = tuple(
                    str(field_name) for field_name in update_fields
                )
                kwargs["update_fields"] = normalized_update_fields
                if _encrypted_fields.isdisjoint(normalized_update_fields):
                    return _original_save(instance, *args, **kwargs)  # type: ignore[operator]

            ciphertexts = tuple(
                str(getattr(instance, field_name, "") or "")
                for field_name in _encrypted_fields
            )
            using_value = kwargs.get("using")
            using = (
                using_value
                if isinstance(using_value, str)
                else router.db_for_write(type(instance), instance=instance)
            )
            with transaction.atomic(using=using):
                settings_obj = (
                    ProxboxPluginSettings.objects.using(using)
                    .select_for_update()
                    .filter(singleton_key="default")
                    .first()
                )
                current_key = (
                    str(settings_obj.encryption_key or "").strip()
                    if settings_obj is not None
                    else ""
                )
                persisted = None
                instance_pk = getattr(instance, "pk", None)
                if instance_pk is not None:
                    persisted = (
                        type(instance)
                        .objects.using(using)
                        .filter(pk=instance_pk)
                        .values_list(*_encrypted_fields)
                        .first()
                    )
                expected_writes = dict(getattr(instance, _EXPLICIT_WRITE_MARKER, {}))
                if persisted is not None:
                    for field_name, persisted_ciphertext in zip(
                        _encrypted_fields, persisted, strict=True
                    ):
                        candidate_value = getattr(instance, field_name, "") or ""
                        candidate = str(candidate_value)
                        current = str(persisted_ciphertext or "")
                        if candidate == current:
                            continue
                        expected = expected_writes.get(field_name)
                        setter_produced = isinstance(
                            candidate_value, _SetterProducedCiphertext
                        )
                        if not setter_produced and (
                            expected is None or str(expected or "") != current
                        ):
                            raise ValidationError(
                                {
                                    "__all__": (
                                        "This object changed during encryption-key "
                                        "recovery. Reload it before saving credentials."
                                    )
                                }
                            )
                try:
                    for ciphertext in ciphertexts:
                        if ciphertext:
                            enc_helpers.decrypt(ciphertext, key=current_key)
                except enc_helpers.EncryptionError:
                    raise ValidationError(
                        {
                            "__all__": (
                                "Encrypted values were prepared with a stale or "
                                "unavailable plugin key. Reload the object and "
                                "submit the credential again."
                            )
                        }
                    ) from None
                result = _original_save(instance, *args, **kwargs)  # type: ignore[operator]
                for field_name in _encrypted_fields:
                    value = getattr(instance, field_name, "")
                    if isinstance(value, _SetterProducedCiphertext):
                        # Provenance authorizes one persisted write only. Do not
                        # leave a reusable bypass marker on a long-lived instance.
                        setattr(instance, field_name, str(value))
                setattr(instance, _EXPLICIT_WRITE_MARKER, {})
                return result

        model.save = guarded_save
        model._proxbox_encryption_writer_guard_installed = True


def lock_encrypted_field_tables(
    *, using: str = "default"
) -> tuple[tuple[EncryptedFieldFamily, type], ...]:
    """Block concurrent registered-table writes for one PostgreSQL transaction."""

    connection = connections[using]
    if connection.vendor != "postgresql":
        raise EncryptionRecoveryConfigurationError(
            "Encryption-key mutation requires PostgreSQL table locking and was "
            "blocked on this unsupported database backend."
        )
    family_models = _available_family_models()
    dormant_tables = _dormant_optional_tables(using=using)
    table_names = sorted(
        {model._meta.db_table for _family, model in family_models}
        | {table_name for _family, table_name in dormant_tables}
    )
    quoted_tables = ", ".join(
        connection.ops.quote_name(table_name) for table_name in table_names
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"LOCK TABLE {quoted_tables} IN SHARE ROW EXCLUSIVE MODE")
    except DatabaseError as exc:
        raise EncryptionRecoveryConfigurationError(
            "Encryption-key mutation could not lock every registered database table."
        ) from exc
    if _dormant_optional_ciphertext_exists(dormant_tables, using=using):
        raise EncryptionRecoveryConfigurationError(
            "Encryption-key mutation was blocked because an unloaded optional "
            "companion still owns shared-key ciphertext. Re-enable and migrate "
            "the companion, then rotate or reset its registered family."
        )
    return family_models


def record_encryption_recovery_event(
    *,
    settings_obj: object,
    actor: object,
    request_id: UUID,
    operation: str,
    outcome: str,
    family_keys: tuple[str, ...],
    rows_affected: int = 0,
    ciphertext_values_affected: int = 0,
) -> None:
    """Persist one secret-free NetBox changelog event for a recovery attempt."""

    from django.contrib.contenttypes.models import ContentType

    from core.choices import ObjectChangeActionChoices
    from core.models import ObjectChange

    event = {
        "operation": operation,
        "outcome": outcome,
        "families": list(family_keys),
        "rows_affected": rows_affected,
        "ciphertext_values_affected": ciphertext_values_affected,
    }
    username = str(getattr(actor, "username", "") or "")
    ObjectChange.objects.create(
        user=actor,
        user_name=username,
        request_id=request_id,
        action=ObjectChangeActionChoices.ACTION_UPDATE,
        changed_object_type=ContentType.objects.get_for_model(
            settings_obj, for_concrete_model=False
        ),
        changed_object_id=getattr(settings_obj, "pk"),
        object_repr=str(settings_obj)[:200],
        message=(
            f"Encryption recovery {operation} {outcome}; "
            f"families={len(family_keys)}, rows={rows_affected}, "
            f"ciphertexts={ciphertext_values_affected}"
        )[:200],
        prechange_data={"encryption_recovery": {"outcome": "requested"}},
        postchange_data={"encryption_recovery": event},
    )


def _ciphertext_query(family: EncryptedFieldFamily) -> Q:
    query = Q()
    for field_name in family.encrypted_fields:
        query |= ~Q(**{field_name: ""})
    return query


def encrypted_payloads_exist() -> bool:
    """Return whether any registered family contains non-empty ciphertext."""

    try:
        active_ciphertext_exists = any(
            model.objects.filter(_ciphertext_query(family)).exists()
            for family, model in _available_family_models()
        )
        if active_ciphertext_exists:
            return True
        dormant_tables = _dormant_optional_tables()
        return _dormant_optional_ciphertext_exists(dormant_tables)
    except DatabaseError as exc:
        raise EncryptionRecoveryConfigurationError(
            "Encrypted-secret recovery could not verify the registered database "
            "tables. Key mutation remains blocked until the installation is repaired."
        ) from exc


@sensitive_variables()
def assert_ordinary_key_mutation_allowed(current_key: str, proposed_key: str) -> None:
    """Reject ordinary key clear/replacement while ciphertext still exists."""

    current = (current_key or "").strip()
    proposed = (proposed_key or "").strip()
    if current == proposed:
        return
    if encrypted_payloads_exist():
        raise EncryptionKeyMutationBlocked(
            "The plugin encryption key cannot be cleared or replaced while encrypted "
            "values exist. Use the verified rotation workflow, or the separately "
            "permissioned destructive reset workflow if the old key is unavailable."
        )


@sensitive_variables()
def ciphertext_state(ciphertext: str, *, key: str | None = None) -> str:
    """Return ``missing``, ``configured``, or ``recovery_required`` without plaintext."""

    value = str(ciphertext or "")
    if not value:
        return "missing"
    if key is None:
        from netbox_proxbox.models import ProxboxPluginSettings

        key = str(ProxboxPluginSettings.get_solo().encryption_key or "")
    try:
        enc_helpers.decrypt(value, key=key)
    except enc_helpers.EncryptionError:
        return "recovery_required"
    return "configured"


@sensitive_variables()
def encrypted_family_statuses(
    *, key: str | None = None
) -> tuple[EncryptedFamilyStatus, ...]:
    """Return aggregate family counts and current-key usability without secrets."""

    if key is None:
        from netbox_proxbox.models import ProxboxPluginSettings

        key = str(ProxboxPluginSettings.get_solo().encryption_key or "")

    statuses: list[EncryptedFamilyStatus] = []
    try:
        for family, model in _available_family_models():
            queryset = model.objects.filter(_ciphertext_query(family))
            row_count = queryset.count()
            recovery_required = False
            for values in queryset.values_list(*family.encrypted_fields).iterator(
                chunk_size=200
            ):
                for ciphertext in values:
                    if (
                        ciphertext
                        and ciphertext_state(str(ciphertext), key=key)
                        == "recovery_required"
                    ):
                        recovery_required = True
                        break
                if recovery_required:
                    break
            statuses.append(
                EncryptedFamilyStatus(
                    key=family.key,
                    label=family.label,
                    rows_with_ciphertext=row_count,
                    recovery_required=recovery_required,
                )
            )
    except DatabaseError as exc:
        raise EncryptionRecoveryConfigurationError(
            "Encrypted-secret recovery could not inspect the registered database "
            "tables. Key mutation remains blocked until the installation is repaired."
        ) from exc
    return tuple(statuses)


@sensitive_variables()
def _assert_backends_use_independent_encryption(
    *, old_key: str, using: str = "default"
) -> None:
    """Require every configured proxbox-api to provide the versioned key proof."""

    from netbox_proxbox.models import FastAPIEndpoint
    from netbox_proxbox.services.backend_key_adoption import (
        BackendKeyAdoptionError,
        backend_key_target,
        backend_key_target_fingerprint,
    )

    endpoints = FastAPIEndpoint.objects.using(using).all().order_by("pk")
    for endpoint in endpoints:
        ip_resolver = getattr(endpoint, "backend_key_ip_address_for_trust", None)
        ip_address = (
            ip_resolver()
            if callable(ip_resolver)
            else getattr(endpoint, "ip_address", None)
        )
        target = _BackendTargetSnapshot(
            domain=str(getattr(endpoint, "domain", "") or ""),
            ip_address=ip_address,
            port=int(getattr(endpoint, "port", 0) or 0),
            use_https=bool(getattr(endpoint, "use_https", False)),
            verify_ssl=bool(getattr(endpoint, "verify_ssl", True)),
            use_websocket=bool(getattr(endpoint, "use_websocket", False)),
            server_side_websocket=bool(
                getattr(endpoint, "server_side_websocket", False)
            ),
            websocket_domain=getattr(endpoint, "websocket_domain", None),
            websocket_port=getattr(endpoint, "websocket_port", None),
        )
        stored_fingerprint = (
            str(getattr(endpoint, "backend_key_target_fingerprint", "") or "")
            .strip()
            .lower()
        )
        try:
            captured_fingerprint = backend_key_target_fingerprint(target)
        except BackendKeyAdoptionError as exc:
            raise BackendEncryptionDependencyError(
                "Plugin-key rotation could not resolve every configured proxbox-api "
                "target for encryption-source attestation."
            ) from exc
        if len(stored_fingerprint) != 64 or not compare_digest(
            stored_fingerprint, captured_fingerprint
        ):
            raise BackendEncryptionDependencyError(
                "Plugin-key rotation requires every configured proxbox-api target "
                "to have a current trusted identity binding."
            )
        try:
            # Both fingerprint comparison and request URL derive from this one
            # captured object. A concurrent IPAddress update cannot rebind the
            # decrypted API key between validation and the network request.
            base_url, verify_ssl = backend_key_target(target)
            token = enc_helpers.decrypt(str(endpoint.token_enc or ""), key=old_key)
        except (BackendKeyAdoptionError, enc_helpers.EncryptionError) as exc:
            raise BackendEncryptionDependencyError(
                "Plugin-key rotation could not authenticate every configured "
                "proxbox-api encryption-source attestation."
            ) from exc
        try:
            response = requests.get(
                f"{base_url.rstrip('/')}/admin/encryption/status",
                headers={"X-Proxbox-API-Key": token},
                verify=verify_ssl,
                timeout=10,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise BackendEncryptionDependencyError(
                "Plugin-key rotation could not reach every configured proxbox-api "
                "encryption-source attestation endpoint."
            ) from exc
        try:
            if response.status_code != 200:
                raise BackendEncryptionDependencyError(
                    "Plugin-key rotation requires a successful encryption-source "
                    "attestation from every configured proxbox-api target."
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise BackendEncryptionDependencyError(
                    "Plugin-key rotation received an invalid encryption-source "
                    "attestation from a configured proxbox-api target."
                ) from exc
            version = (
                payload.get("attestation_version")
                if isinstance(payload, dict)
                else None
            )
            active_source = (
                payload.get("active_key_source") if isinstance(payload, dict) else None
            )
            credentials_verified = (
                payload.get("encrypted_credentials_verified")
                if isinstance(payload, dict)
                else None
            )
            if (
                not isinstance(version, int)
                or isinstance(version, bool)
                or version != 1
                or active_source not in {"env", "local"}
                or credentials_verified is not True
            ):
                raise BackendEncryptionDependencyError(
                    "Plugin-key rotation requires proxbox-api's versioned attestation "
                    "that its active cached key is independent and decrypts every "
                    "stored backend credential. Upgrade and migrate the backend first."
                )
        finally:
            response.close()


@sensitive_variables()
def rotate_encryption_key(
    *,
    old_key: str,
    new_key: str,
    audit_actor: object,
    audit_request_id: UUID,
) -> RotationResult:
    """Verify every ciphertext with ``old_key`` then atomically re-encrypt all rows."""

    from netbox_proxbox.models import ProxboxPluginSettings

    old_value = (old_key or "").strip()
    new_value = (new_key or "").strip()
    try:
        same_key = enc_helpers.keys_match(old_value, new_value)
    except enc_helpers.EncryptionError as exc:
        raise OldEncryptionKeyRejected(
            "Both the current and replacement keys must be valid Fernet keys."
        ) from exc
    if same_key:
        raise OldEncryptionKeyRejected(
            "The replacement encryption key must differ from the current key."
        )

    try:
        with transaction.atomic():
            settings_obj = ProxboxPluginSettings.get_solo()
            locked_settings = ProxboxPluginSettings.objects.select_for_update().get(
                pk=settings_obj.pk
            )
            stored_key = str(locked_settings.encryption_key or "").strip()
            try:
                stored_matches_old = enc_helpers.keys_match(old_value, stored_key)
            except enc_helpers.EncryptionError:
                # A drifted or malformed stored setting is recoverable when the
                # supplied key proves possession by decrypting every ciphertext.
                stored_matches_old = False

            ciphertext_count = 0
            row_keys: set[tuple[str, object]] = set()

            # First pass: lock and verify the complete registry before any write.
            # Plaintexts deliberately remain scoped to one decrypt call instead of
            # accumulating in memory while later families are checked.
            family_models = lock_encrypted_field_tables()
            for family, model in family_models:
                rows = (
                    model.objects.select_for_update()
                    .filter(_ciphertext_query(family))
                    .values_list("pk", *family.encrypted_fields)
                    .order_by("pk")
                )
                for values in rows.iterator(chunk_size=200):
                    pk, *ciphertexts = values
                    for _field_name, ciphertext in zip(
                        family.encrypted_fields, ciphertexts, strict=True
                    ):
                        if not ciphertext:
                            continue
                        try:
                            enc_helpers.decrypt(str(ciphertext), key=old_value)
                        except enc_helpers.EncryptionError as exc:
                            if not stored_matches_old:
                                raise OldEncryptionKeyRejected(
                                    "The supplied current encryption key was not "
                                    "accepted by the stored setting or every "
                                    "encrypted value."
                                ) from exc
                            raise CiphertextVerificationFailed(
                                "Key rotation was aborted because at least one "
                                f"encrypted value in {family.label} row {pk} could "
                                "not be verified. No encrypted values or settings "
                                "were changed."
                            ) from exc
                        ciphertext_count += 1
                    row_keys.add((family.model_label, pk))

            if ciphertext_count == 0 and not stored_matches_old:
                raise OldEncryptionKeyRejected(
                    "The supplied current encryption key was not accepted."
                )

            _assert_backends_use_independent_encryption(old_key=old_value)

            # Second pass: every relevant row is still locked by this transaction,
            # so the verified ciphertext cannot change before it is re-encrypted.
            for family, model in family_models:
                rows = (
                    model.objects.filter(_ciphertext_query(family))
                    .values_list("pk", *family.encrypted_fields)
                    .order_by("pk")
                )
                for values in rows.iterator(chunk_size=200):
                    pk, *ciphertexts = values
                    replacements: dict[str, str] = {}
                    for field_name, ciphertext in zip(
                        family.encrypted_fields, ciphertexts, strict=True
                    ):
                        if not ciphertext:
                            continue
                        try:
                            plaintext = enc_helpers.decrypt(
                                str(ciphertext), key=old_value
                            )
                            replacements[field_name] = enc_helpers.encrypt(
                                plaintext, key=new_value
                            )
                        except enc_helpers.EncryptionError as exc:
                            raise CiphertextVerificationFailed(
                                "Key rotation was rolled back because a previously "
                                f"verified value in {family.label} row {pk} changed "
                                "or could not be re-encrypted. No encrypted values "
                                "or settings were changed."
                            ) from exc
                    if replacements:
                        model.objects.filter(pk=pk).update(**replacements)

            ProxboxPluginSettings.objects.filter(pk=locked_settings.pk).update(
                encryption_key=new_value
            )
            record_encryption_recovery_event(
                settings_obj=locked_settings,
                actor=audit_actor,
                request_id=audit_request_id,
                operation="rotate",
                outcome="succeeded",
                family_keys=tuple(family.key for family, _model in family_models),
                rows_affected=len(row_keys),
                ciphertext_values_affected=ciphertext_count,
            )
    except DatabaseError as exc:
        raise EncryptionRecoveryConfigurationError(
            "Encryption-key rotation could not access every registered database "
            "table. No encrypted values or settings were changed."
        ) from exc

    return RotationResult(
        rows_rotated=len(row_keys),
        ciphertext_values_rotated=ciphertext_count,
    )


def reset_encrypted_families(
    *,
    family_keys: list[str] | tuple[str, ...],
    confirmation: str,
    audit_actor: object,
    audit_request_id: UUID,
) -> ResetResult:
    """Destructively clear selected ciphertext/trust fields without save signals."""

    from netbox_proxbox.models import ProxboxPluginSettings

    selected = tuple(dict.fromkeys(str(key) for key in family_keys if key))
    unknown = tuple(key for key in selected if key not in _FAMILY_BY_KEY)
    if not selected or unknown:
        raise DestructiveResetRejected(
            "Select at least one recognized encrypted field family."
        )
    if confirmation != RESET_CONFIRMATION_PHRASE:
        raise DestructiveResetRejected(
            f"Type the exact confirmation phrase: {RESET_CONFIRMATION_PHRASE}"
        )

    matched_rows: set[tuple[str, object]] = set()
    reset_families: list[str] = []
    settings_obj = ProxboxPluginSettings.get_solo()
    try:
        with transaction.atomic():
            locked_settings = ProxboxPluginSettings.objects.select_for_update().get(
                pk=settings_obj.pk
            )
            family_models = {
                family.key: (family, model)
                for family, model in lock_encrypted_field_tables()
            }
            for key in selected:
                family = _FAMILY_BY_KEY[key]
                resolved = family_models.get(key)
                if resolved is None:
                    continue
                _resolved_family, model = resolved
                queryset = model.objects.select_for_update().filter(
                    _ciphertext_query(family)
                )
                matched_rows.update(
                    (family.model_label, pk)
                    for pk in queryset.values_list("pk", flat=True)
                )
                clear_values = {
                    field_name: "" for field_name in family.encrypted_fields
                }
                for field_name in family.trust_fields:
                    model_field = model._meta.get_field(field_name)
                    clear_values[field_name] = None if model_field.null else ""
                clear_values.update(dict(family.operational_reset_values))
                queryset.update(**clear_values)
                reset_families.append(key)
            record_encryption_recovery_event(
                settings_obj=locked_settings,
                actor=audit_actor,
                request_id=audit_request_id,
                operation="reset",
                outcome="succeeded",
                family_keys=tuple(reset_families),
                rows_affected=len(matched_rows),
            )
    except DatabaseError as exc:
        raise EncryptionRecoveryConfigurationError(
            "Encrypted-secret reset could not access every selected database table. "
            "No encrypted values or trust state were changed."
        ) from exc

    return ResetResult(
        families_reset=tuple(reset_families), rows_matched=len(matched_rows)
    )
