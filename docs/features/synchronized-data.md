# Synchronized Data

Proxbox synchronizes data between Proxmox clusters and NetBox via NetBox background jobs.
The NetBox plugin triggers `ProxboxSyncJob` runs, and each job consumes streaming backend
SSE endpoints from ProxBox FastAPI to perform object creation and updates.

## Sync Mode

The current plugin path is job-based and stream-backed:

- UI/API sync actions enqueue a NetBox background job.
- The job reads backend SSE (`text/event-stream`) until completion.
- Progress and terminal state are recorded on the NetBox Job row.

## Typed Sync-State Models

Proxbox is phasing out the historical NetBox custom fields that proxbox-api
created on core NetBox objects. The first phase is additive: the plugin creates
typed sidecar models under `/api/plugins/proxbox/sync-state/...` and backfills
them from the existing `custom_field_data`, while proxbox-api continues to write
the legacy custom fields.

The sidecars are keyed one-to-one to the affected core objects:

| Core object | Sidecar model | API path |
|-------------|---------------|----------|
| `virtualization.VirtualMachine` | `ProxboxVirtualMachineSyncState` | `/api/plugins/proxbox/sync-state/virtual-machines/` |
| `dcim.Device` | `ProxboxDeviceSyncState` | `/api/plugins/proxbox/sync-state/devices/` |
| `virtualization.Cluster` | `ProxboxClusterSyncState` | `/api/plugins/proxbox/sync-state/clusters/` |
| `ipam.IPAddress` | `ProxboxIPAddressSyncState` | `/api/plugins/proxbox/sync-state/ip-addresses/` |
| `dcim.Interface` | `ProxboxInterfaceSyncState` | `/api/plugins/proxbox/sync-state/interfaces/` |
| `ipam.VLAN` | `ProxboxVLANSyncState` | `/api/plugins/proxbox/sync-state/vlans/` |
| `virtualization.ClusterGroup` | `ProxboxClusterGroupSyncState` | `/api/plugins/proxbox/sync-state/cluster-groups/` |
| `virtualization.VirtualDisk` | `ProxboxVirtualDiskSyncState` | `/api/plugins/proxbox/sync-state/virtual-disks/` |
| `virtualization.VMInterface` | `ProxboxVMInterfaceSyncState` | `/api/plugins/proxbox/sync-state/vm-interfaces/` |
| `dcim.DeviceRole` | `ProxboxDeviceRoleSyncState` | `/api/plugins/proxbox/sync-state/device-roles/` |
| `dcim.DeviceType` | `ProxboxDeviceTypeSyncState` | `/api/plugins/proxbox/sync-state/device-types/` |
| `dcim.Manufacturer` | `ProxboxManufacturerSyncState` | `/api/plugins/proxbox/sync-state/manufacturers/` |
| `dcim.Site` | `ProxboxSiteSyncState` | `/api/plugins/proxbox/sync-state/sites/` |
| `virtualization.ClusterType` | `ProxboxClusterTypeSyncState` | `/api/plugins/proxbox/sync-state/cluster-types/` |

All sidecars inherit the shared `ProxboxSyncStateBase` fields:
`proxmox_last_updated` (the old source timestamp custom field) and
`last_run_id` (the old `proxbox_last_run_id`). The inherited NetBox
`last_updated` field remains the row modification timestamp used by API ETags.
VM and device sidecars replace the old shadow values for endpoint, node, and
cluster with nullable FKs to `ProxmoxEndpoint`, `ProxmoxNode`, and
`ProxmoxCluster`. If an old text value cannot be resolved, the FK remains null
and the fallback text/raw ID is retained. Legacy backend IDs are stored as raw
data: `proxmox_endpoint_id` becomes `proxmox_endpoint_raw_id`, and
`proxmox_cluster_id` becomes `proxmox_cluster_raw_id`.

`ProxboxClusterSyncState` is a separate sidecar instead of new columns on
`ProxmoxCluster` because `ProxmoxCluster` is endpoint-scoped and only has a
nullable FK to the core NetBox cluster. A single NetBox cluster is not guaranteed
to be the same row as a Proxmox cluster tracking record.

