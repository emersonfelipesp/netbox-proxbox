from django import forms

from netbox.forms import (
    NetBoxModelForm,
    NetBoxModelFilterSetForm,
)

from ipam.models import IPAddress

from utilities.forms.fields import CommentField, DynamicModelChoiceField

from .models import (
    ProxmoxEndpoint,
)

from . import choices

class ProxmoxEndpointForm(NetBoxModelForm):
    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all()
    )
    
    comments = CommentField()
    
    class Meta:
        model = ProxmoxEndpoint
        fields = ('ip_address', 'port', 'username', 'password', 'token_name', 'token_value', 'verify_ssl', 'tags')


class ProxmoxEndpointFilterForm(NetBoxModelFilterSetForm):
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
        choices=choices.ProxmoxModeChoices,
        required=False
    )
        