# API Integration

Proxbox exposes two API layers:

- The NetBox plugin API for Proxbox models inside NetBox
- The separate `proxbox-api` backend that performs Proxmox discovery and sync orchestration

The NetBox plugin API additionally advertises a read-only semantic-tool
manifest at `/api/plugins/proxbox/mcp/`. This is producer metadata for a future
compatible `netbox-sdk` MCP bridge, not a third execution layer. No released SDK
identity is currently activated: the checked activation artifact remains
blocked until an exact immutable SDK passes the lossless-number and bounded
RFC3339 paired vectors in CI. After that activation, agents discover and call
the descriptors through generic `plugin_list_tools` and `plugin_call_tool` MCP
envelopes; `list_sync_jobs` and `schedule_sync` both reuse the existing
`sync/schedule/` DRF endpoint and its
NetBox permission checks. Proxbox does not embed FastMCP or create another
credential store. An explicit `proxmox_endpoint_ids` scope fails closed: every
requested ID must identify an enabled endpoint or the API returns HTTP 400
without enqueueing. Omitting the scope retains the deliberate all-enabled
behavior, while an explicitly empty scope is rejected rather than widened.
Bridge v1 does not expose `netbox_endpoint_ids`. It requires concrete
`sync_stages`, strict RFC 3339 scheduling, and an exactly-one-unit recurrence
bounded to the persisted minute field. `schedule_sync` is
advertised as destructive because reconciliation
can delete stale NetBox inventory records, while the existing mutation and
`core.add_job` gates continue to control dispatch. The SDK mutation opt-in is
global to every MCP mutation, and ambiguous outcomes are never auto-retried.
Endpoint IDs are positive signed-64-bit PKs. Integer JSON literals retain the
full range, while integral float/Decimal forms normalize only within the exact
`9007199254740991` safe range; unsafe floats and invalid bounds fail before ORM
lookup. Stage selection controls only the 13
SSE stages: endpoint preflight plus scoped cluster/node, firewall, datacenter,
and normally VM-template reconciliation still run. The exact unique full set is
stored as internal `["all"]` for recurring and repair-job identity.

See [Semantic MCP Bridge](../api/semantic-mcp-bridge.md) for the complete
discovery and invocation sequence, strict request contract, executable JSON
examples, error matrix, agent safety guidance, compatibility policy, and
troubleshooting runbook.

## Current Flow

1. The NetBox plugin stores endpoint records.
2. A UI action or scheduled job triggers a Proxbox sync.
3. The plugin calls `proxbox-api`, usually through SSE-backed job execution.
4. The backend talks to Proxmox and NetBox APIs, then streams progress back.

The plugin is primarily an integration and synchronization layer, not a replacement control plane for Proxmox.

## API Reference

For complete endpoint documentation — HTTP methods, field tables, filter parameters, curl examples, and sample responses — see the dedicated API Reference section:

- [Overview](../api/index.md) — authentication, pagination, common patterns, and the full endpoint map
- [Semantic MCP Bridge](../api/semantic-mcp-bridge.md) — bridge-v1 discovery, tools, safety, examples, errors, and compatibility
- [Endpoint Configuration](../api/endpoints.md) — ProxmoxEndpoint, NetBoxEndpoint, FastAPIEndpoint
- [Infrastructure](../api/infrastructure.md) — ProxmoxCluster, ProxmoxNode, ProxmoxStorage
- [VM Data](../api/vm-data.md) — VMBackup, VMSnapshot, VMTaskHistory
- [Operations](../api/operations.md) — BackupRoutine, Replication
- [Settings](../api/settings.md) — ProxboxPluginSettings
