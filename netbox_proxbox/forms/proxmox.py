# Django Imports
from django import forms

# NetBox Imports
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from utilities.forms.fields import CommentField, DynamicModelChoiceField
from ipam.models import IPAddress

# Proxbox Imports
from ..models import ProxmoxEndpoint
from ..choices import ProxmoxModeChoices


class ProxmoxEndpointForm(NetBoxModelForm):
    """
    Form for ProxmoxEndpoint model.
    It is used to CREATE and UPDATE ProxmoxEndpoint objects.
    """
    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all()
    )
    
    comments = CommentField()
    
    class Meta:
        model = ProxmoxEndpoint
        fields = (
            'name', 'ip_address', 'port', 'username',
            'password', 'token_name', 'token_value', 'verify_ssl',
            'tags'
        )


class ProxmoxEndpointFilterForm(NetBoxModelFilterSetForm):
    """
    Filter form for ProxmoxEndpoint model.
    It is used in the ProxmoxEndpointListView.
    """
    
    model = ProxmoxEndpoint
    name = forms.CharField(
        required=False
    )
    ip_address = forms.ModelMultipleChoiceField(
        queryset=IPAddress.objects.all(),
        required=False,
        help_text='Select IP Address'
    )
    mode = forms.MultipleChoiceField(
        choices=ProxmoxModeChoices,
        required=False
    )
