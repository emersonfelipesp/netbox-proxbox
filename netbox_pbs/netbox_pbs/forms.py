"""NetBox forms for the netbox-pbs plugin."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField

from netbox_pbs.choices import (
    PBSBackupTypeChoices,
    PBSGCStatusChoices,
    PBSJobRunStateChoices,
    PBSJobTypeChoices,
    PBSServerStatusChoices,
)
from netbox_pbs.models import (
    PBSDatastore,
    PBSJob,
    PBSPluginSettings,
    PBSServer,
    PBSSnapshot,
)


class PBSPluginSettingsForm(NetBoxModelForm):
    class Meta:
        model = PBSPluginSettings
        fields = (
            "proxbox_api_url",
            "proxbox_api_key",
            "branching_enabled",
            "branch_name_prefix",
            "branch_on_conflict",
            "tags",
        )


class PBSServerForm(NetBoxModelForm):
    class Meta:
        model = PBSServer
        fields = (
            "name",
            "host",
            "port",
            "token_id",
            "fingerprint",
            "verify_ssl",
            "tags",
        )


class PBSServerFilterForm(NetBoxModelFilterSetForm):
    model = PBSServer

    name = forms.CharField(required=False)
    host = forms.CharField(required=False)
    port = forms.IntegerField(required=False)
    status = forms.ChoiceField(choices=PBSServerStatusChoices, required=False)
    verify_ssl = forms.NullBooleanField(required=False)
    version = forms.CharField(required=False)


class _ServerFilterMixin:
    server = DynamicModelChoiceField(
        queryset=PBSServer.objects.all(),
        required=False,
        label=_("PBS server"),
    )


class PBSDatastoreFilterForm(_ServerFilterMixin, NetBoxModelFilterSetForm):
    model = PBSDatastore

    name = forms.CharField(required=False)
    path = forms.CharField(required=False)
    gc_status = forms.ChoiceField(choices=PBSGCStatusChoices, required=False)


class PBSSnapshotFilterForm(_ServerFilterMixin, NetBoxModelFilterSetForm):
    model = PBSSnapshot

    datastore_name = forms.CharField(required=False)
    backup_type = forms.ChoiceField(choices=PBSBackupTypeChoices, required=False)
    backup_id = forms.CharField(required=False)
    owner = forms.CharField(required=False)
    protected = forms.NullBooleanField(required=False)
    verification_state = forms.CharField(required=False)


class PBSJobFilterForm(_ServerFilterMixin, NetBoxModelFilterSetForm):
    model = PBSJob

    job_type = forms.ChoiceField(choices=PBSJobTypeChoices, required=False)
    job_id = forms.CharField(required=False)
    store = forms.CharField(required=False)
    disable = forms.NullBooleanField(required=False)
    last_run_state = forms.ChoiceField(choices=PBSJobRunStateChoices, required=False)
