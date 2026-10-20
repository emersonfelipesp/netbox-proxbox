"""Define NetBox forms for Proxmox endpoint objects and list filtering."""

from dataclasses import dataclass

# Django Imports
from django import forms
from django.core.exceptions import ObjectDoesNotExist, ValidationError

# NetBox Imports
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from netbox.forms import NetBoxModelImportForm
from utilities.forms.fields import (
    CommentField,
    CSVChoiceField,
    CSVModelChoiceField,
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from utilities.forms.rendering import FieldSet
from dcim.models import DeviceRole, Site
from ipam.models import IPAddress
from tenancy.models import Tenant
from django.utils.translation import gettext as _

# Proxbox Imports
from ..constants import OVERWRITE_FIELDS, RPC_FIELDS, SYNC_MODE_FIELDS
from ..models import ProxmoxEndpoint, ProxmoxEndpointService
from ..choices import (
    ProxmoxAccessMethodChoices,
    ProxmoxEndpointEnvironmentChoices,
    ProxmoxModeChoices,
)
from .settings import _parse_tenant_regex_rules, _sync_mode_choice_options

from .import_utils import validate_endpoint_import_headers
from .transport_defaults import SecureTransportImportDefaultsMixin
from ..models import ProxboxPluginSettings
from ..utils import encryption as enc_helpers
from ..models.ssh_credential import (
    AUTH_METHOD_KEY,
    AUTH_METHOD_PASSWORD,
    SSH_CRED_SOURCE_CHOICES,
    SSH_CRED_SOURCE_DEDICATED,
    SSH_CRED_SOURCE_REUSE,
    SSH_CRED_SOURCE_SERVICE,
)
from ..validators import validate_endpoint_node_device_name_template


@dataclass(frozen=True)
class _SSHSecretPresence:
    """Final dedicated SSH secret availability after submitted clear flags."""

    password: bool
    private_key: bool


@dataclass(frozen=True)
class _ServiceCredentialIntent:
    """Validation-time identity and storage state for one service credential."""

    service_id: int | None
    owner_id: int | None
    storage_backend: str | None
    password_reference: object | None
    private_key_reference: object | None


def _credential_source(cleaned_data: dict[str, object], instance: object) -> str:
    """Return the submitted or stored endpoint SSH credential source."""
    return str(
        cleaned_data.get("ssh_credential_source")
        or getattr(instance, "ssh_credential_source", SSH_CRED_SOURCE_DEDICATED)
        or SSH_CRED_SOURCE_DEDICATED
    )


def _secret_available(
    submitted: object,
    stored: object,
    *,
    clear: bool,
) -> bool:
    """Return final secret availability after replacement and clear intent."""
    return bool(submitted) or (bool(stored) and not clear)


def _dedicated_ssh_secret_presence(
    cleaned_data: dict[str, object],
    instance: object,
    *,
    uses_openbao: bool,
) -> _SSHSecretPresence:
    """Resolve final dedicated SSH password and private-key availability."""
    stored_password = bool(getattr(instance, "ssh_password_enc", "")) or (
        uses_openbao
        and bool(getattr(instance, "openbao_ssh_password_credential_uuid", None))
    )
    stored_private_key = bool(getattr(instance, "ssh_private_key_enc", "")) or (
        uses_openbao
        and bool(getattr(instance, "openbao_ssh_keypair_credential_uuid", None))
    )
    return _SSHSecretPresence(
        password=_secret_available(
            cleaned_data.get("ssh_password"),
            stored_password,
            clear=bool(cleaned_data.get("clear_ssh_password")),
        ),
        private_key=_secret_available(
            cleaned_data.get("ssh_private_key"),
            stored_private_key,
            clear=bool(cleaned_data.get("clear_ssh_private_key")),
        ),
    )


def _submitted_or_stored_endpoint_password(
    cleaned_data: dict[str, object], instance: object
) -> object:
    """Return a submitted endpoint password or fail-closed stored resolution."""
    password = cleaned_data.get("password")
    if password is not None:
        return password
    try:
        return getattr(instance, "password", "")
    except (enc_helpers.EncryptionError, ValidationError):
        return ""


class ProxmoxEndpointSSHCredentialFormMixin(forms.Form):
    """Shared endpoint SSH credential controls for main and SSH tab forms."""

    defer_ssh_credential_clean = False
    ssh_credential_field_names = (
        "ssh_credential_source",
        "ssh_service",
        "ssh_storage",
        "openbao_credential",
        "ssh_username",
        "ssh_port",
        "ssh_auth_method",
        "ssh_known_host_fingerprint",
        "ssh_password",
        "ssh_private_key",
        "clear_ssh_password",
        "clear_ssh_private_key",
    )

    ssh_clear_field_names = ("clear_ssh_password", "clear_ssh_private_key")

    ssh_credential_source = forms.ChoiceField(
        choices=SSH_CRED_SOURCE_CHOICES,
        required=True,
        label=_("SSH credential source"),
        help_text=_(
            "Use an application-service credential, a dedicated endpoint "
            "credential, or the endpoint's Proxmox username/password. Reuse strips the realm "
            "(for example, root@pam becomes root); only @pam/PAM-backed "
            "users normally map to local SSH accounts."
        ),
    )
    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all(),
        required=False,
        quick_add=True,
        label=_("IP address"),
        help_text=_("Endpoint IP address bound to the SSH application service."),
    )
    ssh_service = DynamicModelChoiceField(
        queryset=ProxmoxEndpointService.objects.all(),
        required=False,
        label=_("Application service"),
        help_text=_("Select an SSH service or leave blank to reuse or create one."),
    )
    ssh_storage = forms.ChoiceField(
        required=False,
        label=_("SSH credential storage"),
    )
    ssh_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"autocomplete": "new-password"},
        ),
        label=_("SSH password"),
        help_text=_(
            "Leave blank to keep the currently stored SSH password. Ignored when "
            "SSH credential source is 'Reuse endpoint username/password'."
        ),
    )
    ssh_private_key = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 8,
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
        label=_("SSH private key"),
        help_text=_(
            "Leave blank to keep the currently stored SSH private key. Ignored when "
            "SSH credential source is 'Reuse endpoint username/password'."
        ),
    )
    clear_ssh_password = forms.BooleanField(
        required=False,
        label=_("Clear stored SSH password on save"),
    )
    clear_ssh_private_key = forms.BooleanField(
        required=False,
        label=_("Clear stored SSH private key on save"),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Hide clear controls when no corresponding encrypted value exists."""
        self._validated_service_intent = None
        self._resolved_ssh_service = None
        self._request_user = kwargs.pop("request_user", None) or self._current_actor()
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        self._configure_service_chain_fields(instance)
        service_credential = self._service_credential(instance)
        if service_credential is not None:
            self.fields["ssh_username"].initial = service_credential.username
            self.fields["ssh_auth_method"].initial = service_credential.auth_method
        if not (instance and getattr(instance, "pk", None)):
            self.fields.pop("clear_ssh_password", None)
            self.fields.pop("clear_ssh_private_key", None)
            return
        from netbox_proxbox.integrations.openbao import endpoint_uses_openbao_storage

        uses_openbao = endpoint_uses_openbao_storage(instance)
        if instance.ssh_credential_source == SSH_CRED_SOURCE_SERVICE:
            has_ssh_password = instance.has_ssh_password
            has_ssh_private_key = instance.has_ssh_private_key
        else:
            has_ssh_password = bool(getattr(instance, "ssh_password_enc", "")) or (
                uses_openbao and bool(instance.openbao_ssh_password_credential_uuid)
            )
            has_ssh_private_key = bool(
                getattr(instance, "ssh_private_key_enc", "")
            ) or (uses_openbao and bool(instance.openbao_ssh_keypair_credential_uuid))
        if not has_ssh_password:
            self.fields.pop("clear_ssh_password", None)
        if not has_ssh_private_key:
            self.fields.pop("clear_ssh_private_key", None)

    @staticmethod
    def _current_actor() -> object | None:
        """Resolve NetBox's request-scoped actor across supported releases."""
        try:
            from netbox.context import current_request

            request = current_request.get()
        except (ImportError, LookupError):
            return None
        actor = getattr(request, "user", None)
        if not getattr(actor, "is_authenticated", False):
            return None
        if not getattr(actor, "is_active", False):
            return None
        return actor

    @staticmethod
    def _is_authenticated_actor(actor: object | None) -> bool:
        """Return whether an object can safely enter NetBox permission checks."""
        return bool(
            actor is not None
            and getattr(actor, "is_authenticated", False)
            and getattr(actor, "is_active", False)
            and hasattr(actor, "has_perm")
        )

    def _configure_service_chain_fields(self, instance: object) -> None:
        """Install only the storage choices available in this NetBox process."""
        from netbox_proxbox.choices import CredentialStorageBackendChoices
        from netbox_proxbox.integrations.openbao import (
            effective_credential_storage_backend,
            is_netbox_openbao_installed,
        )

        choices = [
            (
                CredentialStorageBackendChoices.LEGACY_ENCRYPTED,
                _("Encrypted in netbox-proxbox"),
            )
        ]
        from django.apps import apps

        installed = is_netbox_openbao_installed() and apps.is_installed(
            "netbox_openbao"
        )
        if installed:
            choices[0:0] = [
                ("openbao_new", _("OpenBao — create from values entered here")),
                ("openbao_existing", _("OpenBao — select existing credential")),
            ]
            credential_model = apps.get_model("netbox_openbao", "Credential")
            queryset = credential_model.objects.filter(
                credential_type__in=("ssh-password", "ssh-keypair")
            )
            if self._is_authenticated_actor(self._request_user):
                queryset = queryset.restrict(self._request_user, "reveal")
            else:
                queryset = queryset.none()
            self.fields["openbao_credential"] = DynamicModelChoiceField(
                queryset=queryset,
                required=False,
                query_params={"credential_type": ["ssh-password", "ssh-keypair"]},
                label=_("Existing OpenBao credential"),
            )
        else:
            self.fields.pop("openbao_credential", None)
        self.fields["ssh_storage"].choices = choices
        service_field = self.fields["ssh_service"]
        if getattr(instance, "pk", None):
            service_queryset = service_field.queryset.filter(endpoint=instance)
            if self._is_authenticated_actor(self._request_user) and hasattr(
                service_queryset, "restrict"
            ):
                service_queryset = service_queryset.restrict(self._request_user, "view")
            elif not self._is_authenticated_actor(self._request_user):
                service_queryset = service_queryset.none()
            service_field.queryset = service_queryset
            service_field.query_params = {"endpoint_id": instance.pk}
        else:
            service_field.queryset = service_field.queryset.none()
        current = self._service_credential(instance)
        if current is not None:
            initial = (
                "openbao_new"
                if current.storage_backend == CredentialStorageBackendChoices.OPENBAO
                else CredentialStorageBackendChoices.LEGACY_ENCRYPTED
            )
        elif effective_credential_storage_backend(instance) == "openbao":
            initial = "openbao_new"
        else:
            initial = CredentialStorageBackendChoices.LEGACY_ENCRYPTED
        self.fields["ssh_storage"].initial = initial
        self.initial["ssh_storage"] = initial
        if self._is_new_ssh_configuration(instance):
            self.initial["ssh_credential_source"] = SSH_CRED_SOURCE_SERVICE

    @staticmethod
    def _is_new_ssh_configuration(instance: object) -> bool:
        """Return whether the form should present the service source by default."""
        if not getattr(instance, "pk", None):
            return True
        return not any(
            (
                getattr(instance, "ssh_service_id", None),
                getattr(instance, "ssh_username", ""),
                getattr(instance, "ssh_known_host_fingerprint", ""),
                getattr(instance, "ssh_password_enc", ""),
                getattr(instance, "ssh_private_key_enc", ""),
                getattr(instance, "openbao_ssh_password_credential_uuid", None),
                getattr(instance, "openbao_ssh_keypair_credential_uuid", None),
            )
        )

    @staticmethod
    def _service_credential(instance: object) -> object | None:
        service = getattr(instance, "ssh_service", None)
        if service is None:
            return None
        try:
            return service.ssh_credential
        except (AttributeError, ObjectDoesNotExist):
            return None

    def clean(self) -> dict[str, object]:
        """Validate complete endpoint SSH credentials before encryption."""
        super().clean()
        cleaned_data = self.cleaned_data
        if not self.defer_ssh_credential_clean:
            self._clean_ssh_credentials()
        return cleaned_data

    def _post_clean(self) -> None:
        """Expose a submitted endpoint password only while the model validates.

        The password form field is write-only and is not copied to the model by
        Django's ``construct_instance()``. Reuse validation still belongs to
        ``ProxmoxEndpoint.clean()``, so provide its final form candidate through
        a transient attribute and remove the plaintext even when validation
        raises.
        """
        password_supplied = "password" in self.cleaned_data
        if password_supplied:
            self.instance._pending_password_for_validation = self.cleaned_data[
                "password"
            ]
        service_pending = (
            _credential_source(self.cleaned_data, self.instance)
            == SSH_CRED_SOURCE_SERVICE
        )
        dedicated_pending = (
            _credential_source(self.cleaned_data, self.instance)
            == SSH_CRED_SOURCE_DEDICATED
        )
        if service_pending:
            self.instance._pending_service_chain_validation = True
            self.instance._pending_service_credentials_ready = (
                self._submitted_service_credentials_ready()
            )
        if dedicated_pending:
            from netbox_proxbox.integrations.openbao import (
                endpoint_uses_openbao_storage,
            )

            presence = _dedicated_ssh_secret_presence(
                self.cleaned_data,
                self.instance,
                uses_openbao=endpoint_uses_openbao_storage(self.instance),
            )
            self.instance._pending_dedicated_ssh_secrets = presence
        try:
            super()._post_clean()
        finally:
            if password_supplied:
                del self.instance._pending_password_for_validation
            if service_pending:
                del self.instance._pending_service_chain_validation
                del self.instance._pending_service_credentials_ready
            if dedicated_pending:
                del self.instance._pending_dedicated_ssh_secrets

    def _clean_ssh_credentials(self) -> None:
        """Validate the selected endpoint SSH credential source."""
        cleaned_data = self.cleaned_data
        instance = self.instance
        credential_source = _credential_source(cleaned_data, instance)
        fingerprint = (cleaned_data.get("ssh_known_host_fingerprint") or "").strip()

        if credential_source == SSH_CRED_SOURCE_REUSE:
            # ``ProxmoxEndpoint.clean()`` owns reuse validation. ``_post_clean``
            # supplies the pending write-only password for create and rotation.
            return
        if credential_source == SSH_CRED_SOURCE_SERVICE:
            self._clean_service_ssh_credentials()
            return

        from netbox_proxbox.integrations.openbao import endpoint_uses_openbao_storage

        uses_openbao = endpoint_uses_openbao_storage(instance)
        presence = _dedicated_ssh_secret_presence(
            cleaned_data,
            instance,
            uses_openbao=uses_openbao,
        )
        if not self._validate_dedicated_ssh_identity(presence, fingerprint):
            return
        self._validate_dedicated_ssh_auth(presence)
        self._validate_dedicated_ssh_storage(uses_openbao=uses_openbao)

    def _clean_service_ssh_credentials(self) -> None:
        """Validate service resolution, creation authority, storage, and material."""
        from netbox_proxbox.services.ssh_service_chain import find_ssh_service

        access_method = self.cleaned_data.get("access_methods") or getattr(
            self.instance, "access_methods", None
        )
        if access_method != ProxmoxAccessMethodChoices.API_SSH:
            return
        if not self._is_authenticated_actor(self._request_user):
            self.add_error(
                "ssh_service",
                _(
                    "An authenticated request actor is required for SSH service changes."
                ),
            )
            return

        ip_address = self.cleaned_data.get("ip_address") or getattr(
            self.instance, "ip_address", None
        )
        if ip_address is None:
            self.add_error(
                "ip_address", _("An IP address is required for the SSH service.")
            )
            return
        port = int(self.cleaned_data.get("ssh_port") or 22)
        service = self.cleaned_data.get("ssh_service")
        visible = ProxmoxEndpointService.objects.all()
        if self._request_user is not None and hasattr(visible, "restrict"):
            visible = visible.restrict(self._request_user, "view")
        try:
            service = service or find_ssh_service(
                self.instance, ip_address, port, visible
            )
        except ValidationError as exc:
            self.add_error("ssh_service", exc.messages[0])
            return
        self._precheck_chain_write_access(service, ip_address)
        if service is not None:
            self._validate_selected_service(service, port)
        else:
            if not self._request_user.has_perm(
                "netbox_proxbox.add_proxmoxendpointservice"
            ):
                self.add_error(
                    "ssh_service",
                    _("You do not have permission to create an application service."),
                )
            try:
                from netbox_proxbox.services.ssh_service_chain import (
                    automatic_ssh_service_name,
                )

                self._automatic_ssh_service_name = automatic_ssh_service_name(
                    self.instance, port
                )
            except ValidationError as exc:
                self.add_error(
                    "ssh_service",
                    exc.messages[0],
                )
        self._resolved_ssh_service = service
        self._validated_service_intent = self._service_credential_intent(service)
        self._validate_service_secret_selection(service)

    def _validate_selected_service(self, service: object, port: int) -> None:
        """Validate one selected service and synchronize its port."""
        from netbox_proxbox.services.ssh_service_chain import service_ssh_port

        if service.endpoint_id != getattr(self.instance, "pk", None):
            self.add_error(
                "ssh_service",
                _("The selected service must belong to this endpoint."),
            )
        if service.protocol != "tcp":
            self.add_error("ssh_service", _("The selected SSH service must use TCP."))
        try:
            self.cleaned_data["ssh_port"] = service_ssh_port(service, port)
        except ValidationError as exc:
            self.add_error("ssh_service", exc.messages[0])

    def _validate_service_secret_selection(self, service: object | None) -> None:
        """Validate service storage selection and final auth material presence."""
        from netbox_proxbox.choices import CredentialStorageBackendChoices

        storage = self.cleaned_data.get("ssh_storage")
        if storage == "openbao_existing" and not self.cleaned_data.get(
            "openbao_credential"
        ):
            self.add_error(
                "openbao_credential", _("Select an existing OpenBao SSH credential.")
            )
        existing = self._credential_for_service(service)
        target_backend = (
            CredentialStorageBackendChoices.OPENBAO
            if storage in ("openbao_existing", "openbao_new")
            else CredentialStorageBackendChoices.LEGACY_ENCRYPTED
        )
        if (
            existing is not None
            and existing.storage_backend == CredentialStorageBackendChoices.OPENBAO
            and target_backend == CredentialStorageBackendChoices.LEGACY_ENCRYPTED
        ):
            self.add_error(
                "ssh_storage",
                _(
                    "Remove the OpenBao service credential before selecting local encrypted storage."
                ),
            )
            return
        if existing is not None and existing.storage_backend != target_backend:
            existing = None
        password, private_key = self._service_secret_presence(existing)
        auth_method = self.cleaned_data.get("ssh_auth_method")
        if not (self.cleaned_data.get("ssh_username") or "").strip():
            self.add_error(
                "ssh_username",
                _("SSH username is required for the application service."),
            )
        if not (self.cleaned_data.get("ssh_known_host_fingerprint") or "").strip():
            self.add_error(
                "ssh_known_host_fingerprint",
                _("Pinned host-key fingerprint is required for endpoint SSH."),
            )
        if auth_method == AUTH_METHOD_KEY and not private_key:
            self.add_error(
                "ssh_private_key", _("Key authentication requires a private key.")
            )
        if auth_method == AUTH_METHOD_PASSWORD and not password:
            self.add_error(
                "ssh_password", _("Password authentication requires a password.")
            )
        if storage == "legacy_encrypted" and (
            self.cleaned_data.get("ssh_password")
            or self.cleaned_data.get("ssh_private_key")
        ):
            if not ProxboxPluginSettings.get_solo().encryption_key:
                self.add_error(
                    "ssh_storage",
                    _(
                        "Configure ProxboxPluginSettings.encryption_key before storing SSH secrets."
                    ),
                )

    def _service_secret_presence(self, existing: object | None) -> tuple[bool, bool]:
        """Return final password and private-key availability for one service."""
        password = bool(self.cleaned_data.get("ssh_password")) or bool(
            existing
            and existing.has_password
            and not self.cleaned_data.get("clear_ssh_password")
        )
        private_key = bool(self.cleaned_data.get("ssh_private_key")) or bool(
            existing
            and existing.has_private_key
            and not self.cleaned_data.get("clear_ssh_private_key")
        )
        selected = self.cleaned_data.get("openbao_credential")
        if selected is not None:
            return (
                selected.credential_type == "ssh-password",
                selected.credential_type == "ssh-keypair",
            )
        return password, private_key

    def _validate_dedicated_ssh_identity(
        self,
        presence: _SSHSecretPresence,
        fingerprint: str,
    ) -> bool:
        """Validate dedicated SSH identity fields and return whether configured."""
        username = (self.cleaned_data.get("ssh_username") or "").strip()
        has_any = any((username, fingerprint, presence.password, presence.private_key))
        if not has_any:
            return False

        if not username:
            self.add_error(
                "ssh_username",
                _("SSH username is required when endpoint fallback SSH is configured."),
            )
        if not fingerprint:
            self.add_error(
                "ssh_known_host_fingerprint",
                _("Pinned host-key fingerprint is required for endpoint fallback SSH."),
            )
        return True

    @staticmethod
    def _credential_for_service(service: object | None) -> object | None:
        if service is None:
            return None
        try:
            return service.ssh_credential
        except (AttributeError, ObjectDoesNotExist):
            return None

    @classmethod
    def _service_credential_intent(
        cls, service: object | None
    ) -> _ServiceCredentialIntent:
        """Capture the selected service credential state used by validation."""
        credential = cls._credential_for_service(service)
        return _ServiceCredentialIntent(
            service_id=getattr(service, "pk", None),
            owner_id=getattr(credential, "pk", None),
            storage_backend=getattr(credential, "storage_backend", None),
            password_reference=getattr(
                credential, "openbao_password_credential_uuid", None
            ),
            private_key_reference=getattr(
                credential, "openbao_keypair_credential_uuid", None
            ),
        )

    def _submitted_service_credentials_ready(self) -> bool:
        """Return whether final submitted service credentials are usable."""
        service = self._resolved_ssh_service
        existing = self._credential_for_service(service)
        password = bool(self.cleaned_data.get("ssh_password")) or bool(
            existing
            and existing.has_password
            and not self.cleaned_data.get("clear_ssh_password")
        )
        private_key = bool(self.cleaned_data.get("ssh_private_key")) or bool(
            existing
            and existing.has_private_key
            and not self.cleaned_data.get("clear_ssh_private_key")
        )
        selected = self.cleaned_data.get("openbao_credential")
        if selected is not None:
            password = selected.credential_type == "ssh-password"
            private_key = selected.credential_type == "ssh-keypair"
        secret = (
            private_key
            if self.cleaned_data.get("ssh_auth_method") == AUTH_METHOD_KEY
            else password
        )
        return bool(
            self.cleaned_data.get("ssh_username")
            and self.cleaned_data.get("ssh_known_host_fingerprint")
            and secret
        )

    def _validate_dedicated_ssh_auth(self, presence: _SSHSecretPresence) -> None:
        """Require the secret selected by the dedicated SSH auth method."""
        auth_method = self.cleaned_data.get("ssh_auth_method")
        if auth_method == AUTH_METHOD_KEY and not presence.private_key:
            self.add_error(
                "ssh_private_key",
                _("Key authentication requires a stored SSH private key."),
            )
        if auth_method == AUTH_METHOD_PASSWORD and not presence.password:
            self.add_error(
                "ssh_password",
                _("Password authentication requires a stored SSH password."),
            )

    def _validate_dedicated_ssh_storage(self, *, uses_openbao: bool) -> None:
        """Require local encryption before accepting new dedicated SSH material."""
        password = self.cleaned_data.get("ssh_password") or ""
        private_key = self.cleaned_data.get("ssh_private_key") or ""
        if (
            (password or private_key)
            and not uses_openbao
            and not ProxboxPluginSettings.get_solo().encryption_key
        ):
            self.add_error(
                "ssh_private_key" if private_key else "ssh_password",
                _(
                    "Configure ProxboxPluginSettings.encryption_key before storing "
                    "endpoint SSH secrets."
                ),
            )

    def save(self, commit: bool = True) -> ProxmoxEndpoint:
        """Encrypt submitted dedicated SSH secrets and preserve blank inputs."""
        instance = super().save(commit=False)
        from netbox_proxbox.integrations.openbao import endpoint_uses_openbao_storage

        uses_openbao = endpoint_uses_openbao_storage(instance)
        self._attach_ssh_save_actor(instance)
        if commit and uses_openbao and not instance.pk:
            instance.save()
        credential_source = self.cleaned_data.get("ssh_credential_source")
        if credential_source != SSH_CRED_SOURCE_SERVICE or not commit:
            self._apply_primary_secret_inputs(instance)

        if credential_source == SSH_CRED_SOURCE_REUSE:
            return self._commit_ssh_form(instance, commit=commit)
        if credential_source == SSH_CRED_SOURCE_SERVICE:
            return self._save_service_chain(instance, commit=commit)

        key = ProxboxPluginSettings.get_solo().encryption_key or ""
        self._clear_dedicated_ssh_secret(
            instance,
            uses_openbao=uses_openbao,
            clear_field="clear_ssh_password",
            reference_field="openbao_ssh_password_credential_uuid",
            encrypted_field="ssh_password_enc",
        )
        self._clear_dedicated_ssh_secret(
            instance,
            uses_openbao=uses_openbao,
            clear_field="clear_ssh_private_key",
            reference_field="openbao_ssh_keypair_credential_uuid",
            encrypted_field="ssh_private_key_enc",
        )
        self._apply_dedicated_ssh_secret_inputs(instance, key=key)
        return self._commit_ssh_form(instance, commit=commit)

    def _save_service_chain(
        self, instance: ProxmoxEndpoint, *, commit: bool
    ) -> ProxmoxEndpoint:
        """Resolve the service chain and store credential metadata and material."""
        if not commit:
            return instance
        from django.db import transaction

        from netbox_proxbox.choices import CredentialStorageBackendChoices

        ip_address = self.cleaned_data["ip_address"]
        port = int(self.cleaned_data.get("ssh_port") or 22)
        storage = self.cleaned_data.get("ssh_storage")
        from netbox_proxbox.integrations.openbao_transaction import (
            current_endpoint_material_context,
            endpoint_material_transaction,
        )

        current_service_credential = self._service_credential(instance)
        needs_provider = storage in ("openbao_existing", "openbao_new") or bool(
            current_service_credential is not None
            and current_service_credential.storage_backend
            == CredentialStorageBackendChoices.OPENBAO
        )
        if needs_provider and current_endpoint_material_context() is None:
            with endpoint_material_transaction([instance]):
                return self._save_service_chain(instance, commit=commit)
        with transaction.atomic():
            if instance.pk is None:
                instance.save()
            else:
                ProxmoxEndpoint.objects.select_for_update().get(pk=instance.pk)
            service, credential, port = self._locked_service_chain_owner(
                instance, ip_address, port
            )
            instance.ssh_service = service
            instance.ssh_port = port
            instance.ssh_username = ""
            self._apply_primary_secret_inputs(instance)
            self._store_service_credential(credential, service, storage)
            service.ssh_credential = credential
            instance.full_clean()
            instance.save()
            self.save_m2m()
        return instance

    def _visible_service_queryset(self) -> object:
        """Return endpoint services visible to the authenticated request actor."""
        visible = ProxmoxEndpointService.objects.all()
        if self._request_user is not None and hasattr(visible, "restrict"):
            return visible.restrict(self._request_user, "view")
        return visible.none()

    def _locked_service_chain_owner(
        self, instance: object, ip_address: object, port: int
    ) -> tuple[object, object, int]:
        """Lock or create the validated service and its credential owner."""
        from django.core.exceptions import PermissionDenied
        from netbox_proxbox.models import ServiceSSHCredential
        from netbox_proxbox.services.ssh_service_chain import (
            automatic_ssh_service_name,
            build_ssh_service,
            find_ssh_service,
            service_ssh_port,
        )

        service = self.cleaned_data.get("ssh_service") or find_ssh_service(
            instance, ip_address, port, self._visible_service_queryset()
        )
        if service is None:
            self._assert_validated_service_intent(None, None)
            if not self._request_user.has_perm(
                "netbox_proxbox.add_proxmoxendpointservice"
            ):
                raise PermissionDenied(
                    "Creating an SSH application service requires add permission."
                )
            self._require_credential_write_access(None)
            service = build_ssh_service(
                instance,
                ip_address,
                port,
                name=automatic_ssh_service_name(instance, port),
            )
            return service, ServiceSSHCredential(service=service), port
        service = self._lock_selected_service(service, instance)
        credential = (
            ServiceSSHCredential.objects.select_for_update()
            .filter(service=service)
            .first()
        )
        self._assert_validated_service_intent(service, credential)
        self._require_credential_write_access(credential)
        port = service_ssh_port(service, port)
        if not service.ipaddresses.filter(pk=ip_address.pk).exists():
            self._require_service_change_access(service)
            service.ipaddresses.add(ip_address)
        return service, credential or ServiceSSHCredential(service=service), port

    def _precheck_chain_write_access(
        self, service: object | None, ip_address: object
    ) -> None:
        """Report missing credential or service write access as form errors."""
        from netbox_proxbox.models import ServiceSSHCredential

        if not self._is_authenticated_actor(self._request_user):
            self.add_error(
                "ssh_service",
                _(
                    "An authenticated request actor is required for SSH service changes."
                ),
            )
            return
        credential = None
        if service is not None:
            credential = ServiceSSHCredential.objects.filter(service=service).first()
            needs_binding = not service.ipaddresses.filter(pk=ip_address.pk).exists()
            if (
                needs_binding
                and not ProxmoxEndpointService.objects.restrict(
                    self._request_user, "change"
                )
                .filter(pk=service.pk)
                .exists()
            ):
                self.add_error(
                    "ssh_service",
                    _("You do not have permission to change this application service."),
                )
        if credential is None:
            allowed = self._request_user.has_perm(
                "netbox_proxbox.add_servicesshcredential"
            )
        else:
            allowed = (
                ServiceSSHCredential.objects.restrict(self._request_user, "change")
                .filter(pk=credential.pk)
                .exists()
            )
        if not allowed:
            self.add_error(
                "ssh_username",
                _("You do not have permission to store this SSH credential."),
            )

    def _require_service_change_access(self, service: object) -> None:
        """Binding a new address mutates the service, so require change access."""
        from django.core.exceptions import PermissionDenied

        allowed = ProxmoxEndpointService.objects.restrict(
            self._request_user, "change"
        ).filter(pk=service.pk)
        if not allowed.exists():
            raise PermissionDenied(
                "Binding this IP address requires change permission on the SSH service."
            )

    def _require_credential_write_access(self, credential: object | None) -> None:
        """Require add access for a new credential and change access for an existing one."""
        from django.core.exceptions import PermissionDenied
        from netbox_proxbox.models import ServiceSSHCredential

        if credential is None:
            allowed = self._request_user.has_perm(
                "netbox_proxbox.add_servicesshcredential"
            )
        else:
            allowed = (
                ServiceSSHCredential.objects.restrict(self._request_user, "change")
                .filter(pk=credential.pk)
                .exists()
            )
        if not allowed:
            raise PermissionDenied(
                "Storing this SSH credential requires permission on SSH credentials."
            )

    @staticmethod
    def _lock_selected_service(service: object, instance: object) -> object:
        """Lock the selected service without disclosing an unavailable object."""
        from django.core.exceptions import PermissionDenied

        try:
            return ProxmoxEndpointService.objects.select_for_update().get(
                pk=service.pk,
                endpoint=instance,
            )
        except ProxmoxEndpointService.DoesNotExist as exc:
            raise PermissionDenied(
                "The selected SSH application service is no longer available."
            ) from exc

    def _assert_validated_service_intent(
        self, service: object | None, credential: object | None
    ) -> None:
        """Reject owner, backend, or provider-reference drift since validation."""
        from utilities.exceptions import AbortRequest

        observed = _ServiceCredentialIntent(
            service_id=getattr(service, "pk", None),
            owner_id=getattr(credential, "pk", None),
            storage_backend=getattr(credential, "storage_backend", None),
            password_reference=getattr(
                credential, "openbao_password_credential_uuid", None
            ),
            private_key_reference=getattr(
                credential, "openbao_keypair_credential_uuid", None
            ),
        )
        if self._validated_service_intent != observed:
            raise AbortRequest(
                "The SSH service credential changed after validation. Review and submit the form again."
            )

    def _store_service_credential(
        self, credential: object, service: object, storage: str
    ) -> None:
        """Persist one complete credential and any selected provider material."""
        from netbox_proxbox.choices import CredentialStorageBackendChoices

        credential.username = self.cleaned_data.get("ssh_username") or ""
        credential.auth_method = self.cleaned_data.get("ssh_auth_method")
        credential.storage_backend = (
            CredentialStorageBackendChoices.OPENBAO
            if storage in ("openbao_existing", "openbao_new")
            else CredentialStorageBackendChoices.LEGACY_ENCRYPTED
        )
        if credential.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            from netbox_proxbox.integrations.openbao_service import (
                validate_service_storage,
            )

            validate_service_storage(credential)
        if storage == "openbao_existing":
            self._assign_existing_service_credential(credential, service)
        else:
            self._apply_service_secret_inputs(credential)
        credential.full_clean()
        credential.save()
        credential._openbao_expected_references = (
            credential.openbao_password_credential_uuid,
            credential.openbao_keypair_credential_uuid,
        )
        if storage == "openbao_new":
            from netbox_proxbox.integrations.openbao_service import (
                persist_service_material,
            )

            persist_service_material(credential, service, user=self._request_user)

    def _assign_existing_service_credential(
        self, credential: object, service: object
    ) -> None:
        """Clear prior slots and bind the selected authorized provider credential."""
        from netbox_proxbox.integrations.openbao_service import (
            assign_existing_service_credential,
        )

        credential.clear_password(user=self._request_user)
        credential.clear_private_key(user=self._request_user)
        assign_existing_service_credential(
            credential,
            service,
            self.cleaned_data["openbao_credential"],
            user=self._request_user,
        )

    def _apply_service_secret_inputs(self, credential: object) -> None:
        """Apply write-only service secrets without cross-backend fallback."""
        from netbox_proxbox.choices import CredentialStorageBackendChoices
        from netbox_proxbox.integrations.openbao_service import clear_service_secret

        password = self.cleaned_data.get("ssh_password") or ""
        private_key = self.cleaned_data.get("ssh_private_key") or ""
        if credential.storage_backend == CredentialStorageBackendChoices.OPENBAO:
            credential.clear_password_ciphertext()
            credential.clear_private_key_ciphertext()
            if (
                self.cleaned_data.get("clear_ssh_password") or password
            ) and credential.openbao_password_credential_uuid:
                clear_service_secret(credential, "password", user=self._request_user)
            if (
                self.cleaned_data.get("clear_ssh_private_key") or private_key
            ) and credential.openbao_keypair_credential_uuid:
                clear_service_secret(credential, "private_key", user=self._request_user)
        else:
            if credential.openbao_password_credential_uuid:
                clear_service_secret(credential, "password", user=self._request_user)
            if credential.openbao_keypair_credential_uuid:
                clear_service_secret(credential, "private_key", user=self._request_user)
            if self.cleaned_data.get("clear_ssh_password"):
                credential.clear_password(user=self._request_user)
            if self.cleaned_data.get("clear_ssh_private_key"):
                credential.clear_private_key(user=self._request_user)
        key = ProxboxPluginSettings.get_solo().encryption_key or ""
        if password:
            credential.set_password(password, key=key, user=self._request_user)
        if private_key:
            credential.set_private_key(private_key, key=key, user=self._request_user)

    def _attach_ssh_save_actor(self, instance: ProxmoxEndpoint) -> None:
        """Attach the request actor used by provider-owned credential writes."""
        if self._request_user is not None:
            instance._openbao_actor_user = self._request_user

    def _apply_primary_secret_inputs(self, instance: ProxmoxEndpoint) -> None:
        """Apply endpoint API secret replacements and explicit clears."""
        self._apply_primary_secret_input(
            instance,
            field="password",
            clear_field="clear_password",
        )
        self._apply_primary_secret_input(
            instance,
            field="token_value",
            clear_field="clear_token",
        )

    def _apply_primary_secret_input(
        self,
        instance: ProxmoxEndpoint,
        *,
        field: str,
        clear_field: str,
    ) -> None:
        """Apply one primary API secret without disturbing a blank edit input."""
        if field not in self.cleaned_data:
            return
        if self.cleaned_data.get(clear_field):
            setattr(instance, field, "")
            return
        value = self.cleaned_data.get(field)
        if value:
            setattr(instance, field, value)

    def _clear_dedicated_ssh_secret(
        self,
        instance: ProxmoxEndpoint,
        *,
        uses_openbao: bool,
        clear_field: str,
        reference_field: str,
        encrypted_field: str,
    ) -> None:
        """Apply one dedicated SSH clear through its selected storage backend."""
        if not self.cleaned_data.get(clear_field):
            return
        if uses_openbao:
            from netbox_proxbox.integrations.openbao import (
                clear_endpoint_openbao_credential,
            )

            clear_endpoint_openbao_credential(
                instance,
                reference_field,
                user=self._request_user,
            )
            return
        from netbox_proxbox.services.encryption_recovery import (
            mark_encrypted_fields_for_write,
        )

        mark_encrypted_fields_for_write(instance, encrypted_field)
        setattr(instance, encrypted_field, "")

    def _apply_dedicated_ssh_secret_inputs(
        self,
        instance: ProxmoxEndpoint,
        *,
        key: str,
    ) -> None:
        """Encrypt nonblank dedicated SSH password and private-key inputs."""
        password = self.cleaned_data.get("ssh_password") or ""
        private_key = self.cleaned_data.get("ssh_private_key") or ""
        if password:
            instance.set_ssh_password(password, key=key)
        if private_key:
            instance.set_ssh_private_key(private_key, key=key)

    def _commit_ssh_form(
        self,
        instance: ProxmoxEndpoint,
        *,
        commit: bool,
    ) -> ProxmoxEndpoint:
        """Persist the endpoint and form relations when requested."""
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ProxmoxEndpointForm(ProxmoxEndpointSSHCredentialFormMixin, NetBoxModelForm):
    """
    Form for ProxmoxEndpoint model.
    It is used to CREATE and UPDATE ProxmoxEndpoint objects.
    """

    defer_ssh_credential_clean = True

    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all(),
        help_text=_("Select a NetBox IP Address"),
        label=_("IP Address"),
        required=False,
        quick_add=True,
    )
    domain = forms.CharField(
        required=False,
        help_text=_(
            "Domain name of the Proxmox Endpoint (Cluster). It will try using the DNS name provided in IP Address if it is not empty."
        ),
        label=_("Domain"),
    )
    verify_ssl = forms.BooleanField(
        required=False,
        help_text=_(
            "Choose or not to verify SSL certificate of the Proxmox Endpoint. Only use this if you are sure about the SSL certificate of the Proxmox Endpoint."
        ),
        label=_("Verify SSL"),
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            render_value=False, attrs={"autocomplete": "new-password"}
        ),
        help_text=_(
            "Password for the Proxmox endpoint. Leave blank to keep the current value."
        ),
        label=_("Password"),
    )
    token_value = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            render_value=False, attrs={"autocomplete": "new-password"}
        ),
        help_text=_(
            "Secret value for the Proxmox API token. Leave blank to keep the current value."
        ),
        label=_("Token value"),
    )
    clear_password = forms.BooleanField(
        required=False,
        label=_("Clear stored password on save"),
        help_text=_(
            "Tick to delete the stored password when saving. Switch credentials cleanly "
            "(for example, moving from password to token auth) without leaving stale "
            "secrets in the database."
        ),
    )
    clear_token = forms.BooleanField(
        required=False,
        label=_("Clear stored API token on save"),
        help_text=_(
            "Tick to delete the stored token name AND token value when saving. The two "
            "fields are always cleared together so the row never holds a half-token."
        ),
    )
    site = DynamicModelChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label=_("Site"),
    )
    tenant = DynamicModelChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Tenant"),
    )
    allowed_tenants = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Allowed tenants"),
        help_text=_(
            "Explicitly grant endpoint access to these tenants. Leave empty to keep "
            "the endpoint in the default visibility pool."
        ),
    )
    comments = CommentField()

    fieldsets = (
        FieldSet(
            "name",
            "node_device_name_template",
            "ip_address",
            "domain",
            "port",
            "username",
            "password",
            "token_name",
            "token_value",
            "credential_storage_backend",
            "verify_ssl",
            "enabled",
            "environment",
            "site",
            "tenant",
            "allowed_tenants",
            "tags",
            name="Connection and credentials (read-only API access)",
        ),
        FieldSet(
            "allow_writes",
            "allow_packer_template_builds",
            name="Write access (opt-in)",
        ),
        FieldSet(
            "access_methods",
            name="Access methods",
        ),
        FieldSet(
            *ProxmoxEndpointSSHCredentialFormMixin.ssh_credential_field_names,
            name="SSH credential access (API + SSH only)",
        ),
        FieldSet(
            "cloud_image_ssh_target_node",
            "cloud_image_ssh_identity_file",
            name="Cloud Image bake binding",
        ),
        FieldSet(
            "service_monitoring_enabled",
            "service_monitoring_interval_minutes",
            "service_monitoring_units",
            name="Service monitoring (needs write access and API + SSH)",
        ),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Only expose the clear-credential checkboxes when there is something to clear."""
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        from netbox_proxbox.integrations.openbao import (
            hide_unavailable_openbao_choice,
        )

        hide_unavailable_openbao_choice(
            self.fields["credential_storage_backend"],
            current=getattr(instance, "credential_storage_backend", None),
        )
        if not (instance and getattr(instance, "pk", None)):
            self.fields.pop("clear_password", None)
            self.fields.pop("clear_token", None)
            return
        from netbox_proxbox.integrations.openbao import endpoint_uses_openbao_storage

        uses_openbao = endpoint_uses_openbao_storage(instance)
        has_password = bool(getattr(instance, "password_enc", "")) or (
            uses_openbao and bool(instance.openbao_password_credential_uuid)
        )
        if not has_password:
            self.fields.pop("clear_password", None)
        has_token = (
            bool(getattr(instance, "token_name", ""))
            or bool(getattr(instance, "token_value_enc", ""))
            or (uses_openbao and bool(instance.openbao_token_credential_uuid))
        )
        if not has_token:
            self.fields.pop("clear_token", None)
        if instance.password_encryption_state == "recovery_required":
            self.fields["password"].help_text = _(
                "Recovery required: the stored password cannot be decrypted. "
                "Enter a replacement or explicitly clear it."
            )
        if instance.token_value_encryption_state == "recovery_required":
            self.fields["token_value"].help_text = _(
                "Recovery required: the stored token value cannot be decrypted. "
                "Enter a replacement or explicitly clear it."
            )

    def clean_credential_storage_backend(self) -> str:
        """Reject a newly selected unavailable companion backend."""
        value = str(self.cleaned_data.get("credential_storage_backend") or "")
        current = str(getattr(self.instance, "credential_storage_backend", "") or "")
        from netbox_proxbox.integrations.openbao import (
            validate_storage_backend_selection,
        )

        try:
            validate_storage_backend_selection(value, current=current)
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages[0]) from exc
        return value

    class Meta:
        model = ProxmoxEndpoint
        fields = (
            "name",
            "node_device_name_template",
            "ip_address",
            "domain",
            "port",
            "username",
            "password",
            "token_name",
            "token_value",
            "credential_storage_backend",
            "verify_ssl",
            "enabled",
            "allow_writes",
            "allow_packer_template_builds",
            "access_methods",
            "service_monitoring_enabled",
            "service_monitoring_interval_minutes",
            "service_monitoring_units",
            "environment",
            "site",
            "tenant",
            "allowed_tenants",
            "ssh_credential_source",
            "ssh_service",
            "ssh_username",
            "ssh_port",
            "ssh_auth_method",
            "ssh_known_host_fingerprint",
            "tags",
            "cloud_image_ssh_target_node",
            "cloud_image_ssh_identity_file",
        )

    def clean_node_device_name_template(self) -> str:
        """Validate the effective template against this endpoint's inventory."""

        template = str(self.cleaned_data.get("node_device_name_template") or "").strip()
        instance = getattr(self, "instance", None)
        validate_endpoint_node_device_name_template(
            template,
            endpoint_id=getattr(instance, "pk", None),
            endpoint_name=str(
                self.cleaned_data.get("name") or getattr(instance, "name", "")
            ),
        )
        return template

    def clean(self) -> dict[str, object]:
        """Require domain or IP, honour explicit credential clears, and enforce
        the password-or-complete-token invariant before save."""
        instance = getattr(self, "instance", None)
        if instance is not None and self._request_user is not None:
            instance._openbao_actor_user = self._request_user
        super().clean()
        cleaned_data = self.cleaned_data
        domain = (cleaned_data.get("domain") or "").strip()
        ip_address = cleaned_data.get("ip_address")

        if not domain and ip_address is None:
            self.add_error("domain", "Provide either a domain or an IP address.")
            self.add_error("ip_address", "Provide either a domain or an IP address.")

        self._clean_cloud_image_ssh_target(instance, domain, ip_address)

        clear_password = bool(cleaned_data.get("clear_password"))
        clear_token = bool(cleaned_data.get("clear_token"))

        # Explicit clears win over both submitted blanks and the preserve branch.
        if clear_password:
            cleaned_data["password"] = ""
        if clear_token:
            cleaned_data["token_name"] = ""
            cleaned_data["token_value"] = ""

        # Keep stored secrets on edit when user submits blank masked fields,
        # unless they explicitly cleared them above.
        self._preserve_primary_secrets()

        self._validate_primary_credentials()
        if not self._ssh_input_ignored():
            self._clean_ssh_credentials()
        self._clean_service_monitoring()
        self._validate_storage_prerequisites()
        self._discard_ssh_input_when_api_only()
        return cleaned_data

    def _clean_cloud_image_ssh_target(
        self, instance: object, domain: str, ip_address: object
    ) -> None:
        """Require the selected bake node to resolve to the endpoint SSH host."""
        gates_open = all(
            (
                bool(self.cleaned_data.get("enabled")),
                self.cleaned_data.get("access_methods")
                == ProxmoxAccessMethodChoices.API_SSH,
                bool(self.cleaned_data.get("allow_writes")),
                bool(self.cleaned_data.get("allow_packer_template_builds")),
            )
        )
        if not gates_open:
            return
        target_node = str(
            self.cleaned_data.get("cloud_image_ssh_target_node") or ""
        ).strip()
        if not target_node:
            return
        from netbox_proxbox.cloud_image_ssh import cloud_image_ssh_target_matches_host

        candidate = ProxmoxEndpoint(
            domain=domain,
            ip_address=ip_address,
            ssh_credential_source=_credential_source(self.cleaned_data, instance),
        )
        if not cloud_image_ssh_target_matches_host(
            instance, target_node=target_node, ssh_host=candidate.ssh_host
        ):
            self.add_error(
                "cloud_image_ssh_target_node",
                "Select an inventory node whose address matches the endpoint SSH host.",
            )

    def _ssh_input_ignored(self) -> bool:
        """Return whether the submitted access method makes SSH input irrelevant."""
        return self.cleaned_data.get("access_methods") == ProxmoxAccessMethodChoices.API

    def _discard_ssh_input_when_api_only(self) -> None:
        """Ignore every SSH input, and its errors, for an API-only endpoint.

        API-only endpoints never use SSH, so SSH fields must not block saving.
        Dropping the keys from ``cleaned_data`` also keeps the model from
        copying submitted values onto the instance, so stored SSH settings
        stay untouched until the access method is switched to API + SSH. The two
        "clear stored SSH secret" requests are explicit operator intent rather
        than SSH configuration. Dedicated clears remain supported. A service
        clear requires its separate credential settings and is rejected here
        rather than silently clearing the wrong owner.
        """
        if not self._ssh_input_ignored():
            return
        self._reject_api_only_service_secret_clears()
        for name in ProxmoxEndpointSSHCredentialFormMixin.ssh_credential_field_names:
            if name in ProxmoxEndpointSSHCredentialFormMixin.ssh_clear_field_names:
                continue
            self._errors.pop(name, None)
            self.cleaned_data.pop(name, None)

    def _reject_api_only_service_secret_clears(self) -> None:
        """Refuse a clear whose stored service owner cannot use this save path."""
        if (
            getattr(self.instance, "ssh_credential_source", None)
            != SSH_CRED_SOURCE_SERVICE
        ):
            return
        for name in ProxmoxEndpointSSHCredentialFormMixin.ssh_clear_field_names:
            if self.cleaned_data.get(name):
                self.add_error(
                    name,
                    _(
                        "API-only edits cannot clear the selected SSH service credential. "
                        "Clear it through the SSH credential settings before changing the access method."
                    ),
                )

    def _preserve_primary_secrets(self) -> None:
        """Preserve masked secrets without requesting an absent unused method."""
        from netbox_proxbox.integrations.openbao import resolve_endpoint_api_secret

        if not self.instance or not self.instance.pk:
            return
        for field, clear in (
            ("password", "clear_password"),
            ("token_value", "clear_token"),
        ):
            if self.cleaned_data.get(clear) or self.cleaned_data.get(field):
                continue
            try:
                self.cleaned_data[field] = resolve_endpoint_api_secret(
                    self.instance,
                    field,
                    token_selected=bool(
                        (self.cleaned_data.get("token_name") or "").strip()
                    ),
                )
            except (enc_helpers.EncryptionError, ValidationError) as exc:
                self.add_error(field, str(getattr(exc, "messages", [exc])[0]))

    def _validate_primary_credentials(self) -> None:
        """Require a password or complete token pair after preservation/clears."""
        cleaned_data = self.cleaned_data

        # Invariant: row must have either a password or a complete (token_name,
        # token_value) pair. Half-tokens are rejected.
        final_password = cleaned_data.get("password") or ""
        final_token_name = (cleaned_data.get("token_name") or "").strip()
        final_token_value = cleaned_data.get("token_value") or ""
        has_password = bool(final_password)
        has_token_pair = bool(final_token_name) and bool(final_token_value)
        has_half_token = bool(final_token_name) ^ bool(final_token_value)

        if has_half_token:
            if not final_token_name:
                self.add_error(
                    "token_name",
                    _("Token name is required when a token value is set."),
                )
            if not final_token_value:
                self.add_error(
                    "token_value",
                    _("Token value is required when a token name is set."),
                )
        if not has_password and not has_token_pair:
            msg = _(
                "Provide either a password or a complete API token "
                "(both token name and token value)."
            )
            self.add_error("password", msg)
            self.add_error("token_name", msg)

    def _validate_storage_prerequisites(self) -> None:
        """Attach selected-store configuration failures to the form fields."""
        cleaned_data = self.cleaned_data
        from netbox_proxbox.integrations.openbao import (
            validate_write_mode_openbao_requirements,
        )

        try:
            validate_write_mode_openbao_requirements(
                self.instance,
                allow_writes=bool(cleaned_data.get("allow_writes")),
                storage_backend=cleaned_data.get("credential_storage_backend") or None,
            )
            if cleaned_data.get("password") or cleaned_data.get("token_value"):
                from netbox_proxbox.integrations.openbao import (
                    validate_openbao_storage_available,
                )

                validate_openbao_storage_available(
                    self.instance,
                    storage_backend=cleaned_data.get("credential_storage_backend")
                    or None,
                )
        except ValidationError as exc:
            if hasattr(exc, "error_dict"):
                for field, messages in exc.error_dict.items():
                    for message in messages:
                        self.add_error(field, message)
            else:
                self.add_error("credential_storage_backend", exc.messages[0])

    def _clean_service_monitoring(self) -> None:
        """Mirror the model eligibility gate using submitted credential values."""
        cleaned_data = self.cleaned_data
        if not cleaned_data.get("service_monitoring_enabled"):
            return

        base_eligible = (
            bool(cleaned_data.get("allow_writes"))
            and cleaned_data.get("access_methods") == ProxmoxAccessMethodChoices.API_SSH
            and self._submitted_service_monitoring_credentials_ready()
        )
        actively_enabling = not bool(
            getattr(self.instance, "pk", None)
            and getattr(self.instance, "service_monitoring_enabled", False)
        )
        if actively_enabling and not base_eligible:
            self.add_error(
                "service_monitoring_enabled",
                _(
                    "Requires write permission (allow_writes), SSH access "
                    "(api_ssh), and a registered SSH credential."
                ),
            )

    def _submitted_service_monitoring_credentials_ready(self) -> bool:
        """Return whether submitted endpoint SSH credentials are complete."""
        cleaned_data = self.cleaned_data
        instance = self.instance
        credential_source = _credential_source(cleaned_data, instance)
        domain = cleaned_data.get("domain") or getattr(instance, "domain", "") or ""
        ip_address = cleaned_data.get("ip_address") or getattr(
            instance,
            "ip_address",
            None,
        )
        host = str(domain or ip_address or "").strip()
        fingerprint = (cleaned_data.get("ssh_known_host_fingerprint") or "").strip()

        if credential_source == SSH_CRED_SOURCE_REUSE:
            return self._reused_monitoring_credentials_ready(host, fingerprint)
        if credential_source == SSH_CRED_SOURCE_SERVICE:
            return bool(
                host and fingerprint and self._submitted_service_credentials_ready()
            )
        return self._dedicated_monitoring_credentials_ready(host, fingerprint)

    def _reused_monitoring_credentials_ready(
        self,
        host: str,
        fingerprint: str,
    ) -> bool:
        """Return reuse-mode monitoring readiness from final form values."""
        username = (
            self.cleaned_data.get("username")
            or getattr(self.instance, "username", "")
            or ""
        )
        effective_username = str(username).split("@", 1)[0].strip()
        password = _submitted_or_stored_endpoint_password(
            self.cleaned_data,
            self.instance,
        )
        return bool(host and fingerprint and effective_username and password)

    def _dedicated_monitoring_credentials_ready(
        self,
        host: str,
        fingerprint: str,
    ) -> bool:
        """Return dedicated-mode monitoring readiness from final form values."""
        username = (self.cleaned_data.get("ssh_username") or "").strip()
        from netbox_proxbox.integrations.openbao import endpoint_uses_openbao_storage

        presence = _dedicated_ssh_secret_presence(
            self.cleaned_data,
            self.instance,
            uses_openbao=endpoint_uses_openbao_storage(self.instance),
        )
        has_secret = (
            presence.private_key
            if self.cleaned_data.get("ssh_auth_method") == AUTH_METHOD_KEY
            else presence.password
        )
        return bool(host and username and fingerprint and has_secret)


class ExcludedFieldErrorsMixin(forms.Form):
    """Report model errors for fields this form omits as non-field errors.

    ``ProxmoxEndpoint.clean()`` attaches errors to fields such as
    ``credential_storage_backend``. Django raises ``ValueError`` when a model
    error names a field that a narrow form does not declare.
    """

    def _update_errors(self, errors: ValidationError) -> None:
        from django.core.exceptions import NON_FIELD_ERRORS

        if hasattr(errors, "error_dict"):
            remapped: dict[str, list[ValidationError]] = {}
            for field, messages in errors.error_dict.items():
                known = field == NON_FIELD_ERRORS or field in self.fields
                remapped.setdefault(field if known else NON_FIELD_ERRORS, []).extend(
                    messages
                )
            errors = ValidationError(remapped)
        super()._update_errors(errors)


class ProxmoxEndpointSettingsForm(ExcludedFieldErrorsMixin, NetBoxModelForm):
    """Per-endpoint Proxmox-specific overrides exposed on the Settings tab.

    Connection tunables (timeout / retries) and overwrite flags live here so the
    main edit form keeps a tight focus on identity, network, and credentials.
    Overwrite fields are tri-state: empty = inherit from the global plugin setting.
    """

    default_role_qemu = DynamicModelChoiceField(
        queryset=DeviceRole.objects.all(),
        required=False,
        query_params={"vm_role": "true"},
        label=_("Default QEMU VM role"),
        help_text=_(
            "Per-endpoint override for the QEMU VM role. Wins over the plugin-global "
            "default. Leave blank to inherit."
        ),
    )
    default_role_lxc = DynamicModelChoiceField(
        queryset=DeviceRole.objects.all(),
        required=False,
        query_params={"vm_role": "true"},
        label=_("Default LXC container role"),
        help_text=_(
            "Per-endpoint override for the LXC container role. Wins over the "
            "plugin-global default. Leave blank to inherit."
        ),
    )

    class Meta:
        model = ProxmoxEndpoint
        fields = (
            "node_device_name_template",
            "timeout",
            "max_retries",
            "retry_backoff",
            "default_role_qemu",
            "default_role_lxc",
            "enable_tenant_name_regex",
            "tenant_name_regex_rules",
            "enable_tenant_tag_assignment",
            "enable_tenant_from_cluster",
            *SYNC_MODE_FIELDS,
            *OVERWRITE_FIELDS,
            *RPC_FIELDS,
        )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        sync_mode_labels = {
            "sync_mode_vm": "VM sync mode",
            "sync_mode_vm_template": "VM template sync mode",
            "sync_mode_vm_interface": "VM interface sync mode",
            "sync_mode_mac": "MAC address sync mode",
            "sync_mode_cluster": "Cluster sync mode",
            "sync_mode_node": "Node sync mode",
            "sync_mode_storage": "Storage sync mode",
            "sync_mode_sdn": "SDN sync mode",
            "sync_mode_sdn_bgp": "SDN BGP projection sync mode",
            "sync_mode_ip_address": "IP address sync mode",
        }
        for name in SYNC_MODE_FIELDS:
            self.fields[name] = forms.ChoiceField(
                required=False,
                choices=_sync_mode_choice_options(include_inherit=True),
                label=_(sync_mode_labels[name]),
                help_text=_(
                    "Leave blank to inherit the global Proxbox plugin setting."
                ),
            )
        for name in OVERWRITE_FIELDS:
            label = name.removeprefix("overwrite_").replace("_", " ").capitalize()
            if name == "overwrite_vm_tags":
                label = "Merge VM tags"
            elif name == "overwrite_vm_proxmox_tags":
                label = "Sync Proxmox tags"
            self.fields[name] = forms.NullBooleanField(
                required=False,
                widget=forms.NullBooleanSelect,
                label=_(label),
                help_text=_(
                    "Leave blank to inherit the global Proxbox plugin setting."
                ),
            )
        self.fields["rpc_enabled"] = forms.NullBooleanField(
            required=False,
            widget=forms.NullBooleanSelect,
            label=_("RPC enabled (override)"),
            help_text=_(
                "Per-endpoint override for netbox-rpc operations against this "
                "endpoint. Leave blank to inherit the global netbox-rpc setting "
                "(per-endpoint wins when set, but netbox-rpc must be installed)."
            ),
        )
        self.fields["enable_tenant_name_regex"] = forms.NullBooleanField(
            required=False,
            widget=forms.NullBooleanSelect,
            label=_("Enable tenant regex (override)"),
            help_text=_(
                "Per-endpoint override for the global tenant-regex toggle. "
                "Leave blank to inherit."
            ),
        )
        # Render the JSON list as a Textarea; empty input => inherit, "[]" => override.
        import json as _json

        instance = kwargs.get("instance") or getattr(self, "instance", None)
        existing = (
            getattr(instance, "tenant_name_regex_rules", None) if instance else None
        )
        initial = "" if existing is None else _json.dumps(existing, indent=2)
        self.fields["tenant_name_regex_rules"] = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={"rows": 6, "cols": 60}),
            initial=initial,
            label=_("Tenant regex rules (override, JSON)"),
            help_text=_(
                "JSON list. Leave blank to inherit the global list. Use '[]' to "
                "explicitly disable all global rules for this endpoint."
            ),
        )
        self.fields["enable_tenant_tag_assignment"] = forms.NullBooleanField(
            required=False,
            widget=forms.NullBooleanSelect,
            label=_("Enable tenant tag assignment (override)"),
            help_text=_(
                "Per-endpoint override for the global tenant tag-assignment toggle. "
                "Leave blank to inherit."
            ),
        )
        self.fields["enable_tenant_from_cluster"] = forms.NullBooleanField(
            required=False,
            widget=forms.NullBooleanSelect,
            label=_("Enable tenant assignment from cluster (override)"),
            help_text=_(
                "Per-endpoint override for the global tenant cluster-inheritance "
                "toggle. Leave blank to inherit."
            ),
        )

    def clean_tenant_name_regex_rules(self) -> list[dict] | None:
        """Empty → None (inherit); '[]' → [] (explicit override)."""
        return _parse_tenant_regex_rules(
            self.cleaned_data.get("tenant_name_regex_rules"),
            allow_none=True,
        )

    def clean_node_device_name_template(self) -> str:
        """Apply the same inventory-aware validation as the main edit form."""

        template = str(self.cleaned_data.get("node_device_name_template") or "").strip()
        instance = self.instance
        validate_endpoint_node_device_name_template(
            template,
            endpoint_id=instance.pk,
            endpoint_name=str(instance.name),
        )
        return template


