# Large multi-cluster deployments

This guide helps operators tune Proxbox when a single NetBox install reflects
many Proxmox clusters (on the order of thirty or more). It focuses on settings
that proxbox-api reads from the singleton **Plugin Settings** object (with
optional `PROXBOX_*` environment overrides on the backend host) and on backend
rate limiting that is **not** controlled from the NetBox UI.

For field-by-field defaults and env var names, see
[Plugin Settings](./plugin-settings.md). Resolution order everywhere proxbox-api
honors a tunable is: **environment variable → Plugin Settings (5-minute cache)
→ built-in default**.

---

## How sync uses concurrency

The plugin's staged sync calls proxbox-api for **one Proxmox endpoint at a
time** in most stages, so the per-endpoint parallelism knobs (Proxmox fetch
concurrency, VM sync concurrency, NetBox write concurrency, batch sizes) govern
load **per cluster** there. A few backend operations fan out across every
Proxmox session they are given in one request — for example backup-routine and
replication collection, and the cluster-wide firewall and datacenter reads — so
their upstream load does grow with the number of endpoints in scope. You
generally do **not** need to raise concurrency settings simply because the
estate grew; watch NetBox and Proxmox health, job duration, and backend rate
limits, and prefer smaller endpoint subsets per job for very large estates.

If a full sync over every enabled endpoint exceeds the NetBox job timeout, split
work into several jobs that each target a subset of endpoints (scheduled or
manual), rather than chasing unbounded parallelism.

---

## Backend rate limiting (`PROXBOX_RATE_LIMIT`)

proxbox-api applies a **global** HTTP rate limiter **before** authentication.
The limit is keyed by **client IP address**. All NetBox → proxbox-api traffic
during sync, UI polling, and operational actions typically originates from **one**
NetBox application address, so the default budget is shared across the entire
estate.

| Setting | Default | Where to set |
|---|---|---|
| `PROXBOX_RATE_LIMIT` | `300` requests per minute per client IP | proxbox-api host environment (not Plugin Settings) |

For large multi-cluster estates, raise this value so legitimate sync traffic is
not throttled. A practical starting point for roughly thirty clusters is
**`PROXBOX_RATE_LIMIT=3000`**. Restart proxbox-api after changing it.

Adding proxbox-api **uvicorn workers** is not a substitute for raising the rate
limit. The rate limiter and the advisory active-sync registry are kept per
worker process, so each worker has its own rate-limit budget and its own view of
running syncs, and every worker multiplies the NetBox connection budget
(`netbox_max_concurrent` × workers). If you do run several workers, size the
NetBox database pool for that product; otherwise a single worker with a higher
`PROXBOX_RATE_LIMIT` is the simpler configuration.

Keep **one active FastAPI backend API key** registered for the NetBox install.
proxbox-api verifies every authenticated request against each active key with
bcrypt, so every stale key adds verification work to every request.

### Recognizing throttling

When the limiter rejects traffic, proxbox-api returns **HTTP 429** with a body
containing **`Rate limit exceeded`**. Check proxbox-api logs for those lines
during sync.

On the Proxbox home page, endpoint badges may briefly show **Error** and then
recover after about a minute when polling retries succeed. Avoid reloading the
home page repeatedly while a sync is starting; each reload adds more API calls
competing with the job.

---

## Plugin settings reference (tuning-focused)

Built-in defaults below come from `ProxboxPluginSettings` in the plugin source.
Per-endpoint Proxmox timeout, retry, and back-off fields on each
`ProxmoxEndpoint` override the global Proxmox defaults when set (including
zero); blank endpoint fields inherit the plugin default.

### Proxmox API (global defaults; overridable per endpoint)

| Field | Default | proxbox-api env (if any) | Role |
|---|---|---|---|
| `proxmox_timeout` | `5` s | — | Per-request Proxmox API timeout |
| `proxmox_max_retries` | `0` | — | Retries for transient Proxmox failures (GET/HEAD) |
| `proxmox_retry_backoff` | `0.50` s | — | Exponential back-off base between Proxmox retries |

### NetBox API

