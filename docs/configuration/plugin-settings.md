# Plugin Settings

Proxbox exposes a singleton **Plugin Settings** object for runtime behavior toggles. Create or edit it under **Plugins → Proxbox → Plugin Settings**.

---

## Core Behavior

| Field | Default | Description |
|---|---|---|
| **Use guest agent interface name** | `true` | Use QEMU guest-agent interface names (e.g. `ens18`) instead of generic Proxmox labels (e.g. `net0`). |
| **Proxmox fetch max concurrency** | `8` | Maximum parallel Proxmox fetch operations per sync stage. Raise for multi-cluster speed; lower if Proxmox load is a concern. |
| **Ignore IPv6 link-local addresses** | `true` | Skip `fe80::/64` addresses during VM interface IP selection. |

---

## NetBox Integration

These fields tune how aggressively Proxbox calls the NetBox API during sync operations. The defaults are conservative and safe for most deployments.

| Field | Default | Description |
|---|---|---|
| **NetBox max concurrent requests** | `1` | Semaphore cap on simultaneous in-flight NetBox API calls. Increase carefully — PostgreSQL connection pool may exhaust at high values. |
| **NetBox max retries** | `5` | Retry attempts for transient NetBox API failures. |
| **NetBox retry delay (s)** | `2.00` | Base delay in seconds for exponential back-off between retries. |
| **NetBox GET cache TTL (s)** | `60.00` | How long NetBox GET responses are cached in memory. Set to `0` to disable caching. |
| **Bulk batch size** | `50` | Number of records per batch during bulk create/update operations. |
| **Bulk batch delay (ms)** | `500` | Milliseconds to pause between bulk batches to avoid overwhelming NetBox. |
| **VM sync max concurrency** | `4` | Maximum number of VMs synced in parallel during a full update. |
| **Custom fields request delay (s)** | `0.00` | Optional sleep between custom-field API operations to throttle requests. |
| **Backend log file path** | `/var/log/proxbox.log` | Absolute path for proxbox-api rotated log archive output. Changes take effect after proxbox-api restart. |

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
