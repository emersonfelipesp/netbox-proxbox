"""DRF viewsets for the netbox-pbs plugin API.

Read-only enforcement lives at the viewset layer: the five reflected models
restrict ``http_method_names`` to GET/HEAD/OPTIONS so POST/PUT/PATCH/DELETE
return 405. ``PBSEndpoint`` is the only writable surface.
"""

from __future__ import annotations

from netbox.api.viewsets import NetBoxModelViewSet

from netbox_pbs import filtersets, models
from netbox_pbs.api.serializers import (
    PBSBackupGroupSerializer,
    PBSDatastoreSerializer,
    PBSEndpointSerializer,
    PBSJobStatusSerializer,
    PBSNodeSerializer,
    PBSSnapshotSerializer,
)


_READ_ONLY_HTTP_METHODS = ("get", "head", "options")


class PBSEndpointViewSet(NetBoxModelViewSet):
    """REST API for PBS endpoint credentials. Full CRUD."""

    queryset = models.PBSEndpoint.objects.all()
    serializer_class = PBSEndpointSerializer
    filterset_class = filtersets.PBSEndpointFilterSet


class PBSNodeViewSet(NetBoxModelViewSet):
    """REST API for reflected PBS nodes. Read-only (GET/HEAD/OPTIONS)."""

    queryset = models.PBSNode.objects.select_related("endpoint")
    serializer_class = PBSNodeSerializer
    filterset_class = filtersets.PBSNodeFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class PBSDatastoreViewSet(NetBoxModelViewSet):
    """REST API for reflected PBS datastores. Read-only (GET/HEAD/OPTIONS)."""

    queryset = models.PBSDatastore.objects.select_related("endpoint")
    serializer_class = PBSDatastoreSerializer
    filterset_class = filtersets.PBSDatastoreFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class PBSBackupGroupViewSet(NetBoxModelViewSet):
    """REST API for reflected PBS backup groups. Read-only (GET/HEAD/OPTIONS)."""

    queryset = models.PBSBackupGroup.objects.select_related(
        "datastore", "datastore__endpoint"
    )
    serializer_class = PBSBackupGroupSerializer
    filterset_class = filtersets.PBSBackupGroupFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class PBSSnapshotViewSet(NetBoxModelViewSet):
    """REST API for reflected PBS snapshots. Read-only (GET/HEAD/OPTIONS)."""

    queryset = models.PBSSnapshot.objects.select_related(
        "backup_group", "backup_group__datastore", "backup_group__datastore__endpoint"
    )
    serializer_class = PBSSnapshotSerializer
    filterset_class = filtersets.PBSSnapshotFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class PBSJobStatusViewSet(NetBoxModelViewSet):
    """REST API for reflected PBS job status. Read-only (GET/HEAD/OPTIONS)."""

    queryset = models.PBSJobStatus.objects.select_related("endpoint", "datastore")
    serializer_class = PBSJobStatusSerializer
    filterset_class = filtersets.PBSJobStatusFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS
