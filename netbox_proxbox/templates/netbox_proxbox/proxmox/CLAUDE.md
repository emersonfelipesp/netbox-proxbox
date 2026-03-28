# `templates/netbox_proxbox/proxmox`

This directory contains Proxmox-specific template fragments.

## Files And Ownership

- [`cluster.html`](./cluster.html): Proxmox cluster-specific markup used when rendering cluster details.

## Dependencies

- Inbound: Proxmox endpoint or dashboard templates include this fragment.
- Outbound: card/status data fetched from the FastAPI backend.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
