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
| **VM interface sync strategy** | `guest_os_model` | _(plugin only)_ | `guest_os_model` keeps Proxmox NICs as core `VMInterface` rows named `net0`/`net1` and writes guest-agent OS interfaces to plugin `GuestVMInterface` rows. `legacy_rename` preserves the older lossy behavior that renames the core VM interface to the guest-agent name. |
| **Use guest agent interface name** | `true` | _(plugin only)_ | **Deprecated.** Used only when **VM interface sync strategy** is `legacy_rename`; then it controls whether guest-agent names (e.g. `ens18`) replace generic Proxmox labels (e.g. `net0`). |
| **Proxmox fetch max concurrency** | `8` | `PROXBOX_FETCH_MAX_CONCURRENCY` | Maximum parallel Proxmox fetch operations per sync stage. Raise for multi-cluster speed; lower if Proxmox load is a concern. |
| **Ignore IPv6 link-local addresses** | `true` | _(plugin only)_ | Skip `fe80::/64` addresses during VM interface IP selection. |
| **Ensure NetBox supporting objects on startup** | `true` | _(plugin only)_ | When enabled, proxbox-api runs an idempotent NetBox-side bootstrap pass on each process start that ensures the supporting objects the plugin relies on (cluster type, device roles, manufacturer, device type, VM type, discovery tags — and the legacy reflection custom fields only when `custom_fields_enabled` is on) exist. Disable to leave hand-curated NetBox installs untouched. |
| **Delete orphan VMs** | `false` | `PROXBOX_DELETE_ORPHANS` | Delete Proxbox-discovered VMs that were not touched by the current full-update run. Review `/full-update/stream?dry_run=true` before enabling in production. |
| **Enable legacy custom fields (deprecated)** | `false` | _(plugin only)_ | Deprecated. When disabled (the default), Proxbox uses the typed `Proxbox*SyncState` models as the sole source of truth for the Proxmox-to-NetBox linkage and does **not** write, read, or reconcile the legacy reflection custom fields. Enable `custom_fields_enabled` only for a temporary transition; while enabled, proxbox-api still writes and reads the custom fields and emits deprecation warnings. The custom fields will be removed in a future release. |
| **Parse description metadata** | `false` | _(plugin only)_ | When enabled, proxbox-api reads each Proxmox object's description for a fenced `netbox-metadata` JSON block and applies the parsed primary-key ids to the matching NetBox fields. Per-field `overwrite_*` flags still gate keys they cover. |
| **Primary IP preference** | `ipv4` | _(plugin only)_ | Whether the sync should prefer IPv4 or IPv6 when assigning primary IP on NetBox VMs. |

### Default VM roles

`default_role_qemu` and `default_role_lxc` provide global fallback DeviceRoles used when a synced VM has no role assignment yet. They are FK choices restricted to `DeviceRole` rows with `vm_role=True`.

| Field | Default | Env override | Description |
|---|---|---|---|
| **Default QEMU VM role** | `virtual-machine-qemu` (seeded by migration) | _(plugin only)_ | DeviceRole assigned to QEMU VMs synced from Proxmox when no per-Endpoint or per-Node override applies. Operator edits on a specific VM are preserved by the `proxmox_last_synced_role_id` snapshot lock. |
| **Default LXC container role** | `container-lxc` (seeded by migration) | _(plugin only)_ | DeviceRole assigned to LXC containers synced from Proxmox when no per-Endpoint or per-Node override applies. Operator edits on a specific VM are preserved by the same snapshot lock. |

The lookup order applied during sync is **VM-level (operator pin) → per-Node → per-Endpoint → Plugin Settings default → built-in fallback**. `ProxboxVirtualMachineSyncState.proxmox_last_synced_role_id` stores the role that sync last wrote. Subsequent runs update the role only while its current value still matches that snapshot, so manual edits in NetBox are not clobbered. Migration `0078_sync_state_last_synced_role` copies valid values from the deprecated same-named VM custom field without deleting the legacy data.

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
| **Persist NetBox OpenAPI schema to disk** | `true` | `PROXBOX_NETBOX_OPENAPI_PERSIST` | When enabled (default), proxbox-api caches the resolved NetBox OpenAPI schema on disk. **Uncheck to run schema resolution fully in-memory** and never write to (or read from) the filesystem. |

### NetBox OpenAPI schema cache (in-memory mode)

