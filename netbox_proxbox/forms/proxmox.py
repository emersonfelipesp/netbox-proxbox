# Django Imports
from django import forms

# NetBox Imports
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from utilities.forms.fields import CommentField, DynamicModelChoiceField
from ipam.models import IPAddress
from django.utils.translation import gettext as _

# Proxbox Imports
from ..models import ProxmoxEndpoint
from ..choices import ProxmoxModeChoices


class ProxmoxEndpointForm(NetBoxModelForm):
    """
    Form for ProxmoxEndpoint model.
    It is used to CREATE and UPDATE ProxmoxEndpoint objects.
    """
    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all(),
        help_text=_('Select a NetBox IP Address'),
        label=_('IP Address'),
        required=False
    )
    domain = forms.CharField(
        required=False,
        help_text=_('Domain name of the Proxmox Endpoint (Cluster). It will try using the DNS name provided in IP Address if it is not empty.'),
        label=_('Domain')
    )
    verify_ssl = forms.BooleanField(
        required=False,
        help_text=_('Choose or not to verify SSL certificate of the Proxmox Endpoint. Only use this if you are sure about the SSL certificate of the Proxmox Endpoint.'),
        label=_('Verify SSL')
    )
    comments = CommentField()
    
    class Meta:
        model = ProxmoxEndpoint
        fields = (
            'name', 'ip_address', 'domain', 'port', 'username',
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
