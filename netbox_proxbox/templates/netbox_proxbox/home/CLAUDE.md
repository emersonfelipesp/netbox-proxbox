# `templates/netbox_proxbox/home`

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

This directory contains dashboard card fragments and log display partials for the plugin home page.

## Files And Ownership

- [`proxmox_card.html`](./proxmox_card.html): Proxmox endpoint summary card.
- [`netbox_card.html`](./netbox_card.html): remote NetBox endpoint summary card.
- [`fastapi_card.html`](./fastapi_card.html): ProxBox backend summary card.
- [`log_messages.html`](./log_messages.html): streamed or polled message display block.
- [`quick_schedule_banner.html`](./quick_schedule_banner.html): home-page banner that surfaces the quick schedule form when recurring sync is not already configured.
- [`job_live_summary.html`](./job_live_summary.html): live job progress summary fragment shown on the home page while a sync is running.

## Dependencies

- Inbound: `HomeView` and related page templates include these fragments.
- Outbound: JS polling/card-refresh code and view functions like `get_proxmox_card()` and `get_service_status()`.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
