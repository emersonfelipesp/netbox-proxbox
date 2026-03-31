"""Define NetBox forms for VM backup records and backup list filtering."""

# Django Imports
from django import forms

# NetBox Imports
from utilities.forms.fields import DynamicModelChoiceField, CommentField
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from virtualization.models import VirtualMachine

# Proxbox Imports
from netbox_proxbox.models import ProxmoxStorage, VMBackup
from netbox_proxbox.choices import (
    ProxmoxBackupSubtypeChoices,
    ProxmoxBackupFormatChoices,
)


class VMBackupForm(NetBoxModelForm):
    """
    Form for VMBackup model.
    """

    class Meta:
        model = VMBackup
        fields = (
            "proxmox_storage",
            "storage",
            "virtual_machine",
            "subtype",
            "format",
            "creation_time",
            "size",
            "notes",
            "volume_id",
            "vmid",
            "used",
            "encrypted",
            "verification_state",
            "verification_upid",
            "tags",
            "comments",
        )

    comments = CommentField()

    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=True,
        help_text="Select a Virtual Machine",
        label="Virtual Machine",
    )
    proxmox_storage = DynamicModelChoiceField(
        queryset=ProxmoxStorage.objects.all(),
        required=False,
        help_text="Select related Proxmox storage object.",
        label="Proxmox Storage",
    )

    subtype = forms.ChoiceField(
        choices=ProxmoxBackupSubtypeChoices,
        required=False,
        help_text="Select a Backup Subtype",
        label="Backup Subtype",
    )

    format = forms.ChoiceField(
        choices=ProxmoxBackupFormatChoices,
        required=False,
        help_text="Select a Backup Format",
        label="Backup Format",
    )


class VMBackupFilterForm(NetBoxModelFilterSetForm):
    """
    Filter form for VMBackup model.
    """

    model = VMBackup

    proxmox_storage = forms.ModelMultipleChoiceField(
        queryset=ProxmoxStorage.objects.all(),
        required=False,
    )

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
