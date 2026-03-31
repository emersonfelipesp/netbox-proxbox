"""Define NetBox forms for VM task history records and tab filtering."""

from django import forms

from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import CommentField, DynamicModelChoiceField
from virtualization.models import VirtualMachine

from netbox_proxbox.models import VMTaskHistory


class VMTaskHistoryForm(NetBoxModelForm):
    """Create or edit a VM task history record."""

    comments = CommentField()
    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=True,
        label="Virtual Machine",
    )

    class Meta:
        model = VMTaskHistory
        fields = (
            "virtual_machine",
            "vm_type",
            "upid",
            "node",
            "pid",
            "pstart",
            "task_id",
            "task_type",
            "username",
            "start_time",
            "end_time",
            "description",
            "status",
            "task_state",
            "exitstatus",
            "tags",
            "comments",
        )


class VMTaskHistoryFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for the VM task history tab view."""

    model = VMTaskHistory

    virtual_machine = forms.ModelMultipleChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
    )
    vm_type = forms.CharField(required=False)
    upid = forms.CharField(required=False)
    node = forms.CharField(required=False)
    task_id = forms.CharField(required=False)
    task_type = forms.CharField(required=False)
    username = forms.CharField(required=False)
    description = forms.CharField(required=False)
    status = forms.CharField(required=False)
    task_state = forms.CharField(required=False)
    exitstatus = forms.CharField(required=False)
