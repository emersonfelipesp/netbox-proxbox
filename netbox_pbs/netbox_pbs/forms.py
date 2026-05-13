"""NetBox forms for netbox-pbs.

Only ``PBSEndpoint`` is editable in v1: operators register endpoints
manually so the read-only sync (PR C3) can reach them. The other five
models are reflected from PBS and have no create/edit/import/bulk-edit
forms — they only get filter forms for their list views.
"""

from __future__ import annotations

from django import forms

from netbox.forms import (
    NetBoxModelBulkEditForm,
    NetBoxModelFilterSetForm,
    NetBoxModelForm,
    NetBoxModelImportForm,
)
from utilities.forms.fields import DynamicModelMultipleChoiceField

from netbox_pbs.choices import (
    PBSBackupTypeChoices,
    PBSDatastoreGCStatusChoices,
    PBSJobRunStateChoices,
    PBSJobTypeChoices,
    PBSSnapshotVerifyChoices,
)
from netbox_pbs.models import (
    PBSBackupGroup,
    PBSDatastore,
    PBSEndpoint,
    PBSJobStatus,
    PBSNode,
    PBSSnapshot,
)


# ----- PBSEndpoint: full CRUD ------------------------------------------------


class PBSEndpointForm(NetBoxModelForm):
    """Create or edit a PBS endpoint."""

    class Meta:
        model = PBSEndpoint
        fields = (
            "name",
            "host",
            "port",
            "token_id",
            "token_value",
            "fingerprint",
            "verify_ssl",
            "timeout",
            "tags",
        )
        widgets = {
            "token_value": forms.PasswordInput(render_value=False),
        }


class PBSEndpointFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for the PBS endpoint list view."""

    model = PBSEndpoint
    verify_ssl = forms.NullBooleanField(required=False)


class PBSEndpointBulkEditForm(NetBoxModelBulkEditForm):
    """Bulk edit PBS endpoint rows."""

    model = PBSEndpoint

    port = forms.IntegerField(required=False)
    verify_ssl = forms.NullBooleanField(required=False)
    timeout = forms.IntegerField(required=False)
    fingerprint = forms.CharField(max_length=128, required=False)

    nullable_fields = ("fingerprint",)


class PBSEndpointImportForm(NetBoxModelImportForm):
    """CSV import for PBS endpoint rows."""

    class Meta:
        model = PBSEndpoint
        fields = (
            "name",
            "host",
            "port",
            "token_id",
            "token_value",
            "fingerprint",
            "verify_ssl",
            "timeout",
            "tags",
        )


# ----- Reflected models: filter forms only -----------------------------------


class PBSNodeFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for the PBS node list view."""

    model = PBSNode
    endpoint = DynamicModelMultipleChoiceField(
        queryset=PBSEndpoint.objects.all(),
        required=False,
    )


class PBSDatastoreFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for the PBS datastore list view."""

    model = PBSDatastore
    endpoint = DynamicModelMultipleChoiceField(
        queryset=PBSEndpoint.objects.all(),
        required=False,
    )
    gc_status = forms.MultipleChoiceField(
        choices=PBSDatastoreGCStatusChoices,
        required=False,
    )


class PBSBackupGroupFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for the PBS backup-group list view."""

    model = PBSBackupGroup
    datastore = DynamicModelMultipleChoiceField(
        queryset=PBSDatastore.objects.all(),
        required=False,
    )
    backup_type = forms.MultipleChoiceField(
        choices=PBSBackupTypeChoices,
        required=False,
    )


class PBSSnapshotFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for the PBS snapshot list view."""

    model = PBSSnapshot
    backup_group = DynamicModelMultipleChoiceField(
        queryset=PBSBackupGroup.objects.all(),
        required=False,
    )
    verified = forms.MultipleChoiceField(
        choices=PBSSnapshotVerifyChoices,
        required=False,
    )
    encrypted = forms.NullBooleanField(required=False)
    protected = forms.NullBooleanField(required=False)


class PBSJobStatusFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for the PBS scheduled-job list view."""

    model = PBSJobStatus
    endpoint = DynamicModelMultipleChoiceField(
        queryset=PBSEndpoint.objects.all(),
        required=False,
    )
    datastore = DynamicModelMultipleChoiceField(
        queryset=PBSDatastore.objects.all(),
        required=False,
    )
    job_type = forms.MultipleChoiceField(
        choices=PBSJobTypeChoices,
        required=False,
    )
    last_run_state = forms.MultipleChoiceField(
        choices=PBSJobRunStateChoices,
        required=False,
    )
    enabled = forms.NullBooleanField(required=False)
