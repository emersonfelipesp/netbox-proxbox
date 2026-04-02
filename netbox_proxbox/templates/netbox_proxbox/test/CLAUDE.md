# `templates/netbox_proxbox/test`

This directory contains development or diagnostic templates.

## Files And Ownership

- [`websocket.html`](./websocket.html): manual test page for the plugin WebSocket integration and FastAPI endpoint reachability.

## Dependencies

- Inbound: `TestWebSocketView` renders this template.
- Outbound: the configured `FastAPIEndpoint` and the WebSocket helper logic in `websocket_client.py`.

## Notes

- Treat this directory as diagnostic support rather than a core user-facing UI surface.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