proxbox-api resolves a NetBox OpenAPI contract at sync time to validate the
payloads it builds. By default the resolved document is cached on disk at
`proxbox_api/generated/netbox/openapi.json` so the backend does not have to
re-fetch it from NetBox on every run.

**Persist NetBox OpenAPI schema to disk** (`netbox_openapi_persist`, env
`PROXBOX_NETBOX_OPENAPI_PERSIST`, default `true`) turns that on-disk cache off.
When it is unchecked:

- The fetched schema is kept only in a process-local, in-memory store — the
  backend **never reads from or writes to the filesystem** for this cache.
- Resolution still avoids repeated live fetches within the same process; only
  cross-restart persistence is lost (the schema is re-fetched after a restart).
- Use this for **read-only filesystems** or deployments that must not write any
  generated artifacts to disk.

The toggle resolves in the standard order: the
`PROXBOX_NETBOX_OPENAPI_PERSIST` environment variable on the backend host wins,
then this plugin setting, then the built-in default (`true`). Behavior is
unchanged when the setting is left enabled.

---

## Sync Pipeline

These fields control batching, concurrency, and pacing for the Proxmox-to-NetBox sync pipeline.

| Field | Default | Env override | Description |
|---|---|---|---|
| **VM sync max concurrency** | `4` | `PROXBOX_VM_SYNC_MAX_CONCURRENCY` | Maximum number of VMs synced in parallel during a full update. |
| **VM reconciliation engine** | `python` | _(plugin only)_ | Engine used by proxbox-api to build VM operation queues: `python`, `compare`, or `rust`. Use `rust` for the PyO3-backed `proxbox-reconcile-rs` engine. |
| **Strict Rust comparison** | `false` | _(plugin only)_ | In `compare` mode, fail the sync on Rust/Python mismatch instead of only logging it. |
| **Bulk batch size** | `50` | `PROXBOX_BULK_BATCH_SIZE` | Number of records per batch during bulk create/update operations. |
| **Bulk batch delay (ms)** | `500` | `PROXBOX_BULK_BATCH_DELAY_MS` | Milliseconds to pause between bulk batches to avoid overwhelming NetBox. |
| **Backup batch size** | `5` | `PROXBOX_BACKUP_BATCH_SIZE` | Records per batch during backup/snapshot reconciliation (kept lower than bulk batches because each item triggers Proxmox calls). |
| **Backup batch delay (ms)** | `200` | `PROXBOX_BACKUP_BATCH_DELAY_MS` | Milliseconds to pause between backup batches. |
| **Interface batch size** | `5` | `PROXBOX_INTERFACE_BATCH_SIZE` | Number of VM interfaces (and their IP addresses, subnets, VLANs) synced per batch. Large VMs (50+ interfaces) may time out if synced all at once; batching prevents overwhelming NetBox with concurrent API calls. |
| **Interface batch delay (ms)** | `100` | `PROXBOX_INTERFACE_BATCH_DELAY_MS` | Milliseconds to wait between interface batches to throttle NetBox load. |
| **Custom fields request delay (s)** | `0.00` | `PROXBOX_CUSTOM_FIELDS_REQUEST_DELAY` | Optional sleep between custom-field API operations to throttle requests. |

---

## Proxmox API

Tunables that govern how proxbox-api talks to upstream Proxmox clusters.

| Field | Default | Env override | Description |
|---|---|---|---|
| **Proxmox API timeout (s)** | `5` | _(plugin only)_ | Per-request timeout for Proxmox API calls. |
| **Proxmox max retries** | `0` | _(plugin only)_ | Retry attempts for transient Proxmox API failures. |
| **Proxmox retry back-off (s)** | `0.50` | _(plugin only)_ | Base delay in seconds for exponential back-off between Proxmox retries. |
| **Proxmox fetch concurrency** | `8` | `PROXBOX_PROXMOX_FETCH_CONCURRENCY` | Cap on parallel Proxmox reads during sync stages that loop over many VMs (e.g. task-history). Distinct from the workspace-wide **Proxmox fetch max concurrency** in Core Behavior. |

Each Proxmox endpoint can override timeout, retries, and retry back-off. A blank
endpoint field inherits the corresponding value above; a concrete endpoint
value, including zero retries or zero back-off, wins. The plugin resolves this
inheritance before registering the endpoint with proxbox-api, so the backend
always receives concrete values rather than JSON `null`.

---

## Ceph control-plane timing

