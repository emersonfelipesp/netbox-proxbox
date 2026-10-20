"""SSH credential metadata and encrypted material attached to an endpoint service."""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.debug import sensitive_variables
from netbox.models import NetBoxModel

from netbox_proxbox.choices import CredentialStorageBackendChoices
from netbox_proxbox.models.ssh_credential import AUTH_METHOD_CHOICES, AUTH_METHOD_KEY
from netbox_proxbox.utils import encryption as enc_helpers


class ServiceSSHCredential(NetBoxModel):
    """SSH credential owned by one Proxbox application service."""

    service = models.OneToOneField(
        to="netbox_proxbox.ProxmoxEndpointService",
        on_delete=models.CASCADE,
        related_name="ssh_credential",
        verbose_name=_("Proxmox application service"),
    )
    username = models.CharField(max_length=64, verbose_name=_("SSH username"))
    auth_method = models.CharField(
        max_length=8,
        choices=AUTH_METHOD_CHOICES,
        default=AUTH_METHOD_KEY,
        verbose_name=_("Authentication method"),
    )
    storage_backend = models.CharField(
        max_length=32,
        choices=(
            (
                CredentialStorageBackendChoices.LEGACY_ENCRYPTED,
                _("Legacy Fernet-encrypted local storage"),
            ),
            (CredentialStorageBackendChoices.OPENBAO, _("OpenBao")),
        ),
        default=CredentialStorageBackendChoices.LEGACY_ENCRYPTED,
        verbose_name=_("Credential storage backend"),
    )
    password_enc = models.TextField(blank=True, default="", editable=False)
    private_key_enc = models.TextField(blank=True, default="", editable=False)
    openbao_password_credential_uuid = models.UUIDField(
        null=True, blank=True, editable=False
    )
    openbao_keypair_credential_uuid = models.UUIDField(
        null=True, blank=True, editable=False
    )
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("service",)
        verbose_name = _("Service SSH credential")
        verbose_name_plural = _("Service SSH credentials")

    def __str__(self) -> str:
        try:
            service = str(self.service)
        except ObjectDoesNotExist:
            service = (
                f"service {self.service_id}"
                if self.service_id is not None
                else "unassigned service"
            )
        return f"{self.username or 'SSH'}@{service}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:servicesshcredential", args=[self.pk])

    def serialize_object(self, exclude=None) -> dict[str, object]:
        """Redact ciphertext and provider references from change snapshots."""
        from netbox_proxbox.models.changelog_redaction import redact_snapshot_data

        return redact_snapshot_data(
            self._meta.model_name, super().serialize_object(exclude=exclude)
        )

    def clean(self) -> None:
        """Keep provider references and Fernet ciphertext mutually exclusive."""
        super().clean()
        errors = {}
        if self.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            if self.password_enc or self.private_key_enc:
                errors["storage_backend"] = (
                    "OpenBao service credentials cannot retain local ciphertext."
                )
        elif (
            self.openbao_password_credential_uuid
            or self.openbao_keypair_credential_uuid
        ):
            errors["storage_backend"] = (
                "Locally encrypted service credentials cannot retain OpenBao references."
            )
        if errors:
            raise ValidationError(errors)

    @property
    def has_password(self) -> bool:
        if self.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            return bool(self.openbao_password_credential_uuid)
        return bool(self.password_enc)

    @property
    def has_private_key(self) -> bool:
        if self.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            return bool(self.openbao_keypair_credential_uuid)
        return bool(self.private_key_enc)

    @sensitive_variables()
    def set_password(
        self,
        plaintext: str,
        *,
        key: str,
        user: object | None = None,
        request: object | None = None,
    ) -> None:
        from netbox_proxbox.services.encryption_recovery import (
            mark_encrypted_fields_for_write,
        )

        mark_encrypted_fields_for_write(self, "password_enc")
        if self.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            from netbox_proxbox.integrations.openbao_service import queue_service_secret

            queue_service_secret(
                self, "password", plaintext, user=user, request=request
            )
            self.password_enc = ""
            return
        self.password_enc = enc_helpers.encrypt(plaintext, key=key)

    def clear_password(self, *, user: object | None = None) -> None:
        """Clear the password selected by this credential's storage backend."""
        if self.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            from netbox_proxbox.integrations.openbao_service import clear_service_secret

            clear_service_secret(self, "password", user=user)
        self.clear_password_ciphertext()

    def clear_password_ciphertext(self) -> None:
        """Clear only legacy password ciphertext through the guarded write path."""
        from netbox_proxbox.services.encryption_recovery import (
            mark_encrypted_fields_for_write,
        )

        mark_encrypted_fields_for_write(self, "password_enc")
        self.password_enc = ""

    @sensitive_variables()
    def set_private_key(
        self,
        plaintext: str,
        *,
        key: str,
        user: object | None = None,
        request: object | None = None,
    ) -> None:
        from netbox_proxbox.services.encryption_recovery import (
            mark_encrypted_fields_for_write,
        )

        mark_encrypted_fields_for_write(self, "private_key_enc")
        if self.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            from netbox_proxbox.integrations.openbao_service import queue_service_secret

            queue_service_secret(
                self, "private_key", plaintext, user=user, request=request
            )
            self.private_key_enc = ""
            return
        self.private_key_enc = enc_helpers.encrypt(plaintext, key=key)

    def clear_private_key(self, *, user: object | None = None) -> None:
        """Clear the private key selected by this credential's storage backend."""
        if self.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            from netbox_proxbox.integrations.openbao_service import clear_service_secret

            clear_service_secret(self, "private_key", user=user)
        self.clear_private_key_ciphertext()

    def clear_private_key_ciphertext(self) -> None:
        """Clear only legacy key ciphertext through the guarded write path."""
        from netbox_proxbox.services.encryption_recovery import (
            mark_encrypted_fields_for_write,
        )

        mark_encrypted_fields_for_write(self, "private_key_enc")
        self.private_key_enc = ""

    @sensitive_variables()
    def get_password(self, *, key: str, user: object | None = None) -> str:
        if self.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            from netbox_proxbox.integrations.openbao_service import (
                resolve_service_secret,
            )

            return resolve_service_secret(self, "password", user=user)
        return enc_helpers.decrypt(self.password_enc, key=key)

    @sensitive_variables()
    def get_private_key(self, *, key: str, user: object | None = None) -> str:
        if self.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            from netbox_proxbox.integrations.openbao_service import (
                resolve_service_secret,
            )

            return resolve_service_secret(self, "private_key", user=user)
        return enc_helpers.decrypt(self.private_key_enc, key=key)
