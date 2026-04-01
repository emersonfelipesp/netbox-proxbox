# `netbox_proxbox.views`

This directory implements the plugin's NetBox UI behavior, including dashboard pages, endpoint CRUD views, sync actions, job integration, and status utilities.

## Files And Ownership

- [`__init__.py`](./__init__.py): top-level page views and re-exports for endpoint views, cluster views, dashboard pages, sync enqueue actions, status checks, settings/storage views, backup/snapshot/task views, and job integration helpers.
- [`backend_sync.py`](./backend_sync.py): shared helper that ensures a Proxmox endpoint is synchronized to proxbox-api before live reads.
- [`cards.py`](./cards.py): dashboard card hydration for Proxmox cluster/version data.
- [`cluster.py`](./cluster.py): cluster storage summary tab and Proxmox cluster summary tab.
- [`cluster_nodes_tab.py`](./cluster_nodes_tab.py): cluster/node tab for Proxmox endpoint detail pages.
- [`dashboard.py`](./dashboard.py): operational cluster and node summary dashboard.
- [`home_context.py`](./home_context.py): home page context assembly and quick-schedule defaults.
- [`sync.py`](./sync.py): POST endpoints that enqueue `ProxboxSyncJob` runs for devices, storage, virtual machines, virtual disks, backups, snapshots, network interfaces, IP addresses, and full update.
- [`schedule_sync.py`](./schedule_sync.py): recurring/one-shot scheduler UI and quick-schedule
  flow from the home dashboard.
- [`keepalive_status.py`](./keepalive_status.py): health and reachability checks for FastAPI, remote NetBox, and Proxmox services.
- [`job_run.py`](./job_run.py), [`job_cancel.py`](./job_cancel.py), and [`job_stream.py`](./job_stream.py): integrate rerun/cancel actions and SSE log streaming into NetBox core Job views for Proxbox sync jobs.
- [`settings.py`](./settings.py): plugin settings page for runtime feature toggles.
- [`storage.py`](./storage.py): CRUD list/detail/delete views for `ProxmoxStorage`.
- [`vm_backup.py`](./vm_backup.py): CRUD list/detail/delete views and the VirtualMachine tab for `VMBackup`.
- [`vm_snapshot.py`](./vm_snapshot.py): CRUD list/detail/delete views and the VirtualMachine tab for `VMSnapshot`.
- [`vm_task_history.py`](./vm_task_history.py): detail and VirtualMachine tab views for `VMTaskHistory`.
- [`vm_config.py`](./vm_config.py): live Proxmox config tab for `VirtualMachine` records.
- [`vm_sync_now.py`](./vm_sync_now.py): targeted per-VM sync action button handler.
- [`external_pages.py`](./external_pages.py): redirect or informational external community pages.
- [`endpoints/`](./endpoints/): model views for the three endpoint models.

## Dependencies

- Inbound: `urls.py` routes here for all plugin UI behavior.
- Outbound: plugin models, forms, tables, filtersets, templates, `requests`, the external ProxBox FastAPI service, and `websocket_client.py`.

## Notes

- `sync.py`, `schedule_sync.py`, `dashboard.py`, `home_context.py`, `job_run.py`, `job_cancel.py`, `job_stream.py`, `keepalive_status.py`, and `cards.py` define most sync/user workflow behavior.
- `HomeView` is the main dashboard entrypoint and assembles endpoint lists plus derived backend URLs for the templates.
- Most changes to user-visible behavior land here first, then cascade into templates, static assets, and tests.
- When adding or changing sync actions, update `urls.py`, `sync.py`, scheduling forms/views, template extensions, and relevant frontend/tests that assert button routes and job flow.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`endpoints/CLAUDE.md`](./endpoints/CLAUDE.md)
