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