class ProxmoxEndpointSSHSettingsForm(
    ExcludedFieldErrorsMixin,
    ProxmoxEndpointSSHCredentialFormMixin,
    NetBoxModelForm,
):
    """Endpoint-level SSH fallback credentials for browser terminal sessions."""

    fieldsets = (
        FieldSet(
            "ip_address",
            *ProxmoxEndpointSSHCredentialFormMixin.ssh_credential_field_names,
            name="SSH credential access",
        ),
    )

    class Meta:
        model = ProxmoxEndpoint
        fields = (
            "ssh_credential_source",
            "ip_address",
            "ssh_service",
            "ssh_username",
            "ssh_port",
            "ssh_auth_method",
            "ssh_known_host_fingerprint",
        )


class ProxmoxEndpointFilterForm(NetBoxModelFilterSetForm):
    """
    Filter form for ProxmoxEndpoint model.
    It is used in the ProxmoxEndpointListView.
    """

    model = ProxmoxEndpoint
    name = forms.CharField(required=False)
    ip_address = forms.ModelMultipleChoiceField(
        queryset=IPAddress.objects.all(), required=False, help_text="Select IP Address"
    )
    mode = forms.MultipleChoiceField(choices=ProxmoxModeChoices, required=False)
    environment = forms.MultipleChoiceField(
        choices=ProxmoxEndpointEnvironmentChoices, required=False
    )
    ssh_credential_source = forms.MultipleChoiceField(
        choices=SSH_CRED_SOURCE_CHOICES,
        required=False,
        label=_("SSH credential source"),
    )
    site = DynamicModelMultipleChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label=_("Site"),
    )
    tenant = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Tenant"),
    )
    allowed_tenants = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Allowed tenants"),
    )


