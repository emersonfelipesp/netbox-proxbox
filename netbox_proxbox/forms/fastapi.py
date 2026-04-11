"""Define NetBox forms for configuring and filtering FastAPI backend endpoints."""

# Django Imports
from django import forms
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


class FastAPIEndpointForm(NetBoxModelForm):
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
        help_text="This will only be working from v0.0.7 and above. Token for the Proxbox Endpoint. If not provided, the Proxbox Endpoint will not be able to send messages to the client (user) browser.",
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
            "verify_ssl",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
            "token",
            "tags",
        )

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


class FastAPIEndpointImportForm(NetBoxModelImportForm):
    """CSV import mapping for bulk FastAPI endpoint creation."""

    ip_address = forms.CharField(
        required=False,
        help_text=_(
            "IP address in CIDR format, for example 192.0.2.10/24. Created automatically if it does not exist."
        ),
    )

    class Meta:
        model = FastAPIEndpoint
        fields = (
            "name",
            "domain",
            "ip_address",
            "port",
            "verify_ssl",
            "token",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
            "tags",
        )

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
