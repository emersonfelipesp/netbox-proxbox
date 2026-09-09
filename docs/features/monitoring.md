# Monitoring & Observability

netbox-proxbox exposes inventory and operational signals inside NetBox. Use
NetBox job history and live SSE progress for synchronization, the Services tab
for optional Proxmox systemd checks, and the InfluxDB integration below for
time-series metrics.

## Available Signals

- NetBox Job status, logs, and structured output for sync runs
- Live SSE-backed progress updates while a job is running
- Endpoint connectivity badges and status details in the plugin UI
- Proxmox cluster InfluxDB metrics queries through the server-side metrics proxy
- Opt-in Proxmox endpoint systemd service status via the optional `netbox-rpc`
  procedure `os.linux.proxmox.show_systemctl_services`
- Background job history under NetBox's standard **Operations > Background Jobs** pages

## Practical Use

Use these views to confirm endpoint reachability, inspect sync failures, review
per-stage progress during long-running updates, and inspect recent Proxmox
resource measurements without giving a browser direct access to InfluxDB.

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

## InfluxDB Metrics Integration

The InfluxDB integration is a bounded, read-only metrics query path for a
Proxmox cluster. It does not make NetBox a metrics writer: Proxmox continues to
write measurements to InfluxDB, while netbox-proxbox provides a controlled way
to query those measurements from the NetBox operator surface.

### How the integration works

The browser calls NetBox only. The plugin resolves the selected
`ProxmoxMetricsInfluxDB` mapping, decrypts its query token in the NetBox
process, and sends a short-lived structured request to the configured
`proxbox-api` endpoint. proxbox-api validates the request, builds the Flux query,
connects to InfluxDB, and returns normalized columns and rows to NetBox.

```text
NetBox UI or plugin API
        │ mapping id + bounded filters
        ▼
netbox-proxbox ── authenticated request + decrypted token ──► proxbox-api
                                                               │
                                                               │ validated Flux
                                                               ▼
                                                            InfluxDB
```

The trust boundary is deliberate:

- InfluxDB credentials are never sent to the browser, returned by the API, or
  written to ordinary change-log snapshots.
- Callers submit structured filters, not arbitrary Flux. The backend accepts a
  measurement, optional field/node/VM/tag filters, a bounded time window, an
  optional aggregation, and a row limit.
- The InfluxDB base URL must be credential-free HTTPS. The backend validates the
  resolved destination against the shared SSRF policy, disables redirects, and
  verifies TLS by default.
- A backend response is normalized and capped at 1 MiB. The default row limit
  is 500 and the maximum is 5,000. Upstream query timeout is 10 seconds.
- Disabled mappings, disabled Proxmox endpoints, missing encryption keys, and
  undecryptable tokens fail closed.

`netbox-monitoring`, `netbox-nms`, and `netbox-rpc` are not runtime
dependencies of this integration. They can consume or complement the metrics
surface, but the InfluxDB request path belongs to netbox-proxbox and
proxbox-api. The full component contract is in
[Proxmox Metrics Architecture](../developer/proxmox-metrics-architecture.md).

### Configure the plugin

Complete the following sequence in the NetBox UI. The names below match the
plugin model and API fields exactly.

#### 1. Prepare the backend and encryption key

1. Install or deploy a `proxbox-api` version that exposes
   `/proxmox/metrics/influx/query`.
2. In **Plugins → Proxbox → FastAPI Endpoints**, configure the backend URL,
   authentication key, and TLS verification. The endpoint must be enabled and
   reachable from the NetBox process.
3. In **Plugins → Proxbox → Plugin Settings**, set **Encryption key** to a
   Fernet key. This key protects the plugin-owned InfluxDB query token in the
   NetBox database; it is not the proxbox-api authentication key or
   `PROXBOX_ENCRYPTION_KEY`.

