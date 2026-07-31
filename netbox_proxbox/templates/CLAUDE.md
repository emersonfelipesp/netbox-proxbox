# `netbox_proxbox.templates`

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

This directory contains Django templates bundled with the plugin.

## Structure

- [`netbox_proxbox/`](./netbox_proxbox/): the plugin template namespace used by all plugin views.

## Notes

- Template names in Python views resolve into this namespaced subtree.
- Most behavior-rich pages pair templates here with JS under `static/netbox_proxbox/js/`.
- The namespaced subtree includes shared layout templates, page fragments, table snippets, test pages, and widget partials.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md)
