# `templates/netbox_proxbox/fastapi`

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

This directory currently contains FastAPI-specific plugin page fragments.

## Files And Ownership

- [`home.html`](./home.html): FastAPI-oriented home/dashboard content that is included from the main plugin home page.

## Dependencies

- Inbound: included or rendered from higher-level dashboard pages.
- Outbound: FastAPI endpoint context assembled in `HomeView` and related card/status components.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
