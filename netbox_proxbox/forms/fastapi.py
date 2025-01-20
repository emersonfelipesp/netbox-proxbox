# Django Imports
from django import forms

# NetBox Imports
from utilities.forms.fields import DynamicModelChoiceField, CommentField
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from ipam.models import IPAddress

# Proxbox Imports
from ..models import FastAPIEndpoint


class FastAPIEndpointForm(NetBoxModelForm):
    """
    Form for FastAPIEndpoint model.
    It is used to CREATE and UPDATE FastAPIEndpoint objects.
    """

    ip_address = DynamicModelChoiceField(
        queryset=IPAddress.objects.all()
    )

    comments = CommentField()

    class Meta:
        model = FastAPIEndpoint
        fields = (
            'name', 'ip_address', 'port',
            'verify_ssl', 'tags'
        )


class FastAPIEndpointFilterForm(NetBoxModelFilterSetForm):
    """
    Filter form for FastAPIEndpoint model.
    It is used in the FastAPIEndpointListView.
    """

    model = FastAPIEndpoint
    name = forms.CharField(
        required=False
    )
    ip_address = forms.ModelMultipleChoiceField(
        queryset=IPAddress.objects.all(),
        required=False,
        help_text='Select IP Address'
    )