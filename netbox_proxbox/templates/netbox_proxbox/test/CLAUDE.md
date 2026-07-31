# `templates/netbox_proxbox/test`

> **Repository destination guardrail:** This guide inherits the hard rule in
> the repository-root `CLAUDE.md`. EdgeUno and the local EdgeUno vendor
> submodule are read-only reference sources, never change destinations. All
> development writes must target exactly
> `https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox.git`; approved
> public promotion may target only
> `https://github.com/emersonfelipesp/netbox-proxbox.git`. Never mutate EdgeUno
> issues, PRs, branches, commits, tags, releases, packages, mirrors, or
> deployments, and never configure EdgeUno as a writable remote, upstream,
> fallback, or PR base.

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
