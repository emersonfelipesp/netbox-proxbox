# Synchronized Data

Proxbox synchronizes data between Proxmox clusters and NetBox via NetBox background jobs.
The NetBox plugin triggers `ProxboxSyncJob` runs, and each job consumes streaming backend
SSE endpoints from ProxBox FastAPI to perform object creation and updates.

## Sync Mode

The current plugin path is job-based and stream-backed:

- UI/API sync actions enqueue a NetBox background job.
- The job reads backend SSE (`text/event-stream`) until completion.
- Progress and terminal state are recorded on the NetBox Job row.

## Sync Endpoints

| Plugin Path | Backend Path Used By Job | Description |
|-------------|--------------------------|-------------|
| `sync/devices/` | `GET /dcim/devices/create/stream` | Queue device synchronization |
| `sync/storage/` | `GET /virtualization/virtual-machines/storage/create/stream` | Queue storage synchronization |
| `sync/virtual-machines/` | `GET /virtualization/virtual-machines/create/stream` | Queue VM synchronization |
| `sync/virtual-machines/virtual-disks/` | `GET /virtualization/virtual-machines/virtual-disks/create/stream` | Queue virtual disk synchronization |
| `sync/virtual-machines/backups/` | `GET /virtualization/virtual-machines/backups/all/create/stream` | Queue backup synchronization |
| `sync/virtual-machines/snapshots/` | `GET /virtualization/virtual-machines/snapshots/all/create/stream` | Queue snapshot synchronization |
| `sync/full-update/` | `GET /full-update/stream` | Queue full update (devices, storage, VMs, disks, backups, snapshots) |

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
