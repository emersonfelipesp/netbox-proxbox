# `netbox_proxbox.views.sync_now`

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
