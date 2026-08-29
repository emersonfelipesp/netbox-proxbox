# Operations API

This page covers four models that store Proxmox operational state in NetBox — scheduled backup routines, replication jobs, deletion requests, and apply jobs — plus the read-only **sync-jobs** listing, which is not a model at all but a filtered view of core's own job table.

**BackupRoutine** and **Replication** are standard read/write models.

**DeletionRequest** and **ProxmoxApplyJob** are **read-only** endpoints (GET / HEAD / OPTIONS only). Attempting a POST, PUT, PATCH, or DELETE returns HTTP 405. See [API Overview — Deletion Requests and Apply Jobs](index.md#deletion-requests-and-apply-jobs-read-only) for the safety rationale.

For common API conventions (authentication, pagination, nested serializers), see [API Overview](index.md).

---

## Backup Routine

A Proxmox backup job (vzdump schedule) synced from the cluster, including its schedule, retention policy, storage targets, and raw configuration.

```
GET    /api/plugins/proxbox/backup-routines/
GET    /api/plugins/proxbox/backup-routines/{id}/
POST   /api/plugins/proxbox/backup-routines/
PUT    /api/plugins/proxbox/backup-routines/{id}/
PATCH  /api/plugins/proxbox/backup-routines/{id}/
DELETE /api/plugins/proxbox/backup-routines/{id}/
```

**Example — list all enabled backup routines:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/backup-routines/?enabled=true"
```

**Example — filter by storage backend:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/backup-routines/?storage_id=2"
```

**Example — filter by node and active status:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/backup-routines/?node_id=1&status=active"
```

**Filterable fields:** `id`, `endpoint`, `job_id`, `enabled`, `node`, `storage`, `status`, `keep_last`, `keep_daily`, `keep_weekly`, `keep_monthly`

**Searchable fields (`?q=`):** `job_id`, `comment`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/backup-routines/1/",
  "display": "job-1 (daily)",
  "endpoint": {
    "id": 1,
    "url": "/api/plugins/proxbox/endpoints/proxmox/1/",
    "display": "prod-proxmox (proxmox.example.com)",
    "name": "prod-proxmox"
  },
  "job_id": "job-1",
  "enabled": true,
  "schedule": "0 2 * * *",
  "next_run": "2026-04-02T02:00:00Z",
  "node": {
    "id": 1,
    "url": "/api/plugins/proxbox/nodes/1/",
    "display": "pve-node-01",
    "name": "pve-node-01",
    "node_id": 1,
    "online": true
  },
  "storage": {
    "id": 2,
    "url": "/api/plugins/proxbox/storage/2/",
    "display": "backup-storage",
    "cluster": {"id": 5, "name": "prod-cluster"},
    "name": "backup-storage"
  },
  "selection": [100, 101, 102],
  "comment": "nightly VM backups",
  "status": {"value": "active", "label": "Active"},
  "keep_last": null,
  "keep_daily": 7,
  "keep_weekly": 4,
  "keep_monthly": 3,
  "keep_yearly": null,
  "keep_all": null,
  "notes_template": "",
  "bwlimit": null,
  "zstd": null,
  "io_workers": null,
  "fleecing": false,
  "fleecing_storage": null,
  "repeat_missed": false,
  "pbs_change_detection_mode": "",
  "raw_config": {"compress": "zstd", "mode": "snapshot"},
  "tags": [],
  "custom_fields": {},
  "created": "2026-01-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

### Data Model

| Field | Type | Description |
|---|---|---|
| `endpoint` | nested ProxmoxEndpoint | Proxmox endpoint this routine belongs to |
| `job_id` | string | Proxmox backup job ID |
| `enabled` | boolean | Whether the backup job is enabled |
| `schedule` | string | Cron-style schedule string (or Proxmox schedule syntax) |
| `next_run` | datetime (nullable) | Next scheduled execution time |
| `node` | nested ProxmoxNode (nullable) | Node that executes the backup |
| `storage` | nested ProxmoxStorage (nullable) | Target storage for backup files |
| `selection` | array | JSON list of VMID integers included in this job |
| `comment` | string | Free-text job description |
| `status` | choice | Sync status. Choices: `active`, `stale` |
| `keep_last` | integer (nullable) | Number of most recent backups to retain |
| `keep_daily` | integer (nullable) | Number of daily backups to retain |
| `keep_weekly` | integer (nullable) | Number of weekly backups to retain |
| `keep_monthly` | integer (nullable) | Number of monthly backups to retain |
| `keep_yearly` | integer (nullable) | Number of yearly backups to retain |
| `keep_all` | boolean (nullable) | Keep all backups regardless of other retention settings |
| `notes_template` | string | Template string for backup notes |
| `bwlimit` | integer (nullable) | Bandwidth limit in KiB/s |
| `zstd` | integer (nullable) | Zstd compression level |
| `io_workers` | integer (nullable) | Number of parallel I/O workers |
| `fleecing` | string | Fleecing options string from Proxmox (empty = disabled) |
| `fleecing_storage` | nested ProxmoxStorage (nullable) | Temporary fleecing storage target |
| `repeat_missed` | boolean | Whether to run missed scheduled jobs on next opportunity |
| `pbs_change_detection_mode` | string | PBS change detection mode (`default`, `legacy`, or `data`) |
| `raw_config` | object | Full raw backup job configuration from Proxmox |

---

## Replication

A Proxmox replication job synced from the cluster, describing scheduled VM replication from one node to another.

```
GET    /api/plugins/proxbox/replications/
GET    /api/plugins/proxbox/replications/{id}/
POST   /api/plugins/proxbox/replications/
PUT    /api/plugins/proxbox/replications/{id}/
PATCH  /api/plugins/proxbox/replications/{id}/
DELETE /api/plugins/proxbox/replications/{id}/
```

**Example — list all replication jobs:**

```bash
curl -H "Authorization: Token <token>" \
     http://netbox.example.com/api/plugins/proxbox/replications/
```

**Example — filter active replications for a specific VM:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/replications/?virtual_machine_id=10&status=active"
```

**Example — filter by target node:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/replications/?target=pve-node-02"
```

**Filterable fields:** `id`, `endpoint`, `replication_id`, `virtual_machine`, `proxmox_node`, `guest`, `target`, `job_type`, `schedule`, `disable`, `source`, `jobnum`, `remove_job`, `status`

**Searchable fields (`?q=`):** `replication_id`, virtual machine name, `target`, `comment`, `source`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/replications/1/",
  "display": "100-0 (web-server-01 → pve-node-02)",
  "endpoint": {
    "id": 1,
    "url": "/api/plugins/proxbox/endpoints/proxmox/1/",
    "display": "prod-proxmox (proxmox.example.com)",
    "name": "prod-proxmox"
  },
  "replication_id": "100-0",
  "virtual_machine": {
    "id": 10,
    "url": "/api/virtualization/virtual-machines/10/",
    "display": "web-server-01",
    "name": "web-server-01"
  },
  "proxmox_node": {
    "id": 1,
    "url": "/api/plugins/proxbox/nodes/1/",
    "display": "pve-node-01",
    "name": "pve-node-01",
    "node_id": 1,
    "online": true
  },
  "guest": 100,
  "target": "pve-node-02",
  "job_type": {"value": "local", "label": "Local"},
  "schedule": "*/15",
  "rate": null,
  "comment": "HA replication",
  "disable": false,
  "source": "pve-node-01",
  "jobnum": 0,
  "remove_job": null,
  "status": {"value": "active", "label": "Active"},
  "raw_config": {"type": "local"},
  "tags": [],
  "custom_fields": {},
  "created": "2026-01-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

### Data Model

| Field | Type | Description |
|---|---|---|
| `endpoint` | nested ProxmoxEndpoint (nullable) | Proxmox endpoint this replication belongs to |
| `replication_id` | string | Proxmox replication job ID (e.g. `100-0`) |
| `virtual_machine` | nested VirtualMachine | Replicated virtual machine |
| `proxmox_node` | nested ProxmoxNode (nullable) | Source node where the VM currently runs |
| `guest` | integer | Proxmox VM ID (VMID) of the guest |
| `target` | string | Target node name for replication |
| `job_type` | choice | Replication job type. Choices: `local` |
| `schedule` | string | Cron-style schedule string |
| `rate` | float (nullable) | Maximum replication bandwidth in MiB/s |
| `comment` | string | Free-text job description |
| `disable` | boolean | Whether the replication job is disabled |
| `source` | string | Source node name |
| `jobnum` | integer | Proxmox job number (sub-ID within the VM) |
| `remove_job` | choice (nullable) | Whether Proxmox should remove the job. Choices: `local`, `full` |
| `status` | choice | Sync status. Choices: `active`, `stale` |
| `raw_config` | object | Full raw replication configuration from Proxmox |

---

## Deletion Request (Read-Only)

`DeletionRequest` records are created through the NetBox UI or the intent API — not through the plugin REST API. The REST endpoint is read-only so automated tools can inspect the deletion queue without being able to modify it.

```
GET    /api/plugins/proxbox/deletion-requests/
GET    /api/plugins/proxbox/deletion-requests/{id}/
```

!!! warning "Write methods are blocked"
    POST, PUT, PATCH, and DELETE return **HTTP 405 Method Not Allowed** on these paths. The five-lock safety chain that gates VM destruction cannot be bypassed through the API.

For the complete four-eyes deletion workflow and the five-lock chain description, see the [Deletion Requests operations guide](../operations/deletion-requests.md).

**Example — list pending deletion requests:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/deletion-requests/?status=pending"
```

---

## ProxmoxApplyJob (Read-Only)

`ProxmoxApplyJob` is an audit log for intent-branch apply cycles (plan → apply operations driven by proxbox-api). Records are written exclusively by the backend; the plugin REST surface is read-only to preserve audit integrity.

```
GET    /api/plugins/proxbox/apply-jobs/
GET    /api/plugins/proxbox/apply-jobs/{id}/
```

!!! warning "Write methods are blocked"
    POST, PUT, PATCH, and DELETE return **HTTP 405 Method Not Allowed** on these paths.

**Example — retrieve a specific apply job:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/apply-jobs/42/"
```

**Example — list recent apply jobs for an endpoint:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/apply-jobs/?endpoint_id=1&limit=10"
```

---

## Sync Jobs (Read-Only)

The plugin has no job model of its own. A Proxbox sync is a **core NetBox
`core.Job` row** whose `data` carries a `proxbox_sync` block, and
`/api/core/jobs/` cannot filter on `data` — which is the only reliable way to
recognise one, because a run scheduled with a custom `job_name` keeps that name
verbatim and no name filter can find it.

This endpoint is core's job list already narrowed to the plugin's own rows, with
the filters that live inside `data` pushed into SQL.

```
GET    /api/plugins/proxbox/sync-jobs/
GET    /api/plugins/proxbox/sync-jobs/{id}/
```

!!! warning "Write methods are blocked"
    POST, PUT, PATCH, and DELETE return **HTTP 405 Method Not Allowed**.
    Scheduling stays on `sync/schedule/` and cancelling on `jobs/{id}/cancel/`,
    each with its own permission gate.

Rows are serialised with core's own `JobSerializer`, so a sync job looks exactly
like the same row on `/api/core/jobs/` and needs no second parser. Object
permissions apply as usual: a caller sees the jobs `core.view_job` allows.

### Filters

Every filter from core's job API keeps working — `status` (multi-value), `name`
and its lookups, `queue_name`, `user`, `object_type`, `object_id`, `id`,
`interval`, `q`, `ordering`, and `created` / `scheduled` / `started` /
`completed` with `__before` / `__after`. On top of those:

| Filter | Matches |
|---|---|
| `sync_type` | Runs that included the stage. Repeatable. |
| `proxmox_endpoint_id` | Runs that covered the endpoint. Repeatable. |
| `cluster_id` | Runs covering the cluster, resolved through its endpoint. |
| `node_id` | Runs covering the node, resolved through its endpoint. |
| `netbox_vm_id` | Runs that targeted the virtual machine. |
| `run_id` | Proxbox run identifier recorded in the parameters. |
| `batch_object_type` | Batch object type recorded in the parameters. |
| `errored` | Runs that failed **or** finished while recording an error. |

Three of these carry semantics worth stating outright, because they decide
whether full syncs show up in scoped queries. They are deliberately the same
rules `nbx proxbox jobs` applies, so one question cannot get two different
answers depending on who asks:

- **An empty endpoint list means "every endpoint".** That is what the schedule
  API stores when the caller names none, and such a run really did sync them
  all — so it matches any `proxmox_endpoint_id`, `cluster_id`, or `node_id`.
  The same holds when the key is absent or JSON `null`.
- **A run recorded as `sync_types: ["all"]` covers every `sync_type`**, and so
  does a run with no types recorded, whose documented default is `all`. The
  legacy singular `sync_type` key is honoured for rows written before
  `sync_types` existed.
- **An empty VM list is not a wildcard.** A run that targeted no particular
  virtual machine is not an answer to "which runs touched VM 199?".

`errored` is broader than a failure status on purpose: a sync can finish
`completed` while recording a stage error, and that is exactly the row an
operator triaging a failure is looking for.

### Log entries

`log_entries` is **omitted from list responses**. It is unbounded — a single
full-sync row can reach 130 KB, and a page of them is most of the payload.
Ask for it explicitly with `?include_log_entries=true`; the detail route always
returns it.

**Example — failed syncs for one cluster in the last week:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/sync-jobs/?cluster_id=3&errored=true&created__after=2026-08-22"
```

**Example — every storage sync that touched one endpoint:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/sync-jobs/?proxmox_endpoint_id=5&sync_type=storage"
```

**Example — one job in full, with its log:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/sync-jobs/24422/"
```
