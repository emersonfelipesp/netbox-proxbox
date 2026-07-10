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
| `reconciliation_engine` | string | VM operation-queue engine used by proxbox-api: `python`, `compare`, or `rust`. Controlled by ProxboxPluginSettings, not backend environment variables. |
| `reconciliation_compare_strict` | boolean | In `compare` mode, fail the sync on Rust/Python mismatch instead of only logging it. |
| `custom_fields_request_delay` | decimal | Delay in seconds between custom field update requests |
| `delete_orphans` | boolean | When `true`, full-update may delete Proxbox-discovered VMs with stale or missing `proxbox_last_run_id` stamps |

### NetBox Client

| Field | Type | Description |
|---|---|---|
| `netbox_max_concurrent` | integer | Maximum concurrent connections to the NetBox API |
| `netbox_max_retries` | integer | Number of retry attempts on failed NetBox API requests |
| `netbox_retry_delay` | decimal | Delay in seconds between retry attempts |
| `netbox_get_cache_ttl` | decimal | TTL in seconds for cached NetBox GET responses |
| `netbox_openapi_persist` | boolean | When `true` (default), proxbox-api caches the resolved NetBox OpenAPI schema on disk. When `false`, schema resolution runs fully in-memory and never reads/writes the filesystem (read-only filesystems, no-disk-write deployments). Overridable by the `PROXBOX_NETBOX_OPENAPI_PERSIST` backend environment variable. |

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
| `encryption_key` | string | Key used for encrypting sensitive values stored in the database |

### Logging

| Field | Type | Description |
|---|---|---|
| `backend_log_file_path` | string | Path to the Proxbox backend log file displayed in the Backend Logs UI page |
