# `templates/netbox_proxbox/proxmox`

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

This directory contains Proxmox-specific template fragments.

## Files And Ownership

- [`cluster.html`](./cluster.html): Proxmox cluster-specific markup used when rendering cluster details and cluster summary tabs.

## Dependencies

- Inbound: Proxmox endpoint or dashboard templates include this fragment.
- Outbound: card/status data fetched from the FastAPI backend.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
