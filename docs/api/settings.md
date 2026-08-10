# Plugin Settings API

The `ProxboxPluginSettings` model is a **singleton** — there is exactly one row, accessed via `singleton_key="default"`. It exposes runtime tuning parameters that control sync concurrency, NetBox client behavior, SSRF protection, and security.

!!! warning "GET and PATCH only"
    POST, PUT, and DELETE are not supported on this endpoint. Use PATCH to update individual settings.

```
GET   /api/plugins/proxbox/settings/
GET   /api/plugins/proxbox/settings/{id}/
PATCH /api/plugins/proxbox/settings/{id}/
```

For common API conventions (authentication, pagination, nested serializers), see [API Overview](index.md). For the human-readable description of every tunable (defaults, env-var overrides, resolution order), see [Plugin Settings configuration guide](../configuration/plugin-settings.md).

---

**Example — read current settings:**

```bash
curl -H "Authorization: Token <token>" \
     http://netbox.example.com/api/plugins/proxbox/settings/
```

**Example — tune sync concurrency:**

```bash
curl -X PATCH \
     -H "Authorization: Token <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "proxbox_fetch_max_concurrency": 20,
       "vm_sync_max_concurrency": 10,
       "bulk_batch_size": 100
     }' \
     http://netbox.example.com/api/plugins/proxbox/settings/1/
```

**Example — disable SSRF protection for a private-only deployment:**

```bash
curl -X PATCH \
     -H "Authorization: Token <token>" \
     -H "Content-Type: application/json" \
     -d '{"ssrf_protection_enabled": false}' \
     http://netbox.example.com/api/plugins/proxbox/settings/1/
```

---

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/settings/1/",
  "display": "Proxbox Plugin Settings",
  "singleton_key": "default",
  "use_guest_agent_interface_name": true,
  "vm_interface_sync_strategy": "guest_os_model",
  "proxbox_fetch_max_concurrency": 8,
  "ignore_ipv6_link_local_addresses": true,
  "delete_orphans": false,
  "custom_fields_enabled": false,
  "cloud_network_lock_enabled": true,
  "cloud_customer_prefix_id": 123,
  "cloud_customer_bridge": "vmbr1",
  "cloud_customer_vlan_tag": 2050,
  "cloud_customer_gateway": "168.0.98.1",
  "netbox_max_concurrent": 1,
  "netbox_max_retries": 5,
  "netbox_retry_delay": "2.00",
  "netbox_get_cache_ttl": "60.00",
  "netbox_openapi_persist": true,
  "bulk_batch_size": 50,
  "bulk_batch_delay_ms": 500,
  "backup_batch_size": 5,
  "backup_batch_delay_ms": 200,
  "vm_sync_max_concurrency": 4,
  "reconciliation_engine": "python",
  "reconciliation_compare_strict": false,
  "ceph_task_timeout": 300.0,
  "ceph_task_poll_interval": 1.0,
  "ceph_run_lease_seconds": 360.0,
  "custom_fields_request_delay": "0.00",
  "backend_log_file_path": "/var/log/proxbox.log",
  "ssrf_protection_enabled": true,
  "allow_private_ips": true,
  "additional_allowed_ip_ranges": "",
  "explicitly_blocked_ip_ranges": "",
  "tags": [],
  "custom_fields": {},
  "created": "2026-01-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

The ordinary list/detail serializer omits `encryption_key` because it is
write-only. `GET /api/plugins/proxbox/settings/runtime/` additionally returns
`"encryption_key_configured": true|false`. For compatibility with current
proxbox-api releases, that backend-only runtime route returns the key only to a
superuser or caller with plugin-settings change permission; every other caller
receives `"encryption_key": ""`. Provision proxbox-api's own local encryption
key before this deprecated compatibility fallback is removed.

---

## Data Model

### Read-Only Fields

These fields are set by the system and cannot be modified via PATCH:

| Field | Type | Description |
|---|---|---|
| `id` | integer | Database ID of the singleton row |
| `url` | string | Canonical API URL |
| `display` | string | Human-readable label |
| `singleton_key` | string | Always `"default"` — enforces the singleton constraint |
| `created` | datetime | When the settings record was created |
| `last_updated` | datetime | When the settings record was last modified |

### Sync Tuning

| Field | Type | Description |
|---|---|---|
| `proxbox_fetch_max_concurrency` | integer | Maximum number of concurrent Proxmox API fetch operations |
| `vm_sync_max_concurrency` | integer | Maximum number of VMs synced in parallel per sync run |
| `reconciliation_engine` | string | VM operation-queue engine used by proxbox-api: `python`, `compare`, or `rust` |
| `bulk_batch_size` | integer | Number of objects per batch in bulk NetBox write operations |
| `bulk_batch_delay_ms` | integer | Delay in milliseconds between bulk write batches |
| `backup_batch_size` | integer | Records per batch during backup/snapshot reconciliation (kept lower than bulk batches because each item triggers Proxmox calls). Default `5`. |
| `backup_batch_delay_ms` | integer | Milliseconds to pause between backup batches. Default `200`. |
| `reconciliation_engine` | string | VM operation-queue engine used by proxbox-api: `python`, `compare`, or `rust`. Controlled by ProxboxPluginSettings, not backend environment variables. |
| `reconciliation_compare_strict` | boolean | In `compare` mode, fail the sync on Rust/Python mismatch instead of only logging it. |
| `custom_fields_request_delay` | decimal | Delay in seconds between custom field update requests |
| `delete_orphans` | boolean | When `true`, full-update may delete Proxbox-discovered VMs with stale or missing `proxbox_last_run_id` stamps |
| `custom_fields_enabled` | boolean | Deprecated. When `false` (the default), the typed `Proxbox*SyncState` models are the sole source of truth and the legacy reflection custom fields are not written, read, or reconciled. When `true`, proxbox-api restores legacy custom-field writes/reads/reconcile and emits deprecation warnings. |

### NetBox Client

| Field | Type | Description |
|---|---|---|
| `netbox_max_concurrent` | integer | Maximum concurrent connections to the NetBox API |
| `netbox_max_retries` | integer | Number of retry attempts on failed NetBox API requests |
| `netbox_retry_delay` | decimal | Delay in seconds between retry attempts |
| `netbox_get_cache_ttl` | decimal | TTL in seconds for cached NetBox GET responses |
| `netbox_openapi_persist` | boolean | When `true` (default), proxbox-api caches the resolved NetBox OpenAPI schema on disk. When `false`, schema resolution runs fully in-memory and never reads/writes the filesystem (read-only filesystems, no-disk-write deployments). Overridable by the `PROXBOX_NETBOX_OPENAPI_PERSIST` backend environment variable. |

### Ceph Control Plane

| Field | Type | Description |
|---|---|---|
| `ceph_task_timeout` | number | Maximum total wait for a submitted Proxmox Ceph task. Default `300.00`, accepted range `1.00–3600.00`; overridden by `PROXBOX_CEPH_TASK_TIMEOUT`. |
| `ceph_task_poll_interval` | number | Delay between provider task-status checks. Default `1.00`, accepted range `0.10–60.00`, and must not exceed `ceph_task_timeout`; overridden by `PROXBOX_CEPH_TASK_POLL_INTERVAL`. |
| `ceph_run_lease_seconds` | number | Renewable durable run lease. Default `360.00`, accepted range `1.00–3600.00`; overridden by `PROXBOX_CEPH_RUN_LEASE_SECONDS` and renewed independently from provider polling. |

proxbox-api resolves each value as **environment override → plugin setting →
built-in default**, captures one immutable request timing snapshot, and persists
the run lease duration. A settings change therefore applies only to later runs
and cannot change the lease or recovery rules for an operation already in
flight. Malformed or non-finite environment values fall through, finite
out-of-range values are clamped, and the resolved polling interval is normalized
to at most the task timeout. Invalid plugin values and polling intervals greater
than the task timeout are rejected by the model, form, and API serializer.

### Network Behavior

| Field | Type | Description |
|---|---|---|
| `vm_interface_sync_strategy` | string | `guest_os_model` keeps Proxmox `netX` NICs as core `VMInterface` rows and stores guest-agent OS names in `GuestVMInterface`; `legacy_rename` preserves the older single-interface rename behavior |
| `use_guest_agent_interface_name` | boolean | Deprecated. Used only when `vm_interface_sync_strategy=legacy_rename`; then it controls whether guest-agent names replace Proxmox-reported names when syncing network interfaces |
| `ignore_ipv6_link_local_addresses` | boolean | When `true`, skip IPv6 link-local addresses (`fe80::/64`) during interface sync |

### Cloud Customer Network

| Field | Type | Description |
|---|---|---|
| `cloud_network_lock_enabled` | boolean | When `true`, cloud provisioning integrations should treat the configured customer network fields as authoritative |
| `cloud_customer_prefix_id` | integer or null | Primary key of the NetBox IPAM Prefix designated as the cloud customer network |
| `cloud_customer_bridge` | string | Proxmox bridge name used for customer-facing cloud interfaces |
| `cloud_customer_vlan_tag` | integer or null | VLAN tag associated with the designated cloud customer network |
| `cloud_customer_gateway` | string | Gateway IP address for the designated cloud customer network |

Populate these fields with `python manage.py ensure_cloud_customer_network ...`
so proxbox-api and nms-backend can resolve the cloud customer network without
hardcoded estate values.

### SSRF Protection

| Field | Type | Description |
|---|---|---|
| `ssrf_protection_enabled` | boolean | Enable SSRF protection on outbound requests from the plugin |
| `allow_private_ips` | boolean | When `true`, allow requests to RFC 1918 private IP ranges (disabled by default) |
| `additional_allowed_ip_ranges` | string | Newline-separated list of CIDR ranges to allow in addition to public IPs |
| `explicitly_blocked_ip_ranges` | string | Newline-separated list of CIDR ranges to always block regardless of other settings |

### Security

| Field | Type | Description |
|---|---|---|
| `encryption_key` | string | Write-only Fernet key for plugin-owned ciphertext in the NetBox database. Ordinary GET responses omit it; the backend-only `/runtime/` compatibility route returns it only to a superuser or caller with plugin-settings change permission. Use `encryption_key_configured` to test presence. Ordinary PATCH cannot clear or replace the key while registered ciphertext exists; use the UI's verified rotation or separately permissioned destructive reset workflow. |

The plugin key should be a different security domain from proxbox-api's
`PROXBOX_ENCRYPTION_KEY` (which protects proxbox-api's own database) and from
the `FastAPIEndpoint` API key (which authenticates requests). Current
proxbox-api releases retain a permission-gated runtime fallback for existing
deployments; migrate the backend to local key configuration before that
compatibility path is removed.

Verified plugin-key rotation additionally requires every enabled, adopted,
operational backend to serve the paired version-1
`/admin/encryption/status` attestation: it must report the active cached key
source as `env` or `local` and confirm that the active key decrypts every
encrypted backend credential. Disabled, pending, retired, or trust-drifted rows
are never contacted; their ciphertext rotates locally. The current legacy
source-only response is intentionally insufficient for an operational backend,
even when it reports `env` or `local`.

### Logging

| Field | Type | Description |
|---|---|---|
| `backend_log_file_path` | string | Path to the Proxbox backend log file displayed in the Backend Logs UI page |
