"""Define NetBox forms for VM snapshot records and snapshot list filtering."""

from django import forms

from netbox.forms import (
    NetBoxModelBulkEditForm,
    NetBoxModelForm,
    NetBoxModelFilterSetForm,
    NetBoxModelImportForm,
)
from utilities.forms.fields import (
    CommentField,
    CSVChoiceField,
    CSVModelChoiceField,
    DynamicModelChoiceField,
)
from utilities.forms.rendering import FieldSet
from virtualization.models import VirtualMachine

from netbox_proxbox.choices import (
    ProxmoxSnapshotSubtypeChoices,
    ProxmoxSnapshotStatusChoices,
)
from netbox_proxbox.models import ProxmoxStorage, VMSnapshot


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


class VMSnapshotBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for simultaneously updating multiple VM snapshot records."""

    model = VMSnapshot

    proxmox_storage = DynamicModelChoiceField(
        queryset=ProxmoxStorage.objects.all(),
        required=False,
        label="Proxmox Storage",
    )
    description = forms.CharField(
        max_length=200,
        required=False,
        label="Description",
    )
    subtype = forms.ChoiceField(
        choices=[("", "---------")] + list(ProxmoxSnapshotSubtypeChoices),
        required=False,
        label="Subtype",
    )
    status = forms.ChoiceField(
        choices=[("", "---------")] + list(ProxmoxSnapshotStatusChoices),
        required=False,
        label="Status",
    )
    comments = CommentField()

    fieldsets = (
        FieldSet(
            "proxmox_storage", "subtype", "status", "description", name="Snapshot"
        ),
    )
    nullable_fields = ("proxmox_storage", "description", "comments")


class VMSnapshotImportForm(NetBoxModelImportForm):
    """CSV import form for bulk creation of VM snapshot records."""

    virtual_machine = CSVModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        to_field_name="name",
        help_text="Name of the associated virtual machine.",
    )
    proxmox_storage = CSVModelChoiceField(
        queryset=ProxmoxStorage.objects.all(),
        to_field_name="name",
        required=False,
        help_text="Name of the associated Proxmox storage (optional).",
    )
    subtype = CSVChoiceField(
        choices=ProxmoxSnapshotSubtypeChoices,
        required=False,
        help_text="Snapshot subtype: qemu or lxc.",
    )
    status = CSVChoiceField(
        choices=ProxmoxSnapshotStatusChoices,
        required=False,
        help_text="Snapshot status: active or stale.",
    )

    class Meta:
        model = VMSnapshot
        fields = (
            "virtual_machine",
            "proxmox_storage",
            "name",
            "description",
            "vmid",
            "node",
            "snaptime",
            "parent",
            "subtype",
            "status",
            "tags",
        )
