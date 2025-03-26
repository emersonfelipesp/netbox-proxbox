# Django Imports
from django import forms
from django.utils.translation import gettext as _
# NetBox Imports
from utilities.forms.fields import DynamicModelChoiceField, CommentField
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm

# Proxbox Imports
from ..models import SyncProcess
from ..choices import SyncTypeChoices, SyncStatusChoices

class SyncProcessForm(NetBoxModelForm):
    """
    Form for SyncProcess model.
    It is used to CREATE and UPDATE SyncProcess objects.
    """
    
    comments = CommentField()
    
    sync_type = forms.ChoiceField(
        choices=SyncTypeChoices,
        required=False
    )
    status = forms.ChoiceField(
        choices=SyncStatusChoices,
        required=False
    )
    runtime = forms.FloatField(
        required=False,
        help_text=_('Time elapsed for the sync process. Format: seconds')
    )
    
    class Meta:
        model = SyncProcess
        fields = ('name', 'sync_type', 'status', 'started_at', 'completed_at', 'runtime')


class SyncProcessFilterForm(NetBoxModelFilterSetForm):
    """
    Filter form for SyncProcess model.
    It is used in the SyncProcessListView.
    """
    
    model = SyncProcess
    name = forms.CharField(
        required=False
    )
    sync_type = forms.ChoiceField(
        choices=SyncTypeChoices,
        required=False,
    )
    status = forms.ChoiceField(
        choices=SyncStatusChoices,
        required=False,
    )
    runtime = forms.FloatField(
        required=False,
        help_text=_('Time elapsed for the sync process. Format: seconds')
    )