These bounded settings govern proxbox-api's durable Ceph write workflow. They
resolve for each request in the order **environment override → this plugin
setting → built-in default**. proxbox-api captures one immutable timing
snapshot before constructing the provider adapter, and each operation run
persists its lease duration so a later settings change cannot alter heartbeat
or recovery semantics for work already in flight.

| Field | Default | Range | Env override | Description |
|---|---:|---:|---|---|
| `ceph_task_timeout` | `300.00` | `1.00–3600.00` | `PROXBOX_CEPH_TASK_TIMEOUT` | Maximum total wait for a submitted Proxmox Ceph task to reach a terminal state. |
| `ceph_task_poll_interval` | `1.00` | `0.10–60.00` | `PROXBOX_CEPH_TASK_POLL_INTERVAL` | Delay between provider status checks while a Ceph task is active. The configured value must not exceed the task timeout. |
| `ceph_run_lease_seconds` | `360.00` | `1.00–3600.00` | `PROXBOX_CEPH_RUN_LEASE_SECONDS` | Renewable durable lease captured on the operation run. proxbox-api renews it independently from provider gates, calls, and polling. |

Malformed or non-finite environment values fall through to the validated plugin
value and then the built-in default. Finite out-of-range environment values are
clamped to the documented field range. proxbox-api also normalizes an
environment-derived polling interval to at most the resolved task timeout, so
environment overrides cannot bypass the cross-field safety rule. NetBox renders
these Django decimal fields as JSON numbers because
`COERCE_DECIMAL_TO_STRING=False`.

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

## Tenant Mapping

These fields drive the optional post-sync Tenant resolvers. Existing tenant assignments are never overwritten by either resolver.

| Field | Default | Env override | Description |
|---|---|---|---|
| **Enable tenant assignment by VM-name regex** | `false` | _(plugin only)_ | When enabled, sync resolves a NetBox Tenant for each VM by matching its name against the rules below. |
| **Tenant name regex rules** | `[]` | _(plugin only)_ | Ordered list of `{pattern, tenant_slug, [label]}` dicts. First match wins; specificity-first ordering is recommended (e.g. `^cust-acme-` before `^cust-`). Patterns are compiled and tenant slugs are verified at save time. |
| **Enable tenant assignment by tags** | `false` | _(plugin only)_ | When enabled, sync assigns a Tenant to VMs carrying both `cloud-customer` and exactly one `tenant-<slug>` tag. Missing tenants are created under the `cloud-customers` TenantGroup. |

See [Tenant Mapping operations](../operations/tenant-mapping.md) for runbook-level guidance, pattern examples, and tag-convention details.

---

## Cloud-customer network

These fields designate the NetBox IPAM objects that proxbox-api and nms-backend
use to discover the customer-facing cloud network. Prefix, VLAN, and gateway
values are operator-provided; they are not hardcoded as plugin defaults or seeded
by data migration.

| Field | Default | Env override | Description |
|---|---|---|---|
| **Enable cloud customer network lock** (`cloud_network_lock_enabled`) | `false` | _(plugin only)_ | Marks the configured cloud customer network as authoritative for cloud provisioning integrations. |
| **Cloud customer Prefix ID** (`cloud_customer_prefix_id`) | `null` | _(plugin only)_ | Primary key of the NetBox IPAM Prefix designated as the cloud customer network. |
| **Cloud customer bridge** (`cloud_customer_bridge`) | `vmbr1` | _(plugin only)_ | Proxmox bridge name used for customer-facing cloud interfaces. |
| **Cloud customer VLAN tag** (`cloud_customer_vlan_tag`) | `null` | _(plugin only)_ | VLAN tag associated with the designated cloud customer network. |
| **Cloud customer gateway** (`cloud_customer_gateway`) | _(empty)_ | _(plugin only)_ | Gateway IP address for the designated cloud customer network. |

Run the idempotent management command from the NetBox environment to create or
reuse the IPAM Role, VLAN, Prefix, and reserved gateway IP, then write the
singleton settings row:

```bash
python manage.py ensure_cloud_customer_network \
  --prefix 168.0.98.0/25 \
  --vlan 2050 \
  --vlan-name cloud-vmbr1 \
  --bridge vmbr1 \
  --gateway 168.0.98.1 \
  --enable-lock
```

The command only creates missing target objects and updates
`ProxboxPluginSettings`. It does not delete objects or mutate unrelated IPAM
records, so it can be run repeatedly during rollout automation.

---

## Branching

These fields configure the optional **branching-enabled sync** mode where every Proxbox job runs against a fresh `netbox-branching` branch and merges on success. Requires the `netbox_branching` plugin installed and listed **last** in `PLUGINS`.

