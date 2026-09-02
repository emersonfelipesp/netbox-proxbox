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
- [`endpoint_scope.py`](./endpoint_scope.py): resolves every registered direct-action target through its linked core cluster to exactly one enabled owning `ProxmoxEndpoint`, translates that row to its proxbox-api wire ID, returns the canonical tracked Proxmox cluster name, and fails closed on missing, disabled, ambiguous, conflicting, or unregistered ownership.
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
- All six registered direct actions (cluster, node, storage, backup, snapshot, and task history) pass the owner's backend wire ID as the dedicated `proxmox_endpoint_ids` argument and pin the selected `FastAPIEndpoint`. This scopes both the top-level request and every recursive dependency request; omitting it means "every endpoint held by proxbox-api," including endpoints disabled in NetBox. Ownership is resolved by the linked core-cluster ID, never by cluster name, because names may be duplicated across Proxmox estates. Multiple enabled tracking rows for one core cluster are refused instead of selecting `.first()`; cluster/node rows additionally verify that their direct endpoint agrees with the linked-cluster owner.
- The individual task-history wire contract uses `type` (with `node`, `vmid`, optional `cluster_name`, and optional `upid`). The model field remains `vm_type`; `_resolve_task_history_batch_params()` translates it at the backend boundary.
- `VMTaskHistory.vm_type` is trusted only after normalization to `qemu` or `lxc`. The resolver derives invalid/default/blank values from the linked VM and resolves VMID only from `virtual_machine.proxbox_sync_state.proxmox_vm_id`; it returns a local 422 when required context remains unknown. `type=unknown` and unscoped VMIDs must never reach proxbox-api.
- Snapshot requests validate and prefer the row's authoritative `VMSnapshot.subtype`. Invalid or missing subtype values may fall back to the linked VM's typed sync state and native VM type, but never to removed reflection custom fields or the generic QEMU compatibility default; no supported type means a local 422.
- The shared response handler treats any non-empty `error` payload as a failure even when proxbox-api returns HTTP 200. Backup and snapshot routes use that status/payload combination when no Proxmox session matches.
- These actions are registered via `register_model_view` path suffix `proxbox-sync-now` on the corresponding object detail routes.
- `template_content.py` resolves each form action from the action target itself
  with `get_viewname(target, "proxbox_sync_now")` and `reverse(..., pk=target.pk)`.
  Core Cluster/Device pages keep targeting their linked plugin tracking rows;
  plugin storage/backup/snapshot/task rows and core VMs target themselves.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
