# `netbox_proxbox.views`

This directory implements the plugin's NetBox UI behavior.

## Files And Ownership

- [`__init__.py`](./__init__.py): top-level page views and re-exports for endpoint views,
  sync enqueue actions, status checks, settings/storage views, backup/snapshot/task views, and
  job integration helpers.
- [`sync.py`](./sync.py): POST endpoints that enqueue `ProxboxSyncJob` runs for devices,
  storage, virtual machines, virtual disks, backups, snapshots, and full update.
- [`schedule_sync.py`](./schedule_sync.py): recurring/one-shot scheduler UI and quick-schedule
  flow from the home dashboard.
- [`keepalive_status.py`](./keepalive_status.py): health and reachability checks for FastAPI, remote NetBox, and Proxmox services.
- [`cards.py`](./cards.py): dashboard card hydration for Proxmox cluster/version data.
- [`storage.py`](./storage.py): CRUD list/detail/delete views for `ProxmoxStorage`.
- [`vm_backup.py`](./vm_backup.py): CRUD list/detail/delete views and the VirtualMachine tab for `VMBackup`.
- [`vm_snapshot.py`](./vm_snapshot.py): CRUD list/detail/delete views and the VirtualMachine tab for `VMSnapshot`.
- [`vm_task_history.py`](./vm_task_history.py): detail and VirtualMachine tab views for `VMTaskHistory`.
- [`job_run.py`](./job_run.py) and [`job_cancel.py`](./job_cancel.py): integrate rerun/cancel
  actions into NetBox core Job views for Proxbox sync jobs.
- [`external_pages.py`](./external_pages.py): redirect or informational external community pages.
- [`endpoints/`](./endpoints/): model views for the three endpoint models.

## Dependencies

- Inbound: `urls.py` routes here for all plugin UI behavior.
- Outbound: plugin models, forms, tables, filtersets, templates, `requests`, the external ProxBox FastAPI service, and `websocket_client.py`.

## Notes

- `sync.py`, `schedule_sync.py`, `jobs.py`, `keepalive_status.py`, and `cards.py` define most
  sync/user workflow behavior.
- `HomeView` is the main dashboard entrypoint and assembles endpoint lists plus derived backend URLs for the templates.
- Most changes to user-visible behavior land here first, then cascade into templates and JS.
- When adding or changing sync actions, update `urls.py`, `sync.py`, scheduling forms/views, and
  relevant frontend/tests that assert button routes and job flow.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`endpoints/CLAUDE.md`](./endpoints/CLAUDE.md)
