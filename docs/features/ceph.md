# Ceph (Proxmox-managed)

`netbox-ceph` is a sibling NetBox plugin shipped from the same repository as
`netbox-proxbox`. Version `0.0.1` (paired with `netbox-proxbox 0.0.17`) is
**strictly read-only**: it reflects Proxmox-managed Ceph state into NetBox
through `proxbox-api` and inherits the same endpoint inventory, FastAPI
backend context, and branch lifecycle helpers that the Proxbox plugin
already provides.

## Scope locks for v1

- Direction: **Proxmox-managed Ceph → NetBox only**. No NetBox → Ceph writes.
- Safety: no pool creation, OSD `in/out`, service start/stop, flag mutation,
  CephFS destroy, or any other Ceph write operation lives in this plugin or
  the matching `proxbox-api[ceph]` surface.
- Dependency: `netbox-ceph` declares `required_plugins = ["netbox_proxbox"]`
  and reuses `ProxmoxEndpoint`, `FastAPIEndpoint`, and the
  `services.branch_lifecycle` helpers without re-implementing them.
- Branching: `CephSyncJob` threads `netbox_branch_schema_id` through every
  `/ceph/sync/*` call so the netbox-branching plugin can review reflected
  inventory before it lands on `main`.
- Integration: the plugin **calls `proxbox-api`** over HTTP; the Proxmox VE
  Ceph endpoints are read through `proxmox-sdk.ceph` on the backend side.

## What it reflects

| Object | Source path | NetBox model |
|---|---|---|
| Cluster health and status | `GET /cluster/ceph/status` | `CephCluster` (+ `CephHealthCheck`) |
| MON / MGR / MDS daemons | `GET /cluster/ceph/{mon,mgr,mds}` | `CephDaemon` |
| OSDs | `GET /cluster/ceph/osd` (+ per-node detail) | `CephOSD` |
| Pools | `GET /cluster/ceph/pools` | `CephPool` |
| CephFS filesystems | `GET /cluster/ceph/fs` | `CephFilesystem` |
| CRUSH rules and tree | `GET /cluster/ceph/rules` | `CephCrushRule` |
| Flags | `GET /cluster/ceph/flags` | `CephFlag` |

The full payload returned by `proxbox-api` is preserved under each model's
`payload` JSON field so the UI can render extended details without losing
upstream fidelity.

## Sync stages

`CephSyncJob` calls the proxbox-api `/ceph/sync/*` routes one resource at a
time and persists progress under `job.data["ceph_sync"]`:

```json
{
  "params": {"resources": ["status", "osds", "pools"]},
  "runtime_seconds": 12.4,
  "response": {
    "stages": [
      {"resource": "status", "status": "ok", "runtime_seconds": 0.3, "response": {…}},
      {"resource": "osds",   "status": "ok", "runtime_seconds": 4.1, "response": {…}},
      {"resource": "pools",  "status": "ok", "runtime_seconds": 0.6, "response": {…}}
    ]
  }
}
```

Default invocation syncs the aggregate `full` resource. Valid resources:
`status`, `daemons`, `osds`, `pools`, `filesystems`, `crush`, `flags`,
`full`. The job uses NetBox's `default` RQ queue with a `7200s`
`job_timeout`, matching the long-running Proxbox sync pattern.

## Branch-aware flow

When `CephPluginSettings.branching_enabled` is `True` **and** the
`netbox_branching` plugin is installed, `CephSyncJob`:

1. Calls `create_and_provision_branch(prefix=…, on_conflict=…)` from the
   shared `netbox_proxbox.services.branch_lifecycle` module.
2. Threads the resulting `netbox_branch_schema_id` through every
   `/ceph/sync/<resource>?netbox_branch_schema_id=…` request.
3. Calls `merge_branch(branch)` on success.
4. On error, leaves the branch open for inspection and raises so the Job
   row records the failure.

Settings defaults are `prefix="ceph-sync"` and `on_conflict="fail"`. When
branching is unavailable or disabled, the job runs against `main`.

## Out of scope for v1

- Direct Ceph Dashboard API integration.
- Prometheus metric ingestion.
- RGW / S3 bucket inventory.
- RBD image inventory.
- External non-Proxmox Ceph clusters.
- Any NetBox → Ceph write operation.

These are tracked separately on the parent issue and intentionally deferred
until the read-only reflection has been validated in production.

## Related

- Parent issue: [`#424`](https://github.com/emersonfelipesp/netbox-proxbox/issues/424).
- Plugin scaffold issue: [`#428`](https://github.com/emersonfelipesp/netbox-proxbox/issues/428).
- Branch-aware sync job issue: [`#430`](https://github.com/emersonfelipesp/netbox-proxbox/issues/430).
- Release / docs / smoke issue: [`#429`](https://github.com/emersonfelipesp/netbox-proxbox/issues/429).
- Backend Ceph routes: `proxbox_api/ceph/routes.py`.
- SDK Ceph facade: `proxmox_sdk/ceph/`.