class ProxmoxEndpointImportForm(
    SecureTransportImportDefaultsMixin, NetBoxModelImportForm
):
    """CSV import mapping for bulk Proxmox endpoint creation."""

    secure_default_fields = ("verify_ssl",)

    password = forms.CharField(required=False)
    token_value = forms.CharField(required=False)
    ip_address = forms.CharField(
        required=False,
        help_text=_(
            "IP address in CIDR format, for example 192.0.2.10/24. Created automatically if it does not exist."
        ),
    )
    mode = CSVChoiceField(choices=ProxmoxModeChoices, required=False)
    environment = CSVChoiceField(
        choices=ProxmoxEndpointEnvironmentChoices, required=False
    )
    site = CSVModelChoiceField(
        queryset=Site.objects.all(),
        to_field_name="slug",
        required=False,
        label=_("Site"),
    )
    tenant = CSVModelChoiceField(
        queryset=Tenant.objects.all(),
        to_field_name="slug",
        required=False,
        label=_("Tenant"),
    )

    class Meta:
        model = ProxmoxEndpoint
        fields = (
            "name",
            "node_device_name_template",
            "domain",
            "ip_address",
            "port",
            "mode",
            "environment",
            "version",
            "repoid",
            "username",
            "password",
            "token_name",
            "token_value",
            "verify_ssl",
            "enabled",
            "timeout",
            "max_retries",
            "retry_backoff",
            *OVERWRITE_FIELDS,
            "site",
            "tenant",
            "tags",
        )

    def clean(self) -> dict[str, object]:
        """Detect wrong endpoint exports before generic CSV header validation."""
        validate_endpoint_import_headers(self, expected="proxmox")
        return super().clean()

    def clean_ip_address(self) -> IPAddress | None:
        """Look up or auto-create the IPAddress so imports from other instances work."""
        raw = (self.cleaned_data.get("ip_address") or "").strip()
        if not raw:
            return None
        ip_obj, _created = IPAddress.objects.get_or_create(address=raw)
        return ip_obj