| Field | Default | proxbox-api env | Role |
|---|---|---|---|
| `netbox_timeout` | `120` s | `PROXBOX_NETBOX_TIMEOUT` | Per-request NetBox API timeout |
| `netbox_max_retries` | `5` | `PROXBOX_NETBOX_MAX_RETRIES` | Retries for transient NetBox failures |
| `netbox_retry_delay` | `2.00` s | `PROXBOX_NETBOX_RETRY_DELAY` | Base delay for exponential back-off |
| `netbox_max_concurrent` | `1` | `PROXBOX_NETBOX_MAX_CONCURRENT` | Cap on simultaneous in-flight NetBox requests (bounded by PostgreSQL pool) |
| `netbox_write_concurrency` | `8` | `PROXBOX_NETBOX_WRITE_CONCURRENCY` | Parallel NetBox writes during VM/snapshot/task fan-out |

Raise `netbox_max_concurrent` only when NetBox’s database connection pool and
PostgreSQL `max_connections` leave headroom; exhausting the pool fails sync with
connection errors rather than graceful throttling.

### Proxmox read parallelism and VM sync

| Field | Default | proxbox-api env | Role |
|---|---|---|---|
| `proxbox_fetch_max_concurrency` | `8` | `PROXBOX_FETCH_MAX_CONCURRENCY` | Parallel Proxmox fetches per sync stage (discovery-style reads) |
| `proxmox_fetch_concurrency` | `8` | `PROXBOX_PROXMOX_FETCH_CONCURRENCY` | Parallel Proxmox reads in backup/snapshot/task-history paths. The Plugin Settings default is **8**; if proxbox-api cannot load Plugin Settings, individual backend paths use their own built-in fallbacks, which may be lower. |
| `vm_sync_max_concurrency` | `4` | `PROXBOX_VM_SYNC_MAX_CONCURRENCY` | VMs processed in parallel during full update |

### Batching (NetBox load pacing)

| Field | Default | proxbox-api env | Role |
|---|---|---|---|
| `bulk_batch_size` | `50` | `PROXBOX_BULK_BATCH_SIZE` | Records per bulk create/update batch |
| `bulk_batch_delay_ms` | `500` | `PROXBOX_BULK_BATCH_DELAY_MS` | Pause between bulk batches |
| `backup_batch_size` | `5` | `PROXBOX_BACKUP_BATCH_SIZE` | VM backup records per batch |
| `backup_batch_delay_ms` | `200` | `PROXBOX_BACKUP_BATCH_DELAY_MS` | Pause between backup batches |
| `interface_batch_size` | `5` | `PROXBOX_INTERFACE_BATCH_SIZE` | VM interfaces (and related IP/VLAN work) per batch |
| `interface_batch_delay_ms` | `100` | `PROXBOX_INTERFACE_BATCH_DELAY_MS` | Pause between interface batches |

**Interface batching on older backends:** proxbox-api releases before the one
that carries this guide ignore the two `interface_batch_*` Plugin Settings and
read only the `PROXBOX_INTERFACE_BATCH_SIZE` and
`PROXBOX_INTERFACE_BATCH_DELAY_MS` environment variables. The guest-agent call
timeout is not a Plugin Setting; set `PROXBOX_GUEST_AGENT_TIMEOUT` (seconds,
default `15`) on the backend if guest-agent calls time out.

---

## Recommended starting profile (~30 clusters)

Apply on top of defaults; adjust after observing job duration and error rates.

| Area | Recommendation |
|---|---|
| Backend env | `PROXBOX_RATE_LIMIT=3000` on proxbox-api |
| `proxmox_timeout` | `15` s globally; **20–30** s on remote or high-latency endpoints |
| `proxmox_max_retries` | `2` |
| `proxmox_retry_backoff` | `1.0` s |
| `netbox_timeout` | `180` s |
| `netbox_max_concurrent` | `1`–`2` unless the NetBox DB pool clearly allows more |
| Concurrency & batch fields | Leave at defaults unless profiling shows a specific bottleneck |

Operational habits:

- Avoid hammering the Proxbox home page while a sync is starting.
- Split very large estates into multiple sync jobs over endpoint subsets so each
  run stays within the configured job timeout.
- Prefer raising `PROXBOX_RATE_LIMIT` and modest timeout/retry adjustments over
  increasing many concurrency knobs at once.

---

## Related documentation

- [Plugin Settings](./plugin-settings.md) — complete field list
- [Background Jobs](../features/background-jobs.md) — job timeouts and workers
- [Scheduled Sync](../features/scheduled-sync.md) — recurring jobs per scope
