"""Define NetBox forms for Replication records and replication list filtering."""

from django import forms
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import CommentField, DynamicModelChoiceField
from virtualization.models import VirtualMachine

from netbox_proxbox.models import ProxmoxNode, Replication


class ReplicationForm(NetBoxModelForm):
    """Form for Replication model."""

    comments = CommentField()

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
        choices=[("local", "Local")],
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
        choices=[
            ("", "---------"),
            ("local", "Local"),
            ("full", "Full"),
        ],
        required=False,
        help_text="Mark the replication job for removal",
        label="Remove Job",
    )

    class Meta:
        model = Replication
        fields = (
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
            "tags",
            "comments",
        )


class ReplicationFilterForm(NetBoxModelFilterSetForm):
    """Filter form for Replication model."""

    model = Replication

    virtual_machine = forms.ModelMultipleChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
    )
    proxmox_node = forms.ModelMultipleChoiceField(
        queryset=ProxmoxNode.objects.all(),
        required=False,
    )
    job_type = forms.MultipleChoiceField(
        choices=[("local", "Local")],
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
        choices=[
            ("local", "Local"),
            ("full", "Full"),
        ],
        required=False,
    )
