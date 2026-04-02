"""Define NetBox forms for backup routine records and backup routine list filtering."""

from django import forms

from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from utilities.forms.fields import CommentField

from netbox_proxbox.models import BackupRoutine, ProxmoxNode, ProxmoxStorage
from netbox_proxbox.choices import BackupRoutineStatusChoices


class BackupRoutineForm(NetBoxModelForm):
    """Form for creating and editing BackupRoutine model."""

    comments = CommentField()

    node = forms.ModelChoiceField(
        queryset=ProxmoxNode.objects.all(),
        required=False,
        help_text="Node to run backup on (leave empty for all nodes).",
        label="Node",
    )
    storage = forms.ModelChoiceField(
        queryset=ProxmoxStorage.objects.all(),
        required=False,
        help_text="Target storage for backup files.",
        label="Storage",
    )
    fleecing_storage = forms.ModelChoiceField(
        queryset=ProxmoxStorage.objects.all(),
        required=False,
        help_text="Storage to use for fleecing operations.",
        label="Fleecing Storage",
    )

    class Meta:
        model = BackupRoutine
        fields = (
            "endpoint",
            "job_id",
            "enabled",
            "schedule",
            "next_run",
            "node",
            "storage",
            "selection",
            "comment",
            "status",
            "keep_last",
            "keep_daily",
            "keep_weekly",
            "keep_monthly",
            "keep_yearly",
            "keep_all",
            "notes_template",
            "bwlimit",
            "zstd",
            "io_workers",
            "fleecing",
            "fleecing_storage",
            "repeat_missed",
            "pbs_change_detection_mode",
            "tags",
            "comments",
        )


class BackupRoutineFilterForm(NetBoxModelFilterSetForm):
    """Filter form for BackupRoutine model list views."""

    model = BackupRoutine

    endpoint = forms.ModelMultipleChoiceField(
        queryset=BackupRoutine.objects.none(),
        required=False,
    )
    node = forms.ModelMultipleChoiceField(
        queryset=ProxmoxNode.objects.all(),
        required=False,
    )
    storage = forms.ModelMultipleChoiceField(
        queryset=ProxmoxStorage.objects.all(),
        required=False,
    )
    status = forms.MultipleChoiceField(
        choices=BackupRoutineStatusChoices,
        required=False,
    )
    enabled = forms.BooleanField(required=False)
    keep_last = forms.IntegerField(required=False)
    keep_daily = forms.IntegerField(required=False)
    keep_weekly = forms.IntegerField(required=False)
    keep_monthly = forms.IntegerField(required=False)
