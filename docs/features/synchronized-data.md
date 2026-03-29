# Synchronized Data

Proxbox synchronizes data between Proxmox clusters and NetBox using a dual-mode sync architecture. The NetBox plugin triggers sync requests against the ProxBox FastAPI backend, which performs the actual object creation and updates.

## Sync Modes

### POST Polling (Traditional)

When you click a sync button, the plugin sends a POST request to the backend and waits for a single JSON response containing the final result. This is the simplest mode and works well for quick syncs.

### GET SSE Streaming (Real-Time Progress)

For longer sync operations, the plugin uses Server-Sent Events (SSE) to stream progress updates in real time. When you click a sync button, the browser fetches a streaming endpoint, and the plugin proxies the backend's `text/event-stream` response back to the page. Progress updates appear immediately in the sync log without waiting for the entire operation to finish.

The plugin prefers SSE streaming when available. Each sync button carries both a POST URL (`data-sync-url`) and a stream URL (`data-sync-stream-url`). The browser JavaScript uses the stream URL when present.

## Stream Endpoints

| Plugin Path | Backend Path | Description |
|-------------|--------------|-------------|
| `sync/devices/stream/` | `GET /dcim/devices/create/stream` | Stream device synchronization progress |
| `sync/virtual-machines/stream/` | `GET /virtualization/virtual-machines/create/stream` | Stream VM synchronization progress |
| `sync/full-update/stream/` | `GET /full-update/stream` | Stream full update (devices + VMs) progress |

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

## SSE Event Format

All stream endpoints return `Content-Type: text/event-stream` and emit three event types:

- **step**: Progress frame with `step` (object kind), `status` (`started`, `progress`, `completed`), `message` (human-readable text), and `rowid` (object name/ID).
- **error**: Error frame when an object fails to sync. Contains `step`, `error`, and `detail`.
- **complete**: Final frame with `ok` (boolean) and `message`. Marks the end of the stream.

## Failure Handling

- If the backend returns an error during streaming, the plugin emits an SSE `error` frame with the failure details and continues with a `complete` frame.
- If the stream proxy itself encounters an error (e.g., backend unreachable), it emits a fallback SSE error frame instead of returning a Django 500 page.
- The browser JavaScript displays error details from both `error` frames and non-200 HTTP responses.

## WebSocket Mode (Legacy)

The backend also provides a WebSocket endpoint (`/ws`) for interactive sync. This predates the SSE streaming approach and sends the same per-object progress JSON over a bidirectional WebSocket channel. SSE streaming is now preferred for browser-based sync because it works with standard HTTP requests.