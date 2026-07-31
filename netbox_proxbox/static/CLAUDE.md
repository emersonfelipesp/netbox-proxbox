# `netbox_proxbox.static`

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

This directory is the top-level container for plugin static files served by Django/NetBox.

## Structure

- [`netbox_proxbox/`](./netbox_proxbox/): plugin-specific static namespace containing images, JavaScript, compiled CSS, and stylesheets.

## Notes

- Keep static assets under the namespaced `netbox_proxbox/` subtree so they do not collide with other NetBox plugins.
- Browser-side behavior is implemented in the `js/` subtree; CSS sources and generated theme assets live under `css/` and `styles/`.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md)
