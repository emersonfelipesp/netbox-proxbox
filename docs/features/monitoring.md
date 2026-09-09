# Monitoring & Observability

Current Proxbox releases include several operator-facing observability features.

## Available Signals

- NetBox Job status, logs, and structured output for sync runs
- Live SSE-backed progress updates while a job is running
- Endpoint connectivity badges and status details in the plugin UI
- Proxmox cluster InfluxDB metrics endpoint metadata for external observability
  integrations
- Opt-in Proxmox endpoint systemd service status via the optional `netbox-rpc`
  procedure `os.linux.proxmox.show_systemctl_services`
- Background job history under NetBox's standard **Operations > Background Jobs** pages

## Practical Use

Use these views to confirm endpoint reachability, inspect sync failures, and review per-stage progress during long-running updates.

## Proxmox Endpoint Services

The Proxmox endpoint **Services** tab is an agentless, pull-based projection of
systemd service state. netbox-proxbox does not perform SSH itself. It creates a
`netbox-rpc` `RPCExecution` for the read-only
`os.linux.proxmox.show_systemctl_services` procedure, assigns it to the
`ProxmoxEndpoint`, and stores the asynchronous result when the RPC job finishes.

The gate is intentionally strict. Service monitoring must be enabled on the
endpoint, and the endpoint is eligible only when all of these are true:

- `allow_writes=True`
- `access_methods="api_ssh"`
- the endpoint has complete SSH credentials registered
- netbox-rpc is effectively enabled for the endpoint — the per-endpoint
  `rpc_enabled` override when set, otherwise the global netbox-rpc opt-in

The last condition matters because each collection tick dispatches a netbox-rpc
`RPCExecution`, and the nms-backend RPC dispatch gate fails closed on an
RPC-disabled endpoint (403 `RPC_ENDPOINT_DISABLED`). Without this gate an
operator could enable monitoring on an RPC-disabled endpoint and accumulate
`failed`/`last_error` state every tick with no upfront signal; the strict
eligibility check now refuses the enable and skips the doomed dispatch.

The RPC backend uses the endpoint's own SSH credential. Scheduled collection
runs from a one-minute NetBox system tick and respects
`service_monitoring_interval_minutes`. The tab's **Refresh now** button queues an
on-demand collection with the same eligibility and `change_proxmoxendpoint`
permission checks.

Projection is two-phase: queue a pending `ProxmoxServiceCollection`, then later
reconcile finished `RPCExecution.result` payloads into `ProxmoxServiceSample`,
`ProxmoxServiceStatus`, and heartbeat fields on the endpoint. A
`reachable=false` result means the target was down or unreachable; it is recorded
without updating the last-success heartbeat.

## InfluxDB Metrics Endpoints

`ProxmoxMetricsInfluxDB` records describe the InfluxDB endpoint associated with a
Proxmox cluster: source `ProxmoxEndpoint`, `ProxmoxCluster`, InfluxDB URL,
organization, bucket, optional measurement prefix, TLS verification, and enabled
state. Query tokens are encrypted by the plugin and are never
returned to the UI or API.

The detail page's **View metrics** action and the API `data` action retrieve
normalized data through `proxbox-api`. The browser has no InfluxDB credentials,
Flux authoring, or direct InfluxDB access. See
[Proxmox Metrics Architecture](../developer/proxmox-metrics-architecture.md).

During upgrade, legacy external token references are cleared, affected mappings
are disabled, and a remediation marker is appended to their comments. Existing
change-log snapshots are masked as part of the same upgrade. To remediate a
quarantined mapping, enter a credential-free HTTPS base URL and a new query
token, then explicitly re-enable the mapping. The migration warning log never
records discarded values; its reverse operation is intentionally irreversible.
