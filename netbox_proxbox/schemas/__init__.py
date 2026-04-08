"""ProxBox Pydantic V2 schema package.

Import the most commonly used schemas from here for convenience.
"""

from netbox_proxbox.schemas.backend_proxy import (
    BackendRequestContext,
    FastAPIUrlDict,
    SseCompletePayload,
    SseDiscoveryPayload,
    SseErrorDetailPayload,
    SseErrorPayload,
    SseEventType,
    SseFrame,
    SseItemProgressPayload,
    SseItemInfo,
    SsePhaseSummaryPayload,
    SseProgressInfo,
    SseSubstepPayload,
    SseTimingInfo,
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
from netbox_proxbox.schemas.backup_routine import (
    BackupRoutineSchema,
    GetClusterBackupIdResponse,
    GetClusterBackupResponseItem,
)

__all__ = [
    "AuthStatusLiteral",
    "BackendRequestContext",
    "BackupRoutineSchema",
    "ClusterSyncResult",
    "FastAPIStatusResult",
    "FastAPIUrlDict",
    "GetClusterBackupIdResponse",
    "GetClusterBackupResponseItem",
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
    "SseDiscoveryPayload",
    "SseErrorDetailPayload",
    "SseErrorPayload",
    "SseEventType",
    "SseFrame",
    "SseItemInfo",
    "SseItemProgressPayload",
    "SsePhaseSummaryPayload",
    "SseProgressInfo",
    "SseSubstepPayload",
    "SseTimingInfo",
    "StatusLiteral",
    "StorageContentRecord",
    "StorageUsage",
    "SyncJobData",
    "SyncJobParams",
]
