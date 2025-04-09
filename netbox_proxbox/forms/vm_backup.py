# Django Imports
from django import forms
from django.utils.translation import gettext as _

# NetBox Imports
from utilities.forms.fields import DynamicModelChoiceField, CommentField
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from virtualization.models import VirtualMachine
# Proxbox Imports
from netbox_proxbox.models import VMBackup
from netbox_proxbox.choices import ProxmoxBackupSubtypeChoices, ProxmoxBackupFormatChoices


class VMBackupForm(NetBoxModelForm):
    """
    Form for VMBackup model.
    """

    comments = CommentField()

    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=True,
        help_text='Select a Virtual Machine',
        label='Virtual Machine',
    )
    
    subtype = forms.ChoiceField(
        choices=ProxmoxBackupSubtypeChoices,
        required=False,
        help_text='Select a Backup Subtype',
        label='Backup Subtype',
    )
    
    format = forms.ChoiceField(
        choices=ProxmoxBackupFormatChoices,
        required=False,
        help_text='Select a Backup Format',
        label='Backup Format',
    )


class VMBackupFilterForm(NetBoxModelFilterSetForm):
    """
    Filter form for VMBackup model.
    """

    model = VMBackup

    virtual_machine = forms.ModelMultipleChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
    )

    subtype = forms.MultipleChoiceField(
        choices=ProxmoxBackupSubtypeChoices,
        required=False,
    )

    format = forms.MultipleChoiceField(
        choices=ProxmoxBackupFormatChoices,
        required=False,
    )
