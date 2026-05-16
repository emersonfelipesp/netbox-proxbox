"""DRF viewsets for the netbox-ceph plugin API.

All resources are read-only in v1: HTTP methods are restricted to GET/HEAD/OPTIONS.
"""

from __future__ import annotations

from netbox.api.viewsets import NetBoxModelViewSet

from netbox_ceph import filtersets
from netbox_ceph.api import serializers
from netbox_ceph.models import (
    CephCluster,
    CephCrushRule,
    CephDaemon,
    CephFilesystem,
    CephFlag,
    CephHealthCheck,
    CephOSD,
    CephPluginSettings,
    CephPool,
)

_READ_ONLY_HTTP_METHODS = ("get", "head", "options")


class CephPluginSettingsViewSet(NetBoxModelViewSet):
    queryset = CephPluginSettings.objects.all()
    serializer_class = serializers.CephPluginSettingsSerializer


class CephClusterViewSet(NetBoxModelViewSet):
    queryset = CephCluster.objects.select_related("endpoint", "proxmox_cluster").all()
    serializer_class = serializers.CephClusterSerializer
    filterset_class = filtersets.CephClusterFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class CephDaemonViewSet(NetBoxModelViewSet):
    queryset = CephDaemon.objects.select_related("endpoint", "cluster", "proxmox_node").all()
    serializer_class = serializers.CephDaemonSerializer
    filterset_class = filtersets.CephDaemonFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class CephOSDViewSet(NetBoxModelViewSet):
    queryset = CephOSD.objects.select_related("endpoint", "cluster", "proxmox_node").all()
    serializer_class = serializers.CephOSDSerializer
    filterset_class = filtersets.CephOSDFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class CephPoolViewSet(NetBoxModelViewSet):
    queryset = CephPool.objects.select_related("endpoint", "cluster").all()
    serializer_class = serializers.CephPoolSerializer
    filterset_class = filtersets.CephPoolFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class CephFilesystemViewSet(NetBoxModelViewSet):
    queryset = CephFilesystem.objects.select_related("endpoint", "cluster", "metadata_pool").all()
    serializer_class = serializers.CephFilesystemSerializer
    filterset_class = filtersets.CephFilesystemFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class CephCrushRuleViewSet(NetBoxModelViewSet):
    queryset = CephCrushRule.objects.select_related("endpoint", "cluster").all()
    serializer_class = serializers.CephCrushRuleSerializer
    filterset_class = filtersets.CephCrushRuleFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class CephFlagViewSet(NetBoxModelViewSet):
    queryset = CephFlag.objects.select_related("endpoint", "cluster").all()
    serializer_class = serializers.CephFlagSerializer
    filterset_class = filtersets.CephFlagFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS


class CephHealthCheckViewSet(NetBoxModelViewSet):
    queryset = CephHealthCheck.objects.select_related("endpoint", "cluster").all()
    serializer_class = serializers.CephHealthCheckSerializer
    filterset_class = filtersets.CephHealthCheckFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS
