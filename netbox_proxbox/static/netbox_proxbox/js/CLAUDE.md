# `netbox_proxbox.static.netbox_proxbox.js`

This directory contains the plugin's browser-side JavaScript.

## Files And Ownership

- [`common.js`](./common.js): shared helpers used across plugin pages.
- [`device.js`](./device.js): client behavior for device/node sync views.
- [`home.js`](./home.js): home dashboard interactions and card/status updates.
- [`polling.js`](./polling.js): repeated polling helpers for status or sync progress.
- [`table.js`](./table.js): table-specific dynamic behavior.
- [`virtual_machine.js`](./virtual_machine.js): client behavior for VM sync views.
- [`websocket.js`](./websocket.js): browser integration for backend WebSocket message streaming.

## Dependencies

- Inbound: page templates include these scripts.
- Outbound: plugin routes in `urls.py`, especially sync, keepalive, card, and `websocket/<message>` endpoints.

## Notes

- Treat these files as coupled to both template markup and the JSON shapes returned by the sync/status views.
- Any change to polling cadence, response shape, or DOM hooks usually requires touching both JS and template files.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
