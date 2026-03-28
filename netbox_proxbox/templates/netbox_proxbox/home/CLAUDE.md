# `templates/netbox_proxbox/home`

This directory contains dashboard card fragments and log display partials for the plugin home page.

## Files And Ownership

- [`proxmox_card.html`](./proxmox_card.html): Proxmox endpoint summary card.
- [`netbox_card.html`](./netbox_card.html): remote NetBox endpoint summary card.
- [`fastapi_card.html`](./fastapi_card.html): ProxBox backend summary card.
- [`log_messages.html`](./log_messages.html): streamed or polled message display block.

## Dependencies

- Inbound: `HomeView` and related page templates include these fragments.
- Outbound: JS polling/card-refresh code and view functions like `get_proxmox_card()` and `get_service_status()`.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
