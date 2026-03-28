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
        help_text='Choose an existing NetBox v1 or v2 API token. If selected, manual token fields are not required.',
        label='API Token',
    )

    token_version = forms.ChoiceField(
        choices=NetBoxTokenVersionChoices,
        initial=NetBoxTokenVersionChoices.V1,
        required=True,
        help_text='Select whether this endpoint uses a NetBox v1 token or v2 token credentials.',
        label='Token Version',
    )

    token_key = forms.CharField(
        required=False,
        help_text='Enter the NetBox v2 token key when not selecting an existing API token.',
        label='Token Key',
        widget=forms.TextInput(attrs={'autocomplete': 'off'}),
    )

    token_secret = forms.CharField(
        required=False,
        help_text='Enter the NetBox v2 token secret when not selecting an existing API token.',
        label='Token Secret',
        widget=forms.PasswordInput(render_value=True, attrs={'autocomplete': 'new-password'}),
    )
    
    comments = CommentField()
    
    class Meta:
        model = NetBoxEndpoint
        fields = (
            'name', 'domain', 'ip_address', 'port',
            'token_version', 'token', 'token_key', 'token_secret', 'verify_ssl', 'tags'
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        token = getattr(self.instance, 'token', None)
        if token is not None:
            self.initial['token_version'] = self._token_version_from_token(token)

    @staticmethod
    def _token_version_from_token(token: Token) -> str:
        return NetBoxTokenVersionChoices.V2 if getattr(token, 'version', None) == 2 else NetBoxTokenVersionChoices.V1

    def clean(self):
        cleaned_data = super().clean()
        token = cleaned_data.get('token')
        token_version = cleaned_data.get('token_version')
        token_key = (cleaned_data.get('token_key') or '').strip()
        token_secret = (cleaned_data.get('token_secret') or '').strip()

        if token:
            cleaned_data['token_version'] = self._token_version_from_token(token)
            cleaned_data['token_key'] = ''
            cleaned_data['token_secret'] = ''
        elif token_version == NetBoxTokenVersionChoices.V2:
            if not token_key:
                self.add_error('token_key', 'Token key is required when using a v2 token.')
            if not token_secret:
                self.add_error('token_secret', 'Token secret is required when using a v2 token.')
            cleaned_data['token_key'] = token_key
            cleaned_data['token_secret'] = token_secret
        else:
            self.add_error('token', 'Select an existing API token to use v1 authentication.')
            cleaned_data['token_key'] = ''
            cleaned_data['token_secret'] = ''

        return cleaned_data


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
