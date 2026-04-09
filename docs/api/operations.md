# Operations API

These two models store Proxmox operational data synced into NetBox: scheduled backup routines and replication jobs.

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
