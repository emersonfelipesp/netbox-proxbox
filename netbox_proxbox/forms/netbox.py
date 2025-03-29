# Django Imports
from django import forms

# NetBox Imports
from utilities.forms.fields import DynamicModelChoiceField, CommentField
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from ipam.models import IPAddress
from users.models import Token

# Proxbox Imports
from ..models import NetBoxEndpoint


class NetBoxEndpointForm(NetBoxModelForm):
    """
    Form for NetBoxEndpoint model.
    It is used to CREATE and UPDATE NetBoxEndpoint objects.
    """
    
    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all(),
        required=False,
        help_text='Select IP Address',
        label='IP Address'
    )
    
    token = forms.ModelChoiceField(
        queryset=Token.objects.all(),
        required=False,
        help_text='Choose an existing NetBox API Token',
        label='API Token',
        to_field_name='key'  # This will return the full token from the database
    )
    
    comments = CommentField()
    
    class Meta:
        model = NetBoxEndpoint
        fields = (
            'name', 'domain', 'ip_address', 'port',
            'token', 'verify_ssl', 'tags'
        )


class NetBoxEndpointFilterForm(NetBoxModelFilterSetForm):
    """
    Filter form for NetBoxEndpoint model.
    It is used in the NetBoxEndpointListView.
    """
    
    model = NetBoxEndpoint
    name = forms.CharField(
        required=False
    )
    ip_address = forms.ModelMultipleChoiceField(
        queryset=IPAddress.objects.all(),
        required=False,
        help_text='Select IP Address'
    )