# Plugin Settings

Proxbox exposes a singleton **Plugin Settings** object for runtime behavior toggles. Create or edit it under **Plugins → Proxbox → Plugin Settings**.

!!! tip "Programmatic access"
    Every field below is also readable and writable through the [Plugin Settings API](../api/settings.md) (GET + PATCH).

## Runtime tunable resolution

Most fields below are also readable by the paired `proxbox-api` backend through
`proxbox_api.runtime_settings.get_int / get_float / get_bool / get_str`. The
backend resolves each tunable in the following order:

1. **`PROXBOX_*` environment variable** on the backend host (highest priority,
   set in `.env` or systemd unit).
2. **Plugin Settings field** here (cached for **5 minutes** in the backend).
3. **Built-in default** documented in each table below.

The 5-minute cache means edits on this page take effect on the next backend
read after the cache expires; restart `proxbox-api` to apply immediately. The
**Env override** column in each table below names the backend env var that
shadows the field.

---

## Core Behavior

| Field | Default | Env override | Description |
|---|---|---|---|
| **Use guest agent interface name** | `true` | _(plugin only)_ | Use QEMU guest-agent interface names (e.g. `ens18`) instead of generic Proxmox labels (e.g. `net0`). |
| **Proxmox fetch max concurrency** | `8` | `PROXBOX_FETCH_MAX_CONCURRENCY` | Maximum parallel Proxmox fetch operations per sync stage. Raise for multi-cluster speed; lower if Proxmox load is a concern. |
| **Ignore IPv6 link-local addresses** | `true` | _(plugin only)_ | Skip `fe80::/64` addresses during VM interface IP selection. |
| **Delete orphan VMs** | `false` | `PROXBOX_DELETE_ORPHANS` | Delete Proxbox-discovered VMs that were not touched by the current full-update run. Review `/full-update/stream?dry_run=true` before enabling in production. |
| **Primary IP preference** | `ipv4` | _(plugin only)_ | Whether the sync should prefer IPv4 or IPv6 when assigning primary IP on NetBox VMs. |

---

## NetBox API

These fields tune how aggressively Proxbox calls the NetBox REST API during sync operations. The defaults are conservative and safe for most deployments.

| Field | Default | Env override | Description |
|---|---|---|---|
| **NetBox client timeout (s)** | `120` | `PROXBOX_NETBOX_TIMEOUT` | Per-request timeout for NetBox API calls. |
| **NetBox max concurrent requests** | `1` | `PROXBOX_NETBOX_MAX_CONCURRENT` | Semaphore cap on simultaneous in-flight NetBox API calls. Increase carefully — PostgreSQL connection pool may exhaust at high values. |
| **NetBox write concurrency** | `8` | `PROXBOX_NETBOX_WRITE_CONCURRENCY` | Cap on parallel writes during create/update fan-out (lower than reads to avoid PostgreSQL row-lock contention). |
| **NetBox max retries** | `5` | `PROXBOX_NETBOX_MAX_RETRIES` | Retry attempts for transient NetBox API failures. |
| **NetBox retry delay (s)** | `2.00` | `PROXBOX_NETBOX_RETRY_DELAY` | Base delay in seconds for exponential back-off between retries. |
| **NetBox GET cache TTL (s)** | `60.00` | `PROXBOX_NETBOX_GET_CACHE_TTL` | How long NetBox GET responses are cached in memory. Set to `0` to disable caching. |
| **NetBox GET cache max entries** | `4096` | `PROXBOX_NETBOX_GET_CACHE_MAX_ENTRIES` | Maximum number of distinct GET responses retained in the in-memory cache. |
| **NetBox GET cache max bytes** | `52428800` | `PROXBOX_NETBOX_GET_CACHE_MAX_BYTES` | Maximum total cache size in bytes (default ≈ 50 MB). |
| **Debug cache logging** | `false` | `PROXBOX_DEBUG_CACHE` | Emit verbose hit/miss/eviction logs for the NetBox GET cache. Use sparingly — produces high log volume. |
| **Expose internal errors** | `false` | `PROXBOX_EXPOSE_INTERNAL_ERRORS` | When enabled, full Python tracebacks surface in HTTP responses. Keep `false` outside of dev environments. |

---

## Sync Pipeline

These fields control batching, concurrency, and pacing for the Proxmox-to-NetBox sync pipeline.

| Field | Default | Env override | Description |
|---|---|---|---|
| **VM sync max concurrency** | `4` | `PROXBOX_VM_SYNC_MAX_CONCURRENCY` | Maximum number of VMs synced in parallel during a full update. |
| **Bulk batch size** | `50` | `PROXBOX_BULK_BATCH_SIZE` | Number of records per batch during bulk create/update operations. |
| **Bulk batch delay (ms)** | `500` | `PROXBOX_BULK_BATCH_DELAY_MS` | Milliseconds to pause between bulk batches to avoid overwhelming NetBox. |
| **Backup batch size** | `5` | `PROXBOX_BACKUP_BATCH_SIZE` | Records per batch during backup/snapshot reconciliation (kept lower than bulk batches because each item triggers Proxmox calls). |
| **Backup batch delay (ms)** | `200` | `PROXBOX_BACKUP_BATCH_DELAY_MS` | Milliseconds to pause between backup batches. |
| **Custom fields request delay (s)** | `0.00` | `PROXBOX_CUSTOM_FIELDS_REQUEST_DELAY` | Optional sleep between custom-field API operations to throttle requests. |