| Field | Default | Env override | Description |
|---|---|---|---|
| **Branching-enabled sync (Proxmox → NetBox)** | `false` | _(plugin only)_ | Master toggle. When enabled, every Proxbox sync job creates a branch, runs the sync on it, and merges it back into `main` on success. |
| **Branch name prefix** | `proxbox-sync` | _(plugin only)_ | Prefix used when auto-creating a NetBox branch per sync job. Final name pattern is `<prefix>-<job_id>-<timestamp>`. |
| **Branch merge conflict policy** | `fail` | _(plugin only)_ | `fail` leaves the branch open for operator review and marks the job failed. `acknowledge` attempts the merge anyway and delegates conflict handling to the netbox-branching merge strategy. |

---

## NetBox → Proxmox intent direction

These fields gate the optional write-back direction in which merging a branch flagged `apply_to_proxmox=True` dispatches CREATE / UPDATE writes to Proxmox via `proxbox-api`. See the [Safety Model](https://github.com/emersonfelipesp/netbox-proxbox/blob/develop/CLAUDE.md#safety-model) for the full five-lock invariant chain.

| Field | Default | Env override | Description |
|---|---|---|---|
| **Enable NetBox → Proxmox intent direction** | `false` | _(plugin only)_ | Master flag. Off by default. DELETE still requires the separate `DeletionRequest` authorization chain even when this is on. |
| **Typed confirmation phrase** | _(empty)_ | _(plugin only)_ | Operators enabling the master flag must type the exact phrase `allow-edit-and-add-actions` here. Toggling the master flag back to `false` clears this phrase, forcing re-confirmation on re-enable. |
| **Allow apply-destroy authorization workflow** | `false` | _(plugin only)_ | Per-branch destroy master switch. Even when set, every destroy flows through a separate `DeletionRequest` approved by a user holding `netbox_proxbox.authorize_deletion_request`. |

---

## Hardware Discovery

| Field | Default | Env override | Description |
|---|---|---|---|
| **Enable SSH-based hardware discovery** | `false` | _(plugin only)_ | Master flag for the SSH-driven hardware-discovery pass. When enabled, proxbox-api opens a pinned-fingerprint SSH session to each `ProxmoxNode` that has a stored `NodeSSHCredential` row, runs `dmidecode + ethtool + ip link` under `sudo -n`, and reflects the parsed chassis / NIC values onto the matching `dcim.Device` and `dcim.Interface` custom fields. Flipping off results in zero SSH sockets opened during sync. |
| **Sync physical NIC MAC addresses** | `false` | _(plugin only)_ | Separate opt-in for native `dcim.MACAddress` creation and `primary_mac_address` assignment on physical node interfaces. Requires hardware discovery to be enabled. Keeping it off preserves pre-feature behavior even when SSH discovery is already enabled. |

See [Hardware Discovery](./hardware-discovery.md) for the full configuration, custom-field surface, and SSH-credential model.

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

These settings control only the Fernet encryption of plugin-owned values stored
in the **NetBox database**. They do not configure proxbox-api's SQLite
encryption and they are not the FastAPI endpoint key used to authenticate HTTP
requests.

| Field | Default | Description |
|---|---|---|
| **Enable credential encryption** | `false` | Enables plugin-at-rest encryption. Once ciphertext exists, this control is locked until all ciphertext is removed through the recovery workflow. |
| **Encryption key** | _(empty)_ | A canonical Fernet key or raw 32-byte secret for plugin-owned ciphertext in NetBox. Ordinary API serializers keep it write-only. The backend runtime route retains a permission-gated compatibility fallback for current proxbox-api releases. |

### Three separate security domains

| Domain | Purpose | Configuration |
|---|---|---|
| **Plugin-at-rest Fernet key** | Protects encrypted model fields in the NetBox PostgreSQL database | This settings page and its verified rotation workflow |
| **proxbox-api-at-rest encryption** | Protects credentials in proxbox-api's own SQLite database | Prefer `PROXBOX_ENCRYPTION_KEY` or proxbox-api's separately administered local key. Current releases can still read the plugin key from the permission-gated runtime route for upgrade compatibility; migrate before that fallback is removed. |
| **FastAPI endpoint API key** | Authenticates NetBox/plugin HTTP requests to proxbox-api | The `FastAPIEndpoint` credential and backend-key adoption workflow; this is credential material protected by the plugin-at-rest key, not an encryption key itself |

Never copy one domain's key into another merely because all three are described
as “keys.” Rotate and recover them independently.

### Generating a key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output into the **Encryption key** field and check **Enable credential encryption**, then save.

### Protected field inventory

The settings page reports secret-free row counts and a
**Configured / Recovery required / Not configured** state for every registered
family:

- Proxmox API credentials and endpoint SSH credentials;
- proxbox-api authentication keys stored on `FastAPIEndpoint`;
- PBS and PDM API token secrets;
- the optional netbox-pbs standalone proxbox-api fallback key when that
  companion plugin is installed;
- per-node SSH credentials;
- cloud-init SSH public-key intent bundles; and
- Firecracker host-agent tokens.

The registry is also the source of truth for rotation and selective reset, so
new encrypted model fields must be added there before release. Optional
companion families are omitted only when their Django app and database table are
both genuinely absent. If an unloaded companion leaves its table behind, the
plugin locks and inspects that known table; any surviving ciphertext blocks key
mutation until the companion is re-enabled and migrated. An installed companion
with an unresolved model or database table also blocks key mutation and recovery
until its installation is repaired.

### Verified rotation

Ordinary form saves, model saves, and API PATCH requests cannot clear or
replace the plugin key while any registered ciphertext exists. Use **Verified
plugin key rotation** instead:

1. Enter the current key and the replacement key twice.
2. The plugin locks the settings plus every registered ciphertext table in a
   deterministic PostgreSQL lock order, then verifies **every** non-empty
   registered ciphertext with the current key. Registered model saves,
   including the optional netbox-pbs settings model, lock the settings row and
   validate their ciphertext and expected pre-write database snapshot under
   that key before the SQL write. A writer
   which prepared old-key ciphertext before rotation is rejected after waiting;
   it cannot commit stale ciphertext under the replacement key. Direct
   `QuerySet.update()`/bulk writes to encrypted fields are forbidden outside the
   recovery service's locked updates.
   Before changing the key, every configured proxbox-api target must also return
   a successful authenticated, versioned `GET /admin/encryption/status`
   attestation. Version 1 must atomically report the active cached key source as
   independent (`env` or `local`) and confirm that the active key decrypts every
   encrypted backend credential. Legacy source-only responses, a failed
   credential scan, an unreachable backend, or an invalid response block
   rotation. Configure `PROXBOX_ENCRYPTION_KEY`, migrate/re-encrypt the backend
   database, and deploy the paired attestation contract before rotating the
   plugin key. Current source-only proxbox-api responses deliberately remain
   blocked.
3. Only after all values verify does it re-encrypt all values and store the new
   key in one transaction.
4. A wrong current key or one corrupt row aborts the transaction without
   changing any ciphertext or setting.
5. The POST body is marked sensitive for Django exception reporting, and the
   transaction writes a secret-free NetBox changelog record containing only
   actor, request, operation, family names, outcome, and aggregate counts.

### Lost-key destructive reset

If the old key is unavailable, a user with the separate
`netbox_proxbox.reset_encrypted_secrets` permission may use **Destructive
encrypted-secret reset**. Select only the affected families, acknowledge data
loss, and type `RESET PROXBOX ENCRYPTED SECRETS` exactly. The operation clears
the selected ciphertext and its associated trust fingerprints with non-signaling
database updates. The same update disables affected Proxmox, proxbox-api, PBS,
and PDM endpoints and marks affected Firecracker hosts offline; per-node SSH,
cloud-init, and optional netbox-pbs fallback rows become explicitly
unconfigured by their empty credential. Re-enter credentials and explicitly
re-enable or restore the affected service before running sync.
The reset takes the settings-row lock before table locks, and the writer guard
rejects any stale instance whose expected ciphertext no longer matches the
cleared row, so a queued full save cannot resurrect credentials or `enabled`.

This path is destructive: it cannot recover plaintext and does not change
unselected families.

### Important notes

- A `Recovery required` state means ciphertext exists but cannot be decrypted
  with the configured plugin key. Forms, lists, dashboards, SSH credential
  endpoints, and save signals fail closed without rendering the stored value.
- Rotation preserves trust fingerprints because the plaintext credential does
  not change. Destructive reset clears the corresponding fingerprints because
  the credential can no longer be vouched for.
- An enabled FastAPI endpoint with undecryptable stored ciphertext accepts only
  an explicit replacement key, authenticates it against that exact target, and
  persists it through the normal adoption boundary. A save without an explicit
  replacement remains blocked.
