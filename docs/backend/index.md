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

| Plugin Path | Backend Path | Description |
|-------------|--------------|-------------|
| `sync/devices/stream/` | `GET /dcim/devices/create/stream` | Stream device sync progress |
| `sync/virtual-machines/stream/` | `GET /virtualization/virtual-machines/create/stream` | Stream VM sync progress |
| `sync/full-update/stream/` | `GET /full-update/stream` | Stream full update progress |
| `sync/devices/` | `POST /dcim/devices/create` | Device sync (single response) |
| `sync/virtual-machines/` | `POST /virtualization/virtual-machines/create` | VM sync (single response) |
| `sync/full-update/` | `POST /full-update` | Full update (single response) |

## How SSE Streaming Works

1. The user clicks a sync button in the NetBox UI.
2. The plugin fetches the stream endpoint (e.g., `sync/full-update/stream/`).
3. The plugin performs a streaming HTTP request to the backend's SSE endpoint.
4. As the backend processes each object, it emits SSE `step` events.
5. The plugin proxies these events back to the browser as a Django `StreamingHttpResponse`.
6. The browser JavaScript parses each SSE frame and updates the sync log and progress bar in real time.

## Architecture

![Proxbox Architecture Image](./proxbox-architecture.png)
