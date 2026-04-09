"""Define NetBox forms for Replication records and replication list filtering."""

from django import forms
from netbox.forms import (
    NetBoxModelBulkEditForm,
    NetBoxModelFilterSetForm,
    NetBoxModelForm,
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
    ReplicationJobTypeChoices,
    ReplicationRemoveJobChoices,
    ReplicationStatusChoices,
)
from netbox_proxbox.models import ProxmoxEndpoint, ProxmoxNode, Replication


class ReplicationForm(NetBoxModelForm):
    """Form for Replication model."""

    comments = CommentField()

    endpoint = DynamicModelChoiceField(
        queryset=ProxmoxEndpoint.objects.all(),
        required=False,
        help_text="Select the source Proxmox endpoint.",
        label="Proxmox Endpoint",
    )
    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=True,
        help_text="Select a Virtual Machine",
        label="Virtual Machine",
    )
    proxmox_node = DynamicModelChoiceField(
        queryset=ProxmoxNode.objects.all(),
        required=False,
        help_text="Select related Proxmox node.",
        label="Proxmox Node",
    )
    job_type = forms.ChoiceField(
        choices=ReplicationJobTypeChoices,
        required=False,
        help_text="Select a Job Type",
        label="Job Type",
    )
    disable = forms.BooleanField(
        required=False,
        help_text="Check to disable/deactivate the entry",
        label="Disabled",
    )
    remove_job = forms.ChoiceField(
        choices=[("", "---------")] + list(ReplicationRemoveJobChoices),
        required=False,
        help_text="Mark the replication job for removal",
        label="Remove Job",
    )
    status = forms.ChoiceField(
        choices=ReplicationStatusChoices,
        required=False,
        help_text="Select a status",
        label="Status",
    )

    class Meta:
        model = Replication
        fields = (
            "endpoint",
            "replication_id",
            "virtual_machine",
            "proxmox_node",
            "guest",
            "target",
            "job_type",
            "schedule",
            "rate",
            "comment",
            "disable",
            "source",
            "jobnum",
            "remove_job",
            "status",
            "tags",
            "comments",
        )


class ReplicationFilterForm(NetBoxModelFilterSetForm):
    """Filter form for Replication model."""

    model = Replication

    endpoint = forms.ModelMultipleChoiceField(
        queryset=ProxmoxEndpoint.objects.all(),
        required=False,
    )
    virtual_machine = forms.ModelMultipleChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
    )
    proxmox_node = forms.ModelMultipleChoiceField(
        queryset=ProxmoxNode.objects.all(),
        required=False,
    )
    job_type = forms.MultipleChoiceField(
        choices=ReplicationJobTypeChoices,
        required=False,
    )
    disable = forms.MultipleChoiceField(
        choices=[
            (True, "Yes"),
            (False, "No"),
        ],
        required=False,
    )
    remove_job = forms.MultipleChoiceField(
        choices=ReplicationRemoveJobChoices,
        required=False,
    )
    status = forms.MultipleChoiceField(
        choices=ReplicationStatusChoices,
        required=False,
    )


class ReplicationBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit form for simultaneously updating multiple Replication records."""

    model = Replication

    proxmox_node = DynamicModelChoiceField(
        queryset=ProxmoxNode.objects.all(),
        required=False,
        label="Proxmox Node",
    )
    job_type = forms.ChoiceField(
        choices=[("", "---------")] + list(ReplicationJobTypeChoices),
        required=False,
        label="Job Type",
    )
    status = forms.ChoiceField(
        choices=[("", "---------")] + list(ReplicationStatusChoices),
        required=False,
        label="Status",
    )
    disable = forms.NullBooleanField(
        required=False,
        widget=forms.Select(
            choices=[("", "---------"), ("True", "Yes"), ("False", "No")]
        ),
        label="Disabled",
    )
    schedule = forms.CharField(
        max_length=128,
        required=False,
        label="Schedule",
    )
    rate = forms.FloatField(
        required=False,
        label="Rate (MB/s)",
    )
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label="Comment",
    )
    comments = CommentField()

    fieldsets = (
        FieldSet("proxmox_node", "job_type", "status", "disable", name="Replication"),
        FieldSet("schedule", "rate", "comment", name="Details"),
    )
    nullable_fields = ("proxmox_node", "comment", "comments", "rate")


class ReplicationImportForm(NetBoxModelImportForm):
    """CSV import form for bulk creation of Replication records."""

    virtual_machine = CSVModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        to_field_name="name",
        help_text="Name of the associated virtual machine.",
    )
    job_type = CSVChoiceField(
        choices=ReplicationJobTypeChoices,
        required=False,
        help_text="Replication type (e.g. local).",
    )
    remove_job = CSVChoiceField(
        choices=ReplicationRemoveJobChoices,
        required=False,
        help_text="Removal marker: local or full.",
    )
    status = CSVChoiceField(
        choices=ReplicationStatusChoices,
        required=False,
        help_text="Status: active or stale.",
    )

    class Meta:
        model = Replication
        fields = (
            "endpoint",
            "replication_id",
            "virtual_machine",
            "guest",
            "target",
            "job_type",
            "schedule",
            "rate",
            "comment",
            "disable",
            "source",
            "jobnum",
            "remove_job",
            "status",
            "tags",
        )
