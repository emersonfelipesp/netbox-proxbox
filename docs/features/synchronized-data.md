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

Proxbox has retired the historical reflection custom fields that proxbox-api
created on core NetBox objects. The plugin exposes typed sidecar models under
`/api/plugins/proxbox/sync-state/...`; migrations 0065 and 0066 created and
backfilled them before the backend writer/reader cutover.

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

The typed `Proxbox*SyncState` models are the **standard** source of truth for
the Proxmox-to-NetBox linkage. A normal sync writes and reads the sidecars and
rebuilds them from live Proxmox data. Migration 0085 removes the twelve
VM-only reflection custom-field definitions, strips their stale keys from each
core VM's JSON, and removes the obsolete `custom_fields_enabled` setting.
`ProxboxVirtualMachineSyncState` is therefore the sole read path for VM
reflection identity and status. Migration 0086 removes the remaining thirty
reflection definitions and strips their stale keys from every affected core
object type. Migration 0087 finishes that removal: 0086 compares each field's label against its own definition table, and proxbox-api's inventory reconcile had rewritten the six hardware-discovery labels, so 0086 failed closed and skipped them. 0087 selects candidates by data type plus `ui_editable="hidden"` -- the two attributes both writers agree on -- and then gates the destructive step on the question that does not require guessing provenance NetBox never recorded: **a field holding a value on any row is left alone in full**, definition, bindings and values, whoever wrote it. Only `None` and the empty string count as blank, the check is repeated once the definitions are locked and again as each key is stripped, and the reverse applies it too, so neither a late writer nor a rollback can expose somebody's data as a Proxbox field. Each object's NetBox detail page shows its typed sidecar when one
exists. It shows no empty card for an object that has never been synchronized.

The `proxmox_node` and `proxmox_storage` custom fields are deliberately not
removed. They are dual-role operator inputs used to select the target node and
storage during NetBox-to-Proxmox CREATE intent. The other intent fields, branch
flags, `source_packer_template`, and netbox-proxy custom fields also remain.

### Concurrency / Known Limitation

On NetBox 4.5.x, these sidecar REST APIs do not emit ETags and do not enforce
`If-Match`. That is a NetBox platform limitation present for all API endpoints
on 4.5.x, not a limitation specific to the Proxbox sidecar models. Optimistic
concurrency for these APIs is available on NetBox 4.6+.

Automated writers must treat the sidecar rows as proxbox-api-owned. Reflection
custom fields are no longer a parallel source of truth.

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
