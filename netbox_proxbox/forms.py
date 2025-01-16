from django import forms

from netbox.forms import (
    NetBoxModelForm,
    NetBoxModelFilterSetForm,
)

from .models import (
    ProxmoxEndpoint,
)

class ProxmoxEndpointForm(NetBoxModelForm):
    class Meta:
        model = ProxmoxEndpoint
        fields = ('ip_address', 'port', 'username', 'password', 'token_name', 'token_value', 'verify_ssl')


class ProxmoxEndpointFilterForm(NetBoxModelFilterSetForm):
    q = forms.CharField(
        required=False, label="Search"
    )
    model = ProxmoxEndpoint
        