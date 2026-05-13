"""NetBox filtersets for netbox-pbs list views and (future) API queries.

Pattern mirrors ``netbox_proxbox.filtersets``: one ``NetBoxModelFilterSet``
per persisted model with a ``search`` method that does the same icontains
join the rest of the plugin uses. ``register_filterset`` so the global
NetBox filter registry can find them.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from netbox.filtersets import NetBoxModelFilterSet
from utilities.filtersets import register_filterset

from netbox_pbs.models import (
    PBSBackupGroup,
    PBSDatastore,
    PBSEndpoint,
    PBSJobStatus,
    PBSNode,
    PBSSnapshot,
)


class _PBSModelFilterSet(NetBoxModelFilterSet):
    """Tag-filter OpenAPI hint helper shared by every PBS filterset."""

    _TAG_FILTER_SCHEMA_MAP = {
        "tag": OpenApiTypes.STR,
        "tag__n": OpenApiTypes.STR,
        "tag_id": OpenApiTypes.INT,
        "tag_id__n": OpenApiTypes.INT,
    }

    @classmethod
    def get_filters(cls):
        filters = super().get_filters()
        for name, openapi_type in cls._TAG_FILTER_SCHEMA_MAP.items():
            if name in filters:
                extend_schema_field(openapi_type)(filters[name])
        return filters


@register_filterset
class PBSEndpointFilterSet(_PBSModelFilterSet):
    """Filter PBS endpoints by name, host, or SSL behavior."""

    class Meta:
        model = PBSEndpoint
        fields = ("id", "name", "host", "port", "verify_ssl")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(host__icontains=value)
            | Q(token_id__icontains=value)
        )


@register_filterset
class PBSNodeFilterSet(_PBSModelFilterSet):
    """Filter PBS node mirrors."""

    class Meta:
        model = PBSNode
        fields = ("id", "endpoint", "hostname", "version")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(hostname__icontains=value)
            | Q(version__icontains=value)
            | Q(endpoint__name__icontains=value)
        )


@register_filterset
class PBSDatastoreFilterSet(_PBSModelFilterSet):
    """Filter PBS datastore mirrors."""

    class Meta:
        model = PBSDatastore
        fields = ("id", "endpoint", "name", "gc_status")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(path__icontains=value)
            | Q(endpoint__name__icontains=value)
        )


@register_filterset
class PBSBackupGroupFilterSet(_PBSModelFilterSet):
    """Filter PBS backup-group mirrors."""

    class Meta:
        model = PBSBackupGroup
        fields = ("id", "datastore", "backup_type", "backup_id", "owner")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(backup_id__icontains=value)
            | Q(owner__icontains=value)
            | Q(comment__icontains=value)
            | Q(datastore__name__icontains=value)
        )


@register_filterset
class PBSSnapshotFilterSet(_PBSModelFilterSet):
    """Filter PBS snapshot mirrors."""

    class Meta:
        model = PBSSnapshot
        fields = (
            "id",
            "backup_group",
            "verified",
            "encrypted",
            "protected",
            "backup_time",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(comment__icontains=value)
            | Q(backup_group__backup_id__icontains=value)
            | Q(backup_group__datastore__name__icontains=value)
        )


@register_filterset
class PBSJobStatusFilterSet(_PBSModelFilterSet):
    """Filter PBS scheduled-job mirrors."""

    class Meta:
        model = PBSJobStatus
        fields = (
            "id",
            "endpoint",
            "datastore",
            "job_type",
            "job_id",
            "enabled",
            "last_run_state",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(job_id__icontains=value)
            | Q(endpoint__name__icontains=value)
            | Q(datastore__name__icontains=value)
        )
