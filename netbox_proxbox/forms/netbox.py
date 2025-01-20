# Django Imports
from django import forms

# NetBox Imports
from utilities.forms.fields import DynamicModelChoiceField, CommentField
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from ipam.models import IPAddress

# Proxbox Imports
from ..models import NetBoxEndpoint


class NetBoxEndpointForm(NetBoxModelForm):
    """
    Form for NetBoxEndpoint model.
    It is used to CREATE and UPDATE NetBoxEndpoint objects.
    """
    
    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all()
    )
    
    comments = CommentField()
    
    class Meta:
        model = NetBoxEndpoint
        fields = (
            'name', 'ip_address', 'port',
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