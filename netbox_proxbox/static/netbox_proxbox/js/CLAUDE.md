# `netbox_proxbox.static.netbox_proxbox.js`

This directory contains the plugin's browser-side JavaScript.

## Files And Ownership

- [`common.js`](./common.js): shared helpers used across plugin pages (badge state, tooltip setup, CSRF token retrieval).
- [`device.js`](./device.js): client behavior for device/node sync views.
- [`home.js`](./home.js): home dashboard interactions and card/status updates. Key functions:
  - `wireSyncForms()`: attaches submit handlers to sync forms. Uses `data-sync-stream-url` (when present) to prefer SSE streaming over POST polling.
  - `streamSyncEvents(syncKind, syncStreamUrl)`: fetches the SSE stream endpoint, parses frames in real time, and updates UI progress/logs incrementally. Handles non-200 responses by reading `await response.text()` for detailed error messages.
  - `parseSSEFrame(rawFrame)`: splits an SSE frame into `event` and parsed JSON `data`.
  - `formatStreamMessage(syncKind, data, event)`: builds user-facing messages from granular SSE payloads. Extracts `data.payload.data.rowid`, `data.payload.object`, and `data.error` to render messages like `Processing device pve01` or `Synced virtual_machine vm101`.
  - `refreshStatusBadges()`, `hydrateProxmoxCards()`: refresh dashboard status cards after sync completion.
  - `startSyncProgress(syncKind)`, `stopSyncProgress(status, detail)`: manage the progress bar state and label text.
- [`polling.js`](./polling.js): repeated polling helpers for status or sync progress.
- [`table.js`](./table.js): table-specific dynamic behavior.
- [`virtual_machine.js`](./virtual_machine.js): client behavior for VM sync views.
- [`websocket.js`](./websocket.js): browser integration for backend WebSocket message streaming. Provides `onSyncEnd(listener)` and `notifySyncEnd(syncObject)` hooks.

## Dependencies

- Inbound: page templates include these scripts.
- Outbound: plugin routes in `urls.py`, especially sync, keepalive, card, and `websocket/<message>` endpoints.

## Notes

- Treat these files as coupled to both template markup and the JSON shapes returned by the sync/status views.
- Any change to polling cadence, response shape, or DOM hooks usually requires touching both JS and template files.
- SSE stream events use `event: step`, `event: error`, and `event: complete` with JSON `data:` payloads. The `step` events carry nested `payload` objects mirroring the websocket JSON shape (`payload.object`, `payload.type`, `payload.data`).

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
