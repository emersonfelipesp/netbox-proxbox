# `netbox_proxbox.views`

This directory implements the plugin's NetBox UI behavior.

## Files And Ownership

- [`__init__.py`](./__init__.py): top-level page views and re-exports for endpoint views, sync helpers, status checks, and backup views.
- [`sync.py`](./sync.py): HTTP endpoints that trigger backend sync operations over the FastAPI service.
- [`keepalive_status.py`](./keepalive_status.py): health and reachability checks for FastAPI, remote NetBox, and Proxmox services.
- [`cards.py`](./cards.py): dashboard card hydration for Proxmox cluster/version data.
- [`vm_backup.py`](./vm_backup.py): CRUD list/detail/delete views and the VirtualMachine tab for `VMBackup`.
- [`sync_process.py`](./sync_process.py): CRUD list/detail/delete views for `SyncProcess`.
- [`external_pages.py`](./external_pages.py): redirect or informational external community pages.
- [`endpoints/`](./endpoints/): model views for the three endpoint models.

## Dependencies

- Inbound: `urls.py` routes here for all plugin UI behavior.
- Outbound: plugin models, forms, tables, filtersets, templates, `requests`, the external ProxBox FastAPI service, and `websocket_client.py`.

## Notes

- `sync.py`, `keepalive_status.py`, `cards.py`, and `websocket_client.py` together define the plugin's integration boundary with the external backend.
- `HomeView` is the main dashboard entrypoint and assembles endpoint lists plus derived backend URLs for the templates.
- Most changes to user-visible behavior land here first, then cascade into templates and JS.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`endpoints/CLAUDE.md`](./endpoints/CLAUDE.md)
