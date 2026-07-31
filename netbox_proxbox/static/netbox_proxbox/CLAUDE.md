# `netbox_proxbox.static.netbox_proxbox`

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

This directory holds the actual static assets referenced by plugin templates.

## Contents

- Image and branding assets such as Proxmox, FastAPI, GitHub, LinkedIn, and NetBox logos/banners.
- [`css/`](./css/): compiled page-specific CSS used by plugin templates.
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
