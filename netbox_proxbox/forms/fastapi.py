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
        queryset=IPAddress.objects.all(),
        required=False,
        help_text='Select NetBox IP Address. Fallback if domain name is not provided.',
        label='IP Address'
    )
    token = forms.CharField(
        required=False,
        help_text='This will only be working from v0.0.7 and above. Token for the Proxbox Endpoint. If not provided, the Proxbox Endpoint will not be able to send messages to the client (user) browser.',
        label='[BETA] Proxbox Backend Token'
    )
    use_websocket = forms.BooleanField(
        required=False,
        help_text='Choose or not to use WebSocket for the Proxbox Endpoint. If enabled, the Proxbox Endpoint will use WebSocket connection to send messages to the client (user) browser.',
        label='Use WebSocket'
    )
    websocket_domain = forms.CharField(
        required=False,
        help_text='Domain name of the WebSocket for the Proxbox Endpoint. The client (user) browser will connect to this domain to receive messages from the Proxbox Endpoint.',
        label='WebSocket Domain'
    )
    websocket_port = forms.IntegerField(
        required=False,
        help_text='Port of the WebSocket for the Proxbox Endpoint (the same as HTTP port)',
        label='WebSocket Port'
    )
    server_side_websocket = forms.BooleanField(
        required=False,
        help_text='Choose or not to use server side WebSocket connection for the Proxbox Endpoint. This is experimental feature and may not work as expected. This way, client will not need to connect to the Proxbox Endpoint. Avoiding firewall rules to protect the Proxbox Endpoint.',
        label='[BETA] Server Side WebSocket'
    )
    
    comments = CommentField()

    class Meta:
        model = FastAPIEndpoint
        fields = (
            'name', 'domain', 'ip_address', 'port',
            'verify_ssl', 'use_websocket', 'websocket_domain', 'websocket_port',
            'server_side_websocket', 'token', 'tags'
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