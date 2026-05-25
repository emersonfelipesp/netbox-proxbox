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
  "proxbox_fetch_max_concurrency": 8,
  "ignore_ipv6_link_local_addresses": true,
  "delete_orphans": false,
  "netbox_max_concurrent": 1,
  "netbox_max_retries": 5,
  "netbox_retry_delay": "2.00",
  "netbox_get_cache_ttl": "60.00",
  "bulk_batch_size": 50,
  "bulk_batch_delay_ms": 500,
  "backup_batch_size": 5,
  "backup_batch_delay_ms": 200,
   "vm_sync_max_concurrency": 4,
   "reconciliation_engine": "python",
  "custom_fields_request_delay": "0.00",
  "backend_log_file_path": "/var/log/proxbox.log",
  "ssrf_protection_enabled": true,
  "allow_private_ips": true,
  "additional_allowed_ip_ranges": "",
  "explicitly_blocked_ip_ranges": "",
  "encryption_key": "",
  "tags": [],
  "custom_fields": {},
  "created": "2026-01-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

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
| `custom_fields_request_delay` | decimal | Delay in seconds between custom field update requests |
| `delete_orphans` | boolean | When `true`, full-update may delete Proxbox-discovered VMs with stale or missing `proxbox_last_run_id` stamps |

### NetBox Client

| Field | Type | Description |
|---|---|---|
| `netbox_max_concurrent` | integer | Maximum concurrent connections to the NetBox API |
| `netbox_max_retries` | integer | Number of retry attempts on failed NetBox API requests |
| `netbox_retry_delay` | decimal | Delay in seconds between retry attempts |
| `netbox_get_cache_ttl` | decimal | TTL in seconds for cached NetBox GET responses |

### Network Behavior

| Field | Type | Description |
|---|---|---|
| `use_guest_agent_interface_name` | boolean | When `true`, use the QEMU guest agent interface name instead of the Proxmox-reported name when syncing network interfaces |
| `ignore_ipv6_link_local_addresses` | boolean | When `true`, skip IPv6 link-local addresses (`fe80::/64`) during interface sync |

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
| `encryption_key` | string | Key used for encrypting sensitive values stored in the database |

### Logging

| Field | Type | Description |
|---|---|---|
| `backend_log_file_path` | string | Path to the Proxbox backend log file displayed in the Backend Logs UI page |
