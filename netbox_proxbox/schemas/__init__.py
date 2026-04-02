"""ProxBox Pydantic V2 schema package.

Import the most commonly used schemas from here for convenience.
"""

from netbox_proxbox.schemas.backend_proxy import (
    BackendRequestContext,
    FastAPIUrlDict,
    SseCompletePayload,
    SseErrorPayload,
    SseFrame,
)
from netbox_proxbox.schemas.openapi_schema import OpenAPISummary
from netbox_proxbox.schemas.proxmox_node import (
    ProxmoxClusterStatusRecord,
    ProxmoxClusterStatusResponse,
    ProxmoxClusterSummary,
    ProxmoxNodeDetail,
    ProxmoxNodeRow,
)
from netbox_proxbox.schemas.proxmox_storage import (
    ProxmoxStorageRecord,
    StorageContentRecord,
    StorageUsage,
)
from netbox_proxbox.schemas.proxmox_vm import (
    ProxmoxGuestSummary,
    ProxmoxResourceRecord,
    ProxmoxVMConfig,
)
from netbox_proxbox.schemas.service_status import (
    AuthStatusLiteral,
    FastAPIStatusResult,
    KeepalivePayload,
    ServiceCheckResult,
    StatusLiteral,
)
from netbox_proxbox.schemas.sync_result import (
    ClusterSyncResult,
    SyncJobData,
    SyncJobParams,
)

__all__ = [
    "AuthStatusLiteral",
    "BackendRequestContext",
    "ClusterSyncResult",
    "FastAPIStatusResult",
    "FastAPIUrlDict",
    "KeepalivePayload",
    "OpenAPISummary",
    "ProxmoxClusterStatusRecord",
    "ProxmoxClusterStatusResponse",
    "ProxmoxClusterSummary",
    "ProxmoxGuestSummary",
    "ProxmoxNodeDetail",
    "ProxmoxNodeRow",
    "ProxmoxResourceRecord",
    "ProxmoxStorageRecord",
    "ProxmoxVMConfig",
    "ServiceCheckResult",
    "SseCompletePayload",
    "SseErrorPayload",
    "SseFrame",
    "StatusLiteral",
    "StorageContentRecord",
    "StorageUsage",
    "SyncJobData",
    "SyncJobParams",
]
