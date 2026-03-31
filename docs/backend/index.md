# Backend Overview

Proxbox uses a separate FastAPI service as its backend. The NetBox plugin does not talk to Proxmox directly.

## How It Works

The backend:

- connects to Proxmox
- connects back to NetBox
- exposes HTTP endpoints used by the plugin
- supports SSE streaming (`text/event-stream`) for real-time per-object sync progress
- can optionally provide WebSocket updates for sync progress

The NetBox plugin stores and manages endpoint records, then triggers sync requests against the backend. Sync can run in two modes:

- **POST polling**: traditional request/response that waits for completion.
- **GET SSE stream**: the plugin proxies the backend's streaming response to the browser, rendering granular progress (e.g., `Processing device pve01`, `Synced virtual_machine vm101`) in real time.

## Sync Endpoints

Current plugin sync endpoints enqueue NetBox background jobs (`ProxboxSyncJob`). The
job worker then consumes the backend SSE stream (`.../stream`) to completion.

| Plugin Path | Backend Path Used By Job | Description |
|-------------|--------------------------|-------------|
| `sync/devices/` | `GET /dcim/devices/create/stream` | Queue device sync |
| `sync/storage/` | `GET /virtualization/virtual-machines/storage/create/stream` | Queue storage sync |
| `sync/virtual-machines/` | `GET /virtualization/virtual-machines/create/stream` | Queue VM sync |
| `sync/virtual-machines/virtual-disks/` | `GET /virtualization/virtual-machines/virtual-disks/create/stream` | Queue virtual disk sync |
| `sync/virtual-machines/backups/` | `GET /virtualization/virtual-machines/backups/all/create/stream` | Queue VM backup sync |
| `sync/virtual-machines/snapshots/` | `GET /virtualization/virtual-machines/snapshots/all/create/stream` | Queue VM snapshot sync |
| `sync/full-update/` | `GET /full-update/stream` | Queue full multi-stage update |

## How Sync Streaming Works In Current Code

1. The user clicks a sync button in the NetBox UI.
2. The plugin enqueues a `ProxboxSyncJob` in NetBox's `default` RQ queue.
3. A NetBox RQ worker executes that job and opens the backend SSE endpoint.
4. As the backend emits SSE events, the job logs progress and stores structured result payloads on the Job row.
5. The user follows status/log/output from the NetBox background job pages.

## Architecture

![Proxbox Architecture Image](./proxbox-architecture.png)
