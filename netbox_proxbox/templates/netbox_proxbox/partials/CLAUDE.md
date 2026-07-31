# `templates/netbox_proxbox/partials`

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

This directory contains small reusable HTML fragments.

## Files And Ownership

- [`websocket_messages.html`](./websocket_messages.html): renders message batches returned by the WebSocket polling endpoint and the job log stream helpers.
- [`home_sync_actions_dropdown.html`](./home_sync_actions_dropdown.html): dropdown menu fragment for individual sync action buttons on the home page.

## Dependencies

- Inbound: WebSocket/polling templates include this fragment.
- Outbound: `WebSocketView` in `websocket_client.py` and the corresponding browser-side polling code.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
