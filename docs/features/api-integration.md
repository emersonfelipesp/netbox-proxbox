# API Integration

Proxbox exposes two API layers:

- The NetBox plugin API for Proxbox models inside NetBox
- The separate `proxbox-api` backend that performs Proxmox discovery and sync orchestration

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