---

## Proxmox API

Tunables that govern how proxbox-api talks to upstream Proxmox clusters.

| Field | Default | Env override | Description |
|---|---|---|---|
| **Proxmox API timeout (s)** | `60` | _(plugin only)_ | Per-request timeout for Proxmox API calls. |
| **Proxmox max retries** | `3` | _(plugin only)_ | Retry attempts for transient Proxmox API failures. |
| **Proxmox retry back-off (s)** | `1.00` | _(plugin only)_ | Base delay in seconds for exponential back-off between Proxmox retries. |
| **Proxmox fetch concurrency** | `8` | `PROXBOX_PROXMOX_FETCH_CONCURRENCY` | Cap on parallel Proxmox reads during sync stages that loop over many VMs (e.g. task-history). Distinct from the workspace-wide **Proxmox fetch max concurrency** in Core Behavior. |

---

## Logging

| Field | Default | Env override | Description |
|---|---|---|---|
| **Backend log file path** | `/var/log/proxbox.log` | _(plugin only)_ | Absolute path for proxbox-api rotated log archive output. Changes take effect after proxbox-api restart. |

---

## Sync Overwrite Flags

The Plugin Settings object also stores **global defaults** for every `overwrite_*` flag (device fields, VM fields, tags, primary IP, status, and custom fields). Per-endpoint overrides live on the **Settings** tab of each `ProxmoxEndpoint`.

Tri-state semantics on the per-endpoint tab:

| Setting | Effect |
|---|---|
| **Use plugin default** (None) | Inherit the value from the global Plugin Settings object. |
| **Always overwrite** (True) | The sync overwrites the existing NetBox value with the Proxmox value on every run. |
| **Never overwrite** (False) | The sync preserves the existing NetBox value and only writes when the field is empty. |

The `overwrite_vm_tags` toggle controls **merge vs replace** semantics: when enabled, Proxbox-managed tags replace the existing tag set; when disabled, Proxbox tags are merged with whatever tags are already present on the NetBox VM.

See [Sync Overwrite Flags](./sync-overwrite-flags.md) for the full flag matrix.

---

## SSRF Protection

These settings guard against Server-Side Request Forgery by validating endpoint IPs before Proxbox contacts them.

| Field | Default | Description |
|---|---|---|
| **Enable SSRF protection** | `true` | Validate that Proxmox/NetBox/FastAPI endpoint IPs are not reserved or internal. Disable only in fully trusted environments. |
| **Allow private IP addresses** | `true` | Allow endpoints on RFC-1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`). Recommended for on-premises deployments. |
| **Additional allowed IP CIDR ranges** | _(empty)_ | One CIDR per line. IPs in these ranges are always allowed regardless of other settings. |
| **Explicitly blocked IP CIDR ranges** | _(empty)_ | One CIDR per line. IPs in these ranges are always blocked even if they match an allowed range above. |

> **Note:** When `Allow private IP addresses` is disabled, Proxbox will reject endpoint addresses on private IP ranges. Enable it for any on-premises Proxmox or NetBox deployment.

---

## Encryption

These settings control credential encryption for the proxbox-api backend. When enabled, sensitive credentials stored in the proxbox-api SQLite database (NetBox API tokens, Proxmox passwords and token values) are encrypted at rest using Fernet (AES-128-CBC with HMAC-SHA256).

| Field | Default | Description |
|---|---|---|
| **Enable credential encryption** | `false` | Checkbox that controls whether the encryption key below is active. Unchecking clears the stored key. |
| **Encryption key** | _(empty)_ | Secret key used by proxbox-api to encrypt credentials. The raw value is hashed with SHA-256 before use. Leave blank to use the `PROXBOX_ENCRYPTION_KEY` environment variable on the proxbox-api host instead. |

### Key resolution order

proxbox-api resolves the encryption key using the following priority:

1. **`PROXBOX_ENCRYPTION_KEY` environment variable** — highest priority, set on the proxbox-api host.
2. **Encryption key field here** — fetched from the NetBox plugin API at startup and cached for 5 minutes.
3. **None** — credentials stored in plaintext; a `CRITICAL` warning is logged on every proxbox-api startup.

### Generating a key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output into the **Encryption key** field and check **Enable credential encryption**, then save.

### Important notes

- Changing the key after credentials are already encrypted requires re-saving each endpoint with its credentials so they are re-encrypted under the new key.
- The key is cached in proxbox-api for the session lifetime. Saving a new key in this page takes effect within 5 minutes (settings cache TTL) or after a proxbox-api restart.
- Credentials stored before encryption was enabled remain plaintext until the endpoint is next saved.
