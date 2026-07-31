# `netbox_proxbox.management`

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

This package contains Django management commands for the ProxBox plugin.

## Files And Ownership

- [`__init__.py`](./__init__.py): package marker.
- [`commands/`](./commands): Django management command modules.

## Dependencies

- Inbound: Django's `manage.py` CLI imports commands from this package when `netbox_proxbox` is installed.
- Outbound: `netbox_proxbox.models`, `netbox_proxbox.signals`, and Django core management utilities.

## Usage

Management commands are invoked via:

```bash
python manage.py proxbox_fix_tokens [--fix]
```

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`commands/CLAUDE.md`](./commands/CLAUDE.md)
