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
from dcim.models import Site
from ipam.models import IPAddress
from tenancy.models import Tenant
from django.utils.translation import gettext as _

# Proxbox Imports
from ..constants import OVERWRITE_FIELDS
from ..models import ProxmoxEndpoint
from ..choices import ProxmoxModeChoices
from .settings import _parse_tenant_regex_rules

from .import_utils import validate_endpoint_import_headers


class ProxmoxEndpointForm(NetBoxModelForm):
    """
    Form for ProxmoxEndpoint model.
    It is used to CREATE and UPDATE ProxmoxEndpoint objects.
    """

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
    comments = CommentField()

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
            "site",
            "tenant",
            "tags",
        )

    def clean(self) -> dict[str, object]:
        """Require domain or IP before save (matches model validation)."""
        super().clean()
        cleaned_data = self.cleaned_data
        domain = (cleaned_data.get("domain") or "").strip()
        ip_address = cleaned_data.get("ip_address")

        if not domain and ip_address is None:
            self.add_error("domain", "Provide either a domain or an IP address.")
            self.add_error("ip_address", "Provide either a domain or an IP address.")

        # Keep stored secrets on edit when user submits blank masked fields.
        if self.instance and self.instance.pk:
            if not cleaned_data.get("password"):
                cleaned_data["password"] = self.instance.password
            if not cleaned_data.get("token_value"):
                cleaned_data["token_value"] = self.instance.token_value

        return cleaned_data


class ProxmoxEndpointSettingsForm(NetBoxModelForm):
    """Per-endpoint Proxmox-specific overrides exposed on the Settings tab.

    Connection tunables (timeout / retries) and overwrite flags live here so the
    main edit form keeps a tight focus on identity, network, and credentials.
    Overwrite fields are tri-state: empty = inherit from the global plugin setting.
    """

    class Meta:
        model = ProxmoxEndpoint
        fields = (
            "timeout",
            "max_retries",
            "retry_backoff",
            "enable_tenant_name_regex",
            "tenant_name_regex_rules",
            *OVERWRITE_FIELDS,
        )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        for name in OVERWRITE_FIELDS:
            label = name.removeprefix("overwrite_").replace("_", " ").capitalize()
            if name == "overwrite_vm_tags":
                label = "Merge VM tags"
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
        existing = getattr(instance, "tenant_name_regex_rules", None) if instance else None
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

    def clean_tenant_name_regex_rules(self) -> list[dict] | None:
        """Empty → None (inherit); '[]' → [] (explicit override)."""
        return _parse_tenant_regex_rules(
            self.cleaned_data.get("tenant_name_regex_rules"),
            allow_none=True,
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


class ProxmoxEndpointImportForm(NetBoxModelImportForm):
    """CSV import mapping for bulk Proxmox endpoint creation."""

    ip_address = forms.CharField(
        required=False,
        help_text=_(
            "IP address in CIDR format, for example 192.0.2.10/24. Created automatically if it does not exist."
        ),
    )
    mode = CSVChoiceField(choices=ProxmoxModeChoices, required=False)
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
            "version",
            "repoid",
            "username",
            "password",
            "token_name",
            "token_value",
            "verify_ssl",
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
