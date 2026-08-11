# API Integration

Proxbox exposes two API layers:

- The NetBox plugin API for Proxbox models inside NetBox
- The separate `proxbox-api` backend that performs Proxmox discovery and sync orchestration

The NetBox plugin API additionally advertises a read-only semantic-tool
manifest at `/api/plugins/proxbox/mcp/`. This is metadata for the standard
`netbox-sdk` MCP bridge, not a third execution layer: `list_sync_jobs` and
`schedule_sync` both reuse the existing `sync/schedule/` DRF endpoint and its
NetBox permission checks. Proxbox does not embed FastMCP or create another
credential store. An explicit `proxmox_endpoint_ids` scope fails closed: every
requested ID must identify an enabled endpoint or the API returns HTTP 400
without enqueueing. Omitting the scope retains the deliberate all-enabled
behavior, while an explicitly empty scope is rejected rather than widened.
Recurrence value and unit must be supplied together. `schedule_sync` is
advertised as destructive because reconciliation
can delete stale NetBox inventory records, while the existing mutation and
`core.add_job` gates continue to control dispatch.

## Current Flow

1. The NetBox plugin stores endpoint records.
2. A UI action or scheduled job triggers a Proxbox sync.
3. The plugin calls `proxbox-api`, usually through SSE-backed job execution.
4. The backend talks to Proxmox and NetBox APIs, then streams progress back.

The plugin is primarily an integration and synchronization layer, not a replacement control plane for Proxmox.

## API Reference

For complete endpoint documentation — HTTP methods, field tables, filter parameters, curl examples, and sample responses — see the dedicated API Reference section:

- [Overview](../api/index.md) — authentication, pagination, common patterns, and the full endpoint map
- [Endpoint Configuration](../api/endpoints.md) — ProxmoxEndpoint, NetBoxEndpoint, FastAPIEndpoint
- [Infrastructure](../api/infrastructure.md) — ProxmoxCluster, ProxmoxNode, ProxmoxStorage
- [VM Data](../api/vm-data.md) — VMBackup, VMSnapshot, VMTaskHistory
- [Operations](../api/operations.md) — BackupRoutine, Replication
- [Settings](../api/settings.md) — ProxboxPluginSettings
