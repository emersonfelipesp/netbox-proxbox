"""NetBox filtersets for PBS inventory models."""

from __future__ import annotations

from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet

from netbox_pbs.models import PBSDatastore, PBSJob, PBSPluginSettings, PBSServer, PBSSnapshot


class PBSServerFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = PBSServer
        fields = ("id", "name", "host", "port", "status", "verify_ssl", "version")

    def search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(host__icontains=value)
            | Q(version__icontains=value)
            | Q(status__icontains=value)
        )


class PBSDatastoreFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = PBSDatastore
        fields = ("id", "server", "name", "path", "gc_status")

    def search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(path__icontains=value)
            | Q(comment__icontains=value)
            | Q(server__name__icontains=value)
        )


class PBSSnapshotFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = PBSSnapshot
        fields = (
            "id",
            "server",
            "datastore_name",
            "backup_type",
            "backup_id",
            "owner",
            "protected",
            "verification_state",
        )

    def search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(datastore_name__icontains=value)
            | Q(backup_id__icontains=value)
            | Q(owner__icontains=value)
            | Q(comment__icontains=value)
            | Q(server__name__icontains=value)
        )


class PBSJobFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = PBSJob
        fields = (
            "id",
            "server",
            "job_type",
            "job_id",
            "store",
            "disable",
            "last_run_state",
        )

    def search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(job_id__icontains=value)
            | Q(store__icontains=value)
            | Q(schedule__icontains=value)
            | Q(comment__icontains=value)
            | Q(server__name__icontains=value)
        )


class PBSPluginSettingsFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = PBSPluginSettings
        fields = ("id", "branching_enabled", "branch_on_conflict")
