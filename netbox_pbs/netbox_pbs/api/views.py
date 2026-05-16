"""DRF viewsets for the netbox-pbs plugin API."""

from __future__ import annotations

from netbox.api.viewsets import NetBoxModelViewSet

from netbox_pbs import filtersets
from netbox_pbs.api import serializers
from netbox_pbs.models import (
    PBSDatastore,
    PBSJob,
    PBSPluginSettings,
    PBSServer,
    PBSSnapshot,
)

_READ_ONLY_HTTP_METHODS = ("get", "head", "options")


class PBSPluginSettingsViewSet(NetBoxModelViewSet):
    queryset = PBSPluginSettings.objects.all()
    serializer_class = serializers.PBSPluginSettingsSerializer


class PBSServerViewSet(NetBoxModelViewSet):
    queryset = PBSServer.objects.all()
    serializer_class = serializers.PBSServerSerializer
    filterset_class = filtersets.PBSServerFilterSet


class PBSDatastoreViewSet(NetBoxModelViewSet):
    queryset = PBSDatastore.objects.select_related("server").all()
    serializer_class = serializers.PBSDatastoreSerializer
    filterset_class = filtersets.PBSDatastoreFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class PBSSnapshotViewSet(NetBoxModelViewSet):
    queryset = PBSSnapshot.objects.select_related("server").all()
    serializer_class = serializers.PBSSnapshotSerializer
    filterset_class = filtersets.PBSSnapshotFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class PBSJobViewSet(NetBoxModelViewSet):
    queryset = PBSJob.objects.select_related("server").all()
    serializer_class = serializers.PBSJobSerializer
    filterset_class = filtersets.PBSJobFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS
