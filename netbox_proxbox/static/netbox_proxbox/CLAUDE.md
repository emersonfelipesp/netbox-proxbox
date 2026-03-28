# `netbox_proxbox.static.netbox_proxbox`

This directory holds the actual static assets referenced by plugin templates.

## Contents

- Image and branding assets such as Proxmox, FastAPI, GitHub, Telegram, Discord, and NetBox logos/banners.
- [`js/`](./js/): browser-side interaction code for plugin pages.
- [`styles/`](./styles/): SCSS sources and compiled CSS/JS theme assets.

## Dependencies

- Inbound: templates under `templates/netbox_proxbox/` load these assets with Django's static tag.
- Outbound: none at the Python level; the JS layer talks to plugin views over HTTP and WebSocket.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children:
  - [`js/CLAUDE.md`](./js/CLAUDE.md)
  - [`styles/CLAUDE.md`](./styles/CLAUDE.md)
