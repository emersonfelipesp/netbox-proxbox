# `netbox_proxbox.views.sync_now`

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

This directory contains targeted per-object sync handlers for cluster, node, storage, and VM actions.

## Files And Ownership

- [`__init__.py`](./__init__.py): re-exports sync-now view classes (`ProxmoxClusterSyncNowView`, `ProxmoxNodeSyncNowView`, `ProxmoxStorageSyncNowView`, `VirtualMachineSyncNowView`).
- [`cluster.py`](./cluster.py): `ProxmoxClusterSyncNowView` — syncs a single Proxmox cluster.
- [`node.py`](./node.py): `ProxmoxNodeSyncNowView` — syncs a single Proxmox node.
- [`storage.py`](./storage.py): `ProxmoxStorageSyncNowView` — syncs a single Proxmox storage.
- [`vm.py`](./vm.py): `VirtualMachineSyncNowView` — syncs a single virtual machine through proxbox-api individual sync endpoints.

## Dependencies

- Inbound: model-level `register_model_view(..., "proxbox_sync_now", path="proxbox-sync-now")` decorators register these actions on NetBox object views.
- Outbound: `netbox_proxbox.services.individual_sync`, plugin models, NetBox view base classes, and templates.

## Notes

- These views provide targeted sync buttons that operate on individual objects rather than full sync jobs.
- They call `netbox_proxbox.services.individual_sync` helpers to communicate with proxbox-api for single-resource updates.
- These actions are registered via `register_model_view` path suffix `proxbox-sync-now` on the corresponding object detail routes.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
