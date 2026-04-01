# `templates/netbox_proxbox/table`

This directory contains table-oriented content templates used by plugin pages.

## Files And Ownership

- [`devices.html`](./devices.html): tabular device/node display.
- [`interfaces.html`](./interfaces.html): tabular interface display.
- [`ip_addresses.html`](./ip_addresses.html): tabular IP address display.
- [`lxc_containers.html`](./lxc_containers.html): tabular LXC container display.
- [`virtual_machines.html`](./virtual_machines.html): tabular VM display.

## Dependencies

- Inbound: list or dashboard pages that present synced objects include these templates.
- Outbound: JS table helpers and any JSON data loaded by the associated views.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
