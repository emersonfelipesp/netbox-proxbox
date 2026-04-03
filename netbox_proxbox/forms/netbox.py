"""Define NetBox forms for remote NetBox endpoints and token selection."""

# Django Imports
from django import forms

# NetBox Imports
from utilities.forms.fields import DynamicModelChoiceField, CommentField
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from ipam.models import IPAddress
from users.models import Token

# Proxbox Imports
from ..choices import NetBoxTokenVersionChoices
from ..models import NetBoxEndpoint
from ..utils import resolve_ip_address_initial


class NetBoxEndpointForm(NetBoxModelForm):
    """
    Form for NetBoxEndpoint model.
    It is used to CREATE and UPDATE NetBoxEndpoint objects.
    """

    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all(),
        required=False,
        help_text="Select IP Address",
        label="IP Address",
        quick_add=True,
    )

    token = DynamicModelChoiceField(
        queryset=Token.objects.all(),
        required=False,
        help_text="Choose an existing NetBox v1 API token. For NetBox v2 authentication, provide token key and token secret below.",
        label="API Token",
        quick_add=True,
    )

    token_version = forms.ChoiceField(
        choices=NetBoxTokenVersionChoices,
        initial=NetBoxTokenVersionChoices.V1,
        required=True,
        help_text="Select whether this endpoint uses a NetBox v1 token or v2 token credentials.",
        label="Token Version",
    )

    token_key = forms.CharField(
        required=False,
        help_text="Enter the NetBox v2 token key when not selecting an existing API token.",
        label="Token Key",
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )

    token_secret = forms.CharField(
        required=False,
        help_text="Enter the NetBox v2 token secret when not selecting an existing API token.",
        label="Token Secret",
        widget=forms.PasswordInput(
            render_value=True, attrs={"autocomplete": "new-password"}
        ),
    )

    comments = CommentField()

    class Meta:
        model = NetBoxEndpoint
        fields = (
            "name",
            "domain",
            "ip_address",
            "port",
            "token_version",
            "token",
            "token_key",
            "token_secret",
            "verify_ssl",
            "tags",
        )

    def __init__(self, *args, **kwargs):
        """Pre-select token version when editing an endpoint with a linked token."""
        super().__init__(*args, **kwargs)

        ip_address = resolve_ip_address_initial(self.initial.get("ip_address"))
        if ip_address is not None:
            self.initial["ip_address"] = ip_address

        token = getattr(self.instance, "token", None)
        if token is not None:
            self.initial["token_version"] = self._token_version_from_token(token)

    @staticmethod
    def _token_version_from_token(token: Token) -> str:
        """Map a NetBox ``Token`` row to v1 or v2 choice value."""
        return (
            NetBoxTokenVersionChoices.V2
            if getattr(token, "version", None) == 2
            else NetBoxTokenVersionChoices.V1
        )

    def clean(self):
        """Validate host target and mutually consistent token / key-secret auth."""
        super().clean()
        cleaned_data = self.cleaned_data
        domain = (cleaned_data.get("domain") or "").strip()
        ip_address = cleaned_data.get("ip_address")
        token = cleaned_data.get("token")
        token_version = cleaned_data.get("token_version")
        token_key = (cleaned_data.get("token_key") or "").strip()
        token_secret = (cleaned_data.get("token_secret") or "").strip()

        if not domain and ip_address is None:
            self.add_error("domain", "Provide either a domain or an IP address.")
            self.add_error("ip_address", "Provide either a domain or an IP address.")
            return cleaned_data

        if token:
            selected_token_version = self._token_version_from_token(token)
            if selected_token_version == NetBoxTokenVersionChoices.V2:
                self.add_error(
                    "token",
                    "Selected NetBox v2 token cannot be used here because its secret cannot be retrieved. Use token key and token secret fields instead.",
                )
                return cleaned_data

            token_plaintext = (getattr(token, "plaintext", "") or "").strip()
            if not token_plaintext:
                self.add_error(
                    "token",
                    "Selected NetBox v1 token does not expose a usable plaintext value. Create a new v1 token (or use v2 key/secret fields) and reselect it.",
                )
                return cleaned_data

            cleaned_data["token_version"] = selected_token_version
            cleaned_data["token_key"] = ""
            cleaned_data["token_secret"] = ""
        elif token_version == NetBoxTokenVersionChoices.V2:
            if not token_key:
                self.add_error(
                    "token_key", "Token key is required when using a v2 token."
                )
            if not token_secret:
                self.add_error(
                    "token_secret", "Token secret is required when using a v2 token."
                )
            cleaned_data["token_key"] = token_key
            cleaned_data["token_secret"] = token_secret
        else:
            self.add_error(
                "token", "Select an existing API token to use v1 authentication."
            )
            cleaned_data["token_key"] = ""
            cleaned_data["token_secret"] = ""

        return cleaned_data


class NetBoxEndpointFilterForm(NetBoxModelFilterSetForm):
    """
    Filter form for NetBoxEndpoint model.
    It is used in the NetBoxEndpointListView.
    """

    model = NetBoxEndpoint
    name = forms.CharField(required=False)
    ip_address = forms.ModelMultipleChoiceField(
        queryset=IPAddress.objects.all(), required=False, help_text="Select IP Address"
    )
