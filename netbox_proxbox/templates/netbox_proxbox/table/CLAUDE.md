# `templates/netbox_proxbox/table`

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
