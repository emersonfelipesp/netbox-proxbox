"""Define NetBox forms for VM snapshot records and snapshot list filtering."""

from django import forms

from utilities.forms.fields import DynamicModelChoiceField, CommentField
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from virtualization.models import VirtualMachine
from netbox_proxbox.models import ProxmoxStorage, VMSnapshot
from netbox_proxbox.choices import (
    ProxmoxSnapshotSubtypeChoices,
    ProxmoxSnapshotStatusChoices,
)


class VMSnapshotForm(NetBoxModelForm):
    """Edit a Proxmox-backed snapshot row attached to a NetBox VM."""

    class Meta:
        model = VMSnapshot
        fields = (
            "proxmox_storage",
            "virtual_machine",
            "name",
            "description",
            "vmid",
            "node",
            "snaptime",
            "parent",
            "subtype",
            "status",
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
        choices=ProxmoxSnapshotSubtypeChoices,
        required=False,
        help_text="Select a Snapshot Subtype",
        label="Subtype",
    )

    status = forms.ChoiceField(
        choices=ProxmoxSnapshotStatusChoices,
        required=False,
        help_text="Select a Snapshot Status",
        label="Status",
    )


class VMSnapshotFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for the VM snapshot list view."""

    model = VMSnapshot
    proxmox_storage = forms.ModelMultipleChoiceField(
        queryset=ProxmoxStorage.objects.all(),
        required=False,
    )

    virtual_machine = forms.ModelMultipleChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
    )

    subtype = forms.MultipleChoiceField(
        choices=ProxmoxSnapshotSubtypeChoices,
        required=False,
    )

    status = forms.MultipleChoiceField(
        choices=ProxmoxSnapshotStatusChoices,
        required=False,
    )
