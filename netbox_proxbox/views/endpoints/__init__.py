"""Re-export endpoint model views for the plugin UI."""

from .fastapi import (
    FastAPIEndpointBulkImportView,
    FastAPIEndpointDeleteView,
    FastAPIEndpointEditView,
    FastAPIEndpointExportView,
    FastAPIEndpointListView,
    FastAPIEndpointView,
    FastAPIOpenAPIView,
)
from .netbox import (
    NetBoxEndpointBulkImportView,
    NetBoxEndpointDeleteView,
    NetBoxEndpointEditView,
    NetBoxEndpointExportView,
    NetBoxEndpointListView,
    NetBoxEndpointView,
)
from .proxmox import (
    ProxmoxEndpointBulkDeleteView,
    ProxmoxEndpointBulkDisableView,
    ProxmoxEndpointBulkEnableView,
    ProxmoxEndpointBulkImportView,
    ProxmoxEndpointDeleteView,
    ProxmoxEndpointEditView,
    ProxmoxEndpointExportView,
    ProxmoxEndpointListView,
    ProxmoxEndpointServicesView,
    ProxmoxEndpointView,
)
from .proxmox_sync_now import ProxmoxEndpointSyncNowView
