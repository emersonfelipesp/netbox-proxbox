"""Persisted models for the netbox-ceph plugin."""

from netbox_ceph.models.ceph import (
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

__all__ = [
    "CephCluster",
    "CephCrushRule",
    "CephDaemon",
    "CephFilesystem",
    "CephFlag",
    "CephHealthCheck",
    "CephOSD",
    "CephPluginSettings",
    "CephPool",
]
