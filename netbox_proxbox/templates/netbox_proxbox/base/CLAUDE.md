# `templates/netbox_proxbox/base`

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

This directory contains shared layout templates for the plugin.

## Files And Ownership

- [`base.html`](./base.html): plugin base template wrapper.
- [`layout.html`](./layout.html): shared page layout scaffold for the dashboard, detail, and action pages.
- [`sidenav.html`](./sidenav.html): plugin side navigation markup.
- [`40x.html`](./40x.html): error-page template.

## Dependencies

- Inbound: many plugin templates extend or include these base templates.
- Outbound: NetBox's own base layout and plugin static styling.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
