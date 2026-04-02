# `templates/netbox_proxbox/partials`

This directory contains small reusable HTML fragments.

## Files And Ownership

- [`websocket_messages.html`](./websocket_messages.html): renders message batches returned by the WebSocket polling endpoint and the job log stream helpers.

## Dependencies

- Inbound: WebSocket/polling templates include this fragment.
- Outbound: `WebSocketView` in `websocket_client.py` and the corresponding browser-side polling code.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
