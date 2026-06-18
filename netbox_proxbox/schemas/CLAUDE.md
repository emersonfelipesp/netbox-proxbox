# `netbox_proxbox.schemas`

This directory contains Pydantic V2 models for backend payloads, normalized sync context, and OpenAPI helpers.

## Files And Ownership

- [`__init__.py`](./__init__.py): re-exports commonly used schemas for convenience.
- [`_base.py`](./_base.py): shared base classes for Pydantic models.
- [`_formatters.py`](./_formatters.py): formatting helpers for schema output.
- [`backend_proxy.py`](./backend_proxy.py): request context, SSE frame types, and URL helpers for proxbox-api communication (`BackendRequestContext`, `SseFrame`, `SseCompletePayload`, `SseErrorPayload`, `FastAPIUrlDict`).
- [`openapi_schema.py`](./openapi_schema.py): OpenAPI summary schema for caching backend API metadata (`OpenAPISummary`).
- [`proxmox_node.py`](./proxmox_node.py): Proxmox cluster/node response models (`ProxmoxClusterStatusRecord`, `ProxmoxClusterStatusResponse`, `ProxmoxClusterSummary`, `ProxmoxNodeDetail`, `ProxmoxNodeRow`).
- [`proxmox_storage.py`](./proxmox_storage.py): Proxmox storage models (`ProxmoxStorageRecord`, `StorageContentRecord`, `StorageUsage`).
- [`proxmox_vm.py`](./proxmox_vm.py): Proxmox VM/guest models (`ProxmoxGuestSummary`, `ProxmoxResourceRecord`, `ProxmoxVMConfig`).
- [`service_status.py`](./service_status.py): service health check models (`ServiceCheckResult`, `FastAPIStatusResult`, `KeepalivePayload`, `AuthStatusLiteral`, `StatusLiteral`).
- [`sync_result.py`](./sync_result.py): sync job payload models (`SyncJobData`, `SyncJobParams`, `ClusterSyncResult`).
- [`backup_routine.py`](./backup_routine.py): backup routine schema models (`BackupRoutineSchema`, `GetClusterBackupIdResponse`, `GetClusterBackupResponseItem`).
- [`schedule_parser.py`](./schedule_parser.py): helpers for parsing and normalising Proxmox schedule strings (cron and PVE-specific formats).

## Dependencies

- Inbound: views, jobs, and services modules import schemas for request/response validation and SSE parsing.
- Outbound: `pydantic`, `pydantic_core`, and standard library types.

## Notes

- All schemas use Pydantic V2 (`pydantic.BaseModel` with `model_config`).
- Service status literals include `disabled` so a deliberately skipped endpoint can be represented separately from an actual `error`.
- SSE-related schemas in `backend_proxy.py` parse streaming frames from proxbox-api.
- These models are transport-layer contracts; they do not persist to the database.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
