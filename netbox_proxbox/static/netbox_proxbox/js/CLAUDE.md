# `netbox_proxbox.static.netbox_proxbox.js`

This directory contains the plugin's browser-side JavaScript.

## Files And Ownership

- [`common.js`](./common.js): shared helpers used across plugin pages (badge state, tooltip setup, CSRF token retrieval).
- [`device.js`](./device.js): client behavior for device/node sync views.
- [`endpoint-status.js`](./endpoint-status.js): periodic refresh for keepalive/status badges across dashboard and list pages.
- [`home.js`](./home.js): home dashboard interactions and card/status updates. It initializes
  websocket support (when enabled), refreshes keepalive status badges, and hydrates Proxmox
  cards with cluster metadata and inline warning/error messages.
- [`job_log_view.js`](./job_log_view.js): browser rendering helpers for the streamed Proxbox job log payloads shown on Job detail pages.
- [`polling.js`](./polling.js): repeated polling helpers for status or sync progress.
- [`sync.js`](./sync.js): shared DOM/SSE helpers used by sync pages and backend stream consumers.
- [`table.js`](./table.js): table-specific dynamic behavior.
- [`virtual_machine.js`](./virtual_machine.js): client behavior for VM sync views.
- [`websocket.js`](./websocket.js): browser integration for backend WebSocket message streaming. Provides `onSyncEnd(listener)` and `notifySyncEnd(syncObject)` hooks.

## Dependencies

- Inbound: page templates include these scripts.
- Outbound: plugin routes in `urls.py`, especially sync, keepalive, card, and `websocket/<message>` endpoints.

## Notes

- Treat these files as coupled to both template markup and the JSON shapes returned by the sync/status views.
- Any change to polling cadence, response shape, or DOM hooks usually requires touching both JS and template files.
- Job-triggering sync actions are submitted by native forms in templates (`data-sync-url`); progress/logs are followed on NetBox background job pages, while `home.js` focuses on dashboard hydration and badge refreshes.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
