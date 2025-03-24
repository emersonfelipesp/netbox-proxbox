# Django Imports
from django import forms

# NetBox Imports
from utilities.forms.fields import DynamicModelChoiceField, CommentField
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm

# Proxbox Imports
from ..models import SyncProcess
from ..choices import SyncType, SyncStatus

class SyncProcessForm(NetBoxModelForm):
    """
    Form for SyncProcess model.
    It is used to CREATE and UPDATE SyncProcess objects.
    """
    
    comments = CommentField()
    
    sync_type = forms.ChoiceField(
        choices=SyncType.choices,
        required=False
    )
    status = forms.ChoiceField(
        choices=SyncStatus.choices,
        required=False
    )
    
    class Meta:
        model = SyncProcess
        fields = ('name', 'sync_type', 'status', 'started_at', 'completed_at')


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
        choices=SyncType.choices,
        required=False
    )
    status = forms.ChoiceField(
        choices=SyncStatus.choices,
        required=False
    )
    
