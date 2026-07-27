"""Define NetBox forms for configuring and filtering FastAPI backend endpoints."""

# Django Imports
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# NetBox Imports
from utilities.forms.fields import (
    DynamicModelChoiceField,
    CommentField,
)
from netbox.forms import (
    NetBoxModelForm,
    NetBoxModelFilterSetForm,
    NetBoxModelImportForm,
)
from ipam.models import IPAddress

# Proxbox Imports
from ..models import FastAPIEndpoint
from ..utils import resolve_ip_address_initial

from .import_utils import NullableCSVIntegerField, validate_endpoint_import_headers


class BackendKeyAdoptionFormMixin:
    """Persist virtual token fields through the model's shared key gate."""

    def save(self, commit: bool = True) -> FastAPIEndpoint:
        instance = super().save(commit=False)  # type: ignore[misc]
        submitted_token = (self.cleaned_data.get("token") or "").strip()  # type: ignore[attr-defined]
        if submitted_token:
            instance.token = submitted_token
        if commit:
            try:
                instance.save()
            except ValidationError as exc:
                from utilities.exceptions import AbortRequest

                messages = exc.message_dict.get("token", exc.messages)
                raise AbortRequest(" ".join(str(item) for item in messages)) from None
            self.save_m2m()  # type: ignore[attr-defined]
        return instance


class FastAPIEndpointForm(BackendKeyAdoptionFormMixin, NetBoxModelForm):
    """
    Form for FastAPIEndpoint model.
    It is used to CREATE and UPDATE FastAPIEndpoint objects.
    """

    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all(),
        required=False,
        help_text="Select NetBox IP Address. Fallback if domain name is not provided.",
        label="IP Address",
        quick_add=True,
    )
    token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            render_value=False, attrs={"autocomplete": "new-password"}
        ),
        help_text="Backend token for proxbox-api. Leave blank to keep the current value.",
        label="[BETA] Proxbox Backend Token",
    )
    use_websocket = forms.BooleanField(
        required=False,
        help_text="Choose or not to use WebSocket for the Proxbox Endpoint. If enabled, the Proxbox Endpoint will use WebSocket connection to send messages to the client (user) browser.",
        label="Use WebSocket",
    )
    websocket_domain = forms.CharField(
        required=False,
        help_text="Domain name of the WebSocket for the Proxbox Endpoint. The client (user) browser will connect to this domain to receive messages from the Proxbox Endpoint.",
        label="WebSocket Domain",
    )
    websocket_port = forms.IntegerField(
        required=False,
        help_text=(
            "⚠️ Advanced: leave blank to use the HTTP port. "
            "Only set this if your WebSocket endpoint listens on a different port than the HTTP endpoint."
        ),
        label="WebSocket Port (Advanced)",
    )
    server_side_websocket = forms.BooleanField(
        required=False,
        help_text="Choose or not to use server side WebSocket connection for the Proxbox Endpoint. This is experimental feature and may not work as expected. This way, client will not need to connect to the Proxbox Endpoint. Avoiding firewall rules to protect the Proxbox Endpoint.",
        label="[BETA] Server Side WebSocket",
    )

    comments = CommentField()

    class Meta:
        model = FastAPIEndpoint
        fields = (
            "name",
            "domain",
            "ip_address",
            "port",
            "use_https",
            "verify_ssl",
            "enabled",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
            "token",
            "tags",
        )
        help_texts = {
            "use_https": (
                "Use HTTPS to reach the ProxBox backend. Enable for the "
                "proxbox-api '*-nginx' image (TLS-only). Leave 'Verify SSL' "
                "unchecked when the backend uses a self-signed certificate."
            ),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Pre-fill loopback IP input when the add view is launched with a default."""
        super().__init__(*args, **kwargs)

        ip_address = resolve_ip_address_initial(self.initial.get("ip_address"))
        if ip_address is not None:
            self.initial["ip_address"] = ip_address

    def clean(self) -> dict[str, object]:
        """Require domain or IP for HTTP/WebSocket base URLs."""
        super().clean()
        cleaned_data = self.cleaned_data
        domain = (cleaned_data.get("domain") or "").strip()
        ip_address = cleaned_data.get("ip_address")

        if not domain and ip_address is None:
            self.add_error("domain", "Provide either a domain or an IP address.")
            self.add_error("ip_address", "Provide either a domain or an IP address.")

        return cleaned_data


class FastAPIEndpointImportForm(BackendKeyAdoptionFormMixin, NetBoxModelImportForm):
    """CSV import mapping for bulk FastAPI endpoint creation."""

    token = forms.CharField(required=False)
    ip_address = forms.CharField(
        required=False,
        help_text=_(
            "IP address in CIDR format, for example 192.0.2.10/24. Created automatically if it does not exist."
        ),
    )
    websocket_port = NullableCSVIntegerField(
        required=False,
        validators=FastAPIEndpoint._meta.get_field("websocket_port").validators,
        help_text=_("Optional WebSocket port. Leave blank to use the HTTP port."),
    )

    class Meta:
        model = FastAPIEndpoint
        fields = (
            "name",
            "domain",
            "ip_address",
            "port",
            "use_https",
            "verify_ssl",
            "enabled",
            "token",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
            "tags",
        )

    def clean(self) -> dict[str, object]:
        """Detect wrong endpoint exports before generic CSV header validation."""
        validate_endpoint_import_headers(self, expected="fastapi")
        return super().clean()

    def clean_ip_address(self) -> IPAddress | None:
        """Look up or auto-create the IPAddress so imports from other instances work."""
        raw = (self.cleaned_data.get("ip_address") or "").strip()
        if not raw:
            return None
        ip_obj, _created = IPAddress.objects.get_or_create(address=raw)
        return ip_obj


class FastAPIEndpointFilterForm(NetBoxModelFilterSetForm):
    """
    Filter form for FastAPIEndpoint model.
    It is used in the FastAPIEndpointListView.
    """

    model = FastAPIEndpoint
    name = forms.CharField(required=False)
    ip_address = forms.ModelMultipleChoiceField(
        queryset=IPAddress.objects.all(), required=False, help_text="Select IP Address"
    )