Generate a Fernet key in the NetBox environment and store it through the
supported Plugin Settings UI or API. Keep the value in the deployment secret
store and back it up according to the NetBox recovery policy:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Do not put the generated value in source control, a public issue, or a browser
request log. Changing an encryption key is a controlled credential operation;
follow the recovery and rotation guidance in
[Plugin Settings](../configuration/plugin-settings.md#encryption-and-credential-storage).

#### 2. Confirm the source objects

Run a Proxbox sync first, or otherwise confirm that the target
`ProxmoxEndpoint` and `ProxmoxCluster` records exist. The selected cluster must
belong to the selected endpoint. A mapping is unique by cluster and name, so
use a distinct **Name** for multiple mappings for one cluster.

#### 3. Create an InfluxDB Metrics mapping

Open **Plugins → Proxbox → InfluxDB Metrics → Add** and fill in:

| Plugin field | What to enter |
|---|---|
| **Name** (`name`) | Operator label for this mapping; defaults to `default`. |
| **Proxmox endpoint** (`endpoint`) | The Proxmox endpoint whose cluster writes the measurements. |
| **Proxmox cluster** (`proxmox_cluster`) | The cluster associated with the InfluxDB bucket. It must belong to the selected endpoint. |
| **InfluxDB URL** (`influx_url`) | Credential-free HTTPS base URL, such as `https://influxdb.example:8086`. Do not include userinfo, a query string, or a fragment. |
| **InfluxDB organization** (`org`) | InfluxDB v2 organization; default `nmulticloud`. |
| **InfluxDB bucket** (`bucket`) | Bucket containing the Proxmox measurements; default `proxmox`. |
| **Measurement prefix** (`measurement_prefix`) | Optional prefix automatically added to the requested measurement. Leave blank unless the writer uses one. |
| **InfluxDB query token** (`query_token`) | A token with the minimum read permission for the selected bucket. It is write-only and is encrypted before persistence. |
| **Verify TLS** (`verify_tls`) | Keep enabled for normal HTTPS deployments. Disable only for a controlled environment where the backend's insecure-TLS override permits it. |
| **Enabled** (`enabled`) | Enable only after the URL and token are valid. Disabled mappings remain inventory-only and cannot be queried. |
| **Comments** (`comments`) | Optional operator notes. Never record the token or other secret material. |

Saving the form validates the URL, endpoint/cluster relationship, encryption
key, and token requirement. On later edits, leave the token blank to retain the
stored credential. The UI shows only a configured/not-configured state; it does
not redisplay the token.

#### 4. Query the metrics

Open the mapping detail page and choose **View metrics**. Enter the required
measurement and, when needed, a field, node, VM ID, tag key/value, time range,
and aggregation. Supported aggregation functions are `count`, `first`, `last`,
`max`, `mean`, `min`, and `sum`; `aggregation_every` and
`aggregation_function` must be supplied together.

Use a narrow time window and field filter first. The result reports the query
window, row count, truncation status, normalized columns, and rows. A truncated
result is a signal to reduce the time range or add filters; it is not a reason
to increase the server-side response cap.

### REST API setup and query

The metadata surface is a standard NetBox plugin API:

```text
GET    /api/plugins/proxbox/metrics-influxdb/
GET    /api/plugins/proxbox/metrics-influxdb/{id}/
POST   /api/plugins/proxbox/metrics-influxdb/
PUT    /api/plugins/proxbox/metrics-influxdb/{id}/
PATCH  /api/plugins/proxbox/metrics-influxdb/{id}/
DELETE /api/plugins/proxbox/metrics-influxdb/{id}/
GET    /api/plugins/proxbox/metrics-influxdb/{id}/data/
```

`query_token` is accepted only as a write-only input. A create or replacement
request must include it; an update may omit it to retain the existing token.
The response exposes `query_token_configured` and
`credential_encryption_state`, never ciphertext or plaintext.

Example bounded query, after obtaining the mapping ID through the metadata
endpoint:

```bash
curl -G \
  -H "Authorization: Token <netbox-token>" \
  --data-urlencode "measurement=cpu" \
  --data-urlencode "field=usage" \
  --data-urlencode "node=pve01" \
  --data-urlencode "time_start=-30m" \
  --data-urlencode "time_stop=now()" \
  --data-urlencode "limit=500" \
  "https://netbox.example.com/api/plugins/proxbox/metrics-influxdb/<id>/data/"
```

The API accepts the same bounded fields as the UI: `time_start`, `time_stop`,
`measurement`, `field`, `node`, `vmid`, `tag_key`, `tag_value`,
`aggregation_every`, `aggregation_function`, and `limit`. It does not accept a
Flux string or direct InfluxDB connection parameters.

### Troubleshooting

| Symptom | Check |
|---|---|
| Mapping cannot be enabled | Confirm the plugin Encryption key is configured and the query token was entered. An enabled mapping requires a decryptable token and a valid HTTPS URL. |
| Backend unavailable | Check the enabled FastAPI endpoint, its API key, TLS settings, and connectivity from the NetBox host to proxbox-api. |
| InfluxDB connection or TLS error | Confirm the credential-free base URL, DNS/SSRF allowlist, certificate chain, and `Verify TLS` setting. Do not put a token in the URL. |
| Empty result | Confirm the organization, bucket, measurement prefix, measurement, field, cluster's writer configuration, and time window. |
| Result is truncated | Reduce the time range or add node, VM, tag, or field filters. The maximum is 5,000 rows and 1 MiB. |
| Token shows recovery required | Re-enter the token with the active plugin Encryption key, save the mapping, and explicitly re-enable it if the mapping was quarantined during an upgrade. |

During an upgrade, legacy external token references are not resolved. Affected
mappings are disabled, discarded references are cleared, and historical
change-log snapshots are masked. Remediation is intentionally explicit: enter a
credential-free HTTPS URL and a new query token, verify the mapping, and enable
it again. The migration warning never records discarded secret values.

For endpoint routes, field names, filters, and normalized response details, see
[Infrastructure API](../api/infrastructure.md#proxmox-influxdb-metrics-endpoint).