The typed `Proxbox*SyncState` models are now the **standard** source of truth
for the Proxmox-to-NetBox linkage. The legacy reflection custom fields are
**deprecated** and, by default, no longer used: the `custom_fields_enabled`
plugin setting defaults to `false`, so a normal sync writes and reads the
sidecar models only and does not write, read, or reconcile the custom fields.
The sidecars are (re)built from live Proxmox data on each sync, so a plain
re-sync recovers them even when a NetBox upgrade has already dropped the custom
fields.

Operators who need the old behavior during a transition can set
`custom_fields_enabled = true`; while enabled, proxbox-api restores the legacy
custom-field writes/reads/reconcile and emits deprecation warnings. The custom
fields (and this flag) will be removed entirely in a future release; the flag is
non-destructive and no custom-field data is deleted while it exists.

### Concurrency / Known Limitation

On NetBox 4.5.x, these sidecar REST APIs do not emit ETags and do not enforce
`If-Match`. That is a NetBox platform limitation present for all API endpoints
on 4.5.x, not a limitation specific to the Proxbox sidecar models. Optimistic
concurrency for these APIs is available on NetBox 4.6+.

Automated writers should treat the sidecar rows as proxbox-api-owned during the
additive migration phase. Custom fields remain the parallel source of truth until
the paired backend writer/reader switch is released.

## Sync Endpoints

| Plugin Path | Backend Path Used By Job | Description |
|-------------|--------------------------|-------------|
| `sync/devices/` | `GET /dcim/devices/create/stream` | Queue device synchronization |
| `sync/storage/` | `GET /virtualization/virtual-machines/storage/create/stream` | Queue storage synchronization |
| `sync/virtual-machines/` | `GET /virtualization/virtual-machines/create/stream` | Queue VM synchronization |
| `sync/virtual-machines/virtual-disks/` | `GET /virtualization/virtual-machines/virtual-disks/create/stream` | Queue virtual disk synchronization |
| `sync/virtual-machines/backups/` | `GET /virtualization/virtual-machines/backups/all/create/stream` | Queue backup synchronization |
| `sync/virtual-machines/snapshots/` | `GET /virtualization/virtual-machines/snapshots/all/create/stream` | Queue snapshot synchronization |
| `sync/full-update/` | `GET /full-update/stream` | Queue full update (devices, storage, VMs, disks, backups, snapshots, replications, backup routines) |

## Progress Messages

SSE streaming provides granular per-object progress messages. For example, during a full update you might see:

```
full-update: Starting devices synchronization.
full-update: Processing device pve01
full-update: Synced device pve01
full-update: Processing device pve02
full-update: Synced device pve02
full-update: Devices synchronization finished.
full-update: Starting virtual machines synchronization.
full-update: Processing virtual_machine vm101
full-update: Synced virtual_machine vm101
full-update: Virtual machines synchronization finished.
full-update: Full update sync completed.
full-update: stream completed
```

## SSE Event Format (Backend Stream)

Backend stream endpoints return `Content-Type: text/event-stream` and emit three event types:

- **step**: Progress frame with `step` (object kind), `status` (`started`, `progress`, `completed`), `message` (human-readable text), and `rowid` (object name/ID).
- **error**: Error frame when an object fails to sync. Contains `step`, `error`, and `detail`.
- **complete**: Final frame with `ok` (boolean) and `message`. Marks the end of the stream.

## Failure Handling

- If the backend returns an error while the job is consuming the stream, the job is marked failed/errored with backend detail.
- If the stream read fails (e.g., backend unreachable), the job records the connection/read failure and exits with a non-success status.
- Use NetBox Job logs and `error` fields for diagnosis.

## WebSocket Mode (Legacy)

The backend also provides a WebSocket endpoint (`/ws`) for interactive sync. This predates the SSE streaming approach and sends the same per-object progress JSON over a bidirectional WebSocket channel. SSE streaming is now preferred for browser-based sync because it works with standard HTTP requests.
