"""Define NetBox forms for Proxmox endpoint objects and list filtering."""

# Django Imports
from django import forms

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
from ..constants import OVERWRITE_FIELDS, SYNC_MODE_FIELDS
from ..models import ProxmoxEndpoint
from ..choices import ProxmoxEndpointEnvironmentChoices, ProxmoxModeChoices
from .settings import _parse_tenant_regex_rules, _sync_mode_choice_options

from .import_utils import validate_endpoint_import_headers
from ..models import ProxboxPluginSettings
from ..models.ssh_credential import (
    AUTH_METHOD_KEY,
    AUTH_METHOD_PASSWORD,
    SSH_CRED_SOURCE_CHOICES,
    SSH_CRED_SOURCE_DEDICATED,
    SSH_CRED_SOURCE_REUSE,
)


class ProxmoxEndpointSSHCredentialFormMixin(forms.Form):
    """Shared endpoint SSH credential controls for main and SSH tab forms."""

    defer_ssh_credential_clean = False
    ssh_credential_field_names = (
        "ssh_credential_source",
        "ssh_username",
        "ssh_port",
        "ssh_auth_method",
        "ssh_known_host_fingerprint",
        "ssh_password",
        "ssh_private_key",
        "clear_ssh_password",
        "clear_ssh_private_key",
    )

    ssh_credential_source = forms.ChoiceField(
        choices=SSH_CRED_SOURCE_CHOICES,
        required=True,
        label=_("SSH credential source"),
        help_text=_(
            "Use a dedicated SSH credential, or reuse this endpoint's "
            "Proxmox username/password for SSH. Reuse strips the realm "
            "(for example, root@pam becomes root); only @pam/PAM-backed "
            "users normally map to local SSH accounts."
        ),
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
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if not (instance and getattr(instance, "pk", None)):
            self.fields.pop("clear_ssh_password", None)
            self.fields.pop("clear_ssh_private_key", None)
            return
        if not getattr(instance, "ssh_password_enc", ""):
            self.fields.pop("clear_ssh_password", None)
        if not getattr(instance, "ssh_private_key_enc", ""):
            self.fields.pop("clear_ssh_private_key", None)

    def clean(self) -> dict[str, object]:
        """Validate complete endpoint SSH credentials before encryption."""
        super().clean()
        cleaned_data = self.cleaned_data
        if not self.defer_ssh_credential_clean:
            self._clean_ssh_credentials()
        return cleaned_data

    def _clean_ssh_credentials(self) -> None:
        """Validate the selected endpoint SSH credential source."""
        cleaned_data = self.cleaned_data
        instance = self.instance

        credential_source = (
            cleaned_data.get("ssh_credential_source")
            or getattr(
                instance,
                "ssh_credential_source",
                SSH_CRED_SOURCE_DEDICATED,
            )
            or SSH_CRED_SOURCE_DEDICATED
        )
        fingerprint = (cleaned_data.get("ssh_known_host_fingerprint") or "").strip()

        if credential_source == SSH_CRED_SOURCE_REUSE:
            endpoint_password = cleaned_data.get("password")
            if endpoint_password is None:
                endpoint_password = getattr(instance, "password", "")
            if not endpoint_password:
                self.add_error(
                    "ssh_credential_source",
                    _(
                        "Reusing endpoint credentials for SSH requires this "
                        "endpoint to store a password; token-only endpoints "
                        "cannot reuse SSH credentials."
                    ),
                )
            if not fingerprint:
                self.add_error(
                    "ssh_known_host_fingerprint",
                    _(
                        "Pinned host-key fingerprint is required when reusing "
                        "endpoint credentials for SSH."
                    ),
                )
            return

        password = cleaned_data.get("ssh_password") or ""
        private_key = cleaned_data.get("ssh_private_key") or ""
        clear_password = bool(cleaned_data.get("clear_ssh_password"))
        clear_private_key = bool(cleaned_data.get("clear_ssh_private_key"))

        has_password = bool(password) or (
            bool(getattr(instance, "ssh_password_enc", "")) and not clear_password
        )
        has_private_key = bool(private_key) or (
            bool(getattr(instance, "ssh_private_key_enc", "")) and not clear_private_key
        )

        username = (cleaned_data.get("ssh_username") or "").strip()
        has_any = any((username, fingerprint, has_password, has_private_key))
        if not has_any:
            return

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

        auth_method = cleaned_data.get("ssh_auth_method")
        if auth_method == AUTH_METHOD_KEY and not has_private_key:
            self.add_error(
                "ssh_private_key",
                _("Key authentication requires a stored SSH private key."),
            )
        if auth_method == AUTH_METHOD_PASSWORD and not has_password:
            self.add_error(
                "ssh_password",
                _("Password authentication requires a stored SSH password."),
            )
        if (
            password or private_key
        ) and not ProxboxPluginSettings.get_solo().encryption_key:
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

        if self.cleaned_data.get("ssh_credential_source") == SSH_CRED_SOURCE_REUSE:
            if commit:
                instance.save()
                self.save_m2m()
            return instance

        key = ProxboxPluginSettings.get_solo().encryption_key or ""

        if self.cleaned_data.get("clear_ssh_password"):
            instance.ssh_password_enc = ""
        if self.cleaned_data.get("clear_ssh_private_key"):
            instance.ssh_private_key_enc = ""
        password = self.cleaned_data.get("ssh_password") or ""
        private_key = self.cleaned_data.get("ssh_private_key") or ""
        if password:
            instance.set_ssh_password(password, key=key)
        if private_key:
            instance.set_ssh_private_key(private_key, key=key)

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
            "ip_address",
            "domain",
            "port",
            "username",
            "password",
            "token_name",
            "token_value",
            "verify_ssl",
            "enabled",
            "environment",
            "site",
            "tenant",
            "allowed_tenants",
            "tags",
            name="Identity and credentials",
        ),
        FieldSet("allow_writes", "access_methods", name="Access control"),
        FieldSet(
            *ProxmoxEndpointSSHCredentialFormMixin.ssh_credential_field_names,
            name="SSH credential access",
        ),
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Only expose the clear-credential checkboxes when there is something to clear."""
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if not (instance and getattr(instance, "pk", None)):
            self.fields.pop("clear_password", None)
            self.fields.pop("clear_token", None)
            return
        if not getattr(instance, "password", ""):
            self.fields.pop("clear_password", None)
        has_token = bool(getattr(instance, "token_name", "")) or bool(
            getattr(instance, "token_value", "")
        )
        if not has_token:
            self.fields.pop("clear_token", None)

    class Meta:
        model = ProxmoxEndpoint
        fields = (
            "name",
            "ip_address",
            "domain",
            "port",
            "username",
            "password",
            "token_name",
            "token_value",
            "verify_ssl",
            "enabled",
            "allow_writes",
            "access_methods",
            "environment",
            "site",
            "tenant",
            "allowed_tenants",
            "ssh_credential_source",
            "ssh_username",
            "ssh_port",
            "ssh_auth_method",
            "ssh_known_host_fingerprint",
            "tags",
        )

    def clean(self) -> dict[str, object]:
        """Require domain or IP, honour explicit credential clears, and enforce
        the password-or-complete-token invariant before save."""
        super().clean()
        cleaned_data = self.cleaned_data
        domain = (cleaned_data.get("domain") or "").strip()
        ip_address = cleaned_data.get("ip_address")

        if not domain and ip_address is None:
            self.add_error("domain", "Provide either a domain or an IP address.")
            self.add_error("ip_address", "Provide either a domain or an IP address.")

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
        if self.instance and self.instance.pk:
            if not clear_password and not cleaned_data.get("password"):
                cleaned_data["password"] = self.instance.password
            if not clear_token and not cleaned_data.get("token_value"):
                cleaned_data["token_value"] = self.instance.token_value

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

        self._clean_ssh_credentials()
        return cleaned_data


class ProxmoxEndpointSettingsForm(NetBoxModelForm):
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


class ProxmoxEndpointSSHSettingsForm(
    ProxmoxEndpointSSHCredentialFormMixin,
    NetBoxModelForm,
):
    """Endpoint-level SSH fallback credentials for browser terminal sessions."""

    fieldsets = (
        FieldSet(
            *ProxmoxEndpointSSHCredentialFormMixin.ssh_credential_field_names,
            name="SSH credential access",
        ),
    )

    class Meta:
        model = ProxmoxEndpoint
        fields = (
            "ssh_credential_source",
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


class ProxmoxEndpointImportForm(NetBoxModelImportForm):
    """CSV import mapping for bulk Proxmox endpoint creation."""

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
