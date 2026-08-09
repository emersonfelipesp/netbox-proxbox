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

This directory contains targeted per-object sync handlers for plugin cluster,
node, storage, backup, snapshot, and task-history actions, plus a legacy direct
VM handler. The active core VirtualMachine action is registered by
`../vm_sync_now.py` and queues the targeted sync job.

## Files And Ownership

- [`__init__.py`](./__init__.py): lazily re-exports all sync-now view classes to avoid circular imports during app initialization.
- [`backup.py`](./backup.py): `VMBackupSyncNowView` — syncs a single VM backup.
- [`cluster.py`](./cluster.py): `ProxmoxClusterSyncNowView` — syncs a single Proxmox cluster.
- [`node.py`](./node.py): `ProxmoxNodeSyncNowView` — syncs a single Proxmox node.
- [`snapshot.py`](./snapshot.py): `VMSnapshotSyncNowView` — syncs a single VM snapshot.
- [`storage.py`](./storage.py): `ProxmoxStorageSyncNowView` — syncs a single Proxmox storage.
- [`task_history.py`](./task_history.py): `VMTaskHistorySyncNowView` — syncs a single VM task-history row.
- [`vm.py`](./vm.py): legacy `VirtualMachineSyncNowView` implementation retained for compatibility; the eagerly imported action lives in `../vm_sync_now.py`.

## Dependencies

- Inbound: model-level `register_model_view(..., "proxbox_sync_now", path="proxbox-sync-now")` decorators register these actions on NetBox object views.
- Outbound: `netbox_proxbox.services.individual_sync`, plugin models, NetBox view base classes, and templates.

## Notes

- These views provide targeted sync buttons that operate on individual objects rather than full sync jobs.
- They call `netbox_proxbox.services.individual_sync` helpers to communicate with proxbox-api for single-resource updates.
- These actions are registered via `register_model_view` path suffix `proxbox-sync-now` on the corresponding object detail routes.
- `template_content.py` resolves each form action from the action target itself
  with `get_viewname(target, "proxbox_sync_now")` and `reverse(..., pk=target.pk)`.
  Core Cluster/Device pages keep targeting their linked plugin tracking rows;
  plugin storage/backup/snapshot/task rows and core VMs target themselves.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
