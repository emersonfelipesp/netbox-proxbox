# `templates/netbox_proxbox`

This is the main Django template namespace for the plugin.

## Main Templates

- Dashboard and informational pages: `home.html`, `dashboard.html`, `community.html`, `contributing.html`, `devices.html`, `interfaces.html`, `ip_addresses.html`, `lxc_containers.html`, and `virtual_machines.html`.
- Endpoint pages: `proxmoxendpoint.html`, `proxmoxendpoint_list.html`, `proxmoxendpoint_edit.html`, `proxmoxendpoint_cluster_nodes.html`, `proxmox_endpoint.html`, `proxmox-endpoints.html`, `netboxendpoint.html`, `netboxendpoint_list.html`, `netboxendpoint_edit.html`, `fastapiendpoint.html`, `fastapiendpoint_list.html`, `fastapiendpoint_edit.html`, and `fastapiendpoint_openapi.html`.
- Sync, status, and settings pages: `schedule_sync.html`, `settings.html`, `sync_devices.html`, `sync_storage.html`, `sync_virtual_machines.html`, `sync_virtual_disks.html`, `sync_vm_backups.html`, `sync_vm_snapshots.html`, `sync_network_interfaces.html`, `sync_ip_addresses.html`, `sync_full_update.html`, `proxbox-backend-status.html`, `status_badge.html`, `websocket_page.html`, and `vm_proxmox_config.html`.
- Inventory detail/list pages: `storage_list.html`, `vmbackup.html`, `vmbackup_list.html`, `vmbackup_bulk_delete.html`, `vmsnapshot.html`, `vmsnapshot_list.html`, `vmtaskhistory.html`, and `proxmoxstorage.html` (VM backups on a virtual machine use NetBox `generic/object_children.html` via `ObjectChildrenView`).
- Shared fragments and includes: `footer.html` and the reusable `inc/` snippets for job buttons, runtime panels, live poll alerts, schedule form fields, and VM sync actions.
- Child subdirectories: `base`, `cluster`, `fastapi`, `home`, `inc`, `partials`, `proxmox`, `table`, `test`, and `widgets`.

## Dependencies

- Inbound: views throughout `views/` render these templates.
- Outbound: static assets, NetBox base templates, and the JSON/HTML response contracts used by the views.

## Notes

- There is some historical naming overlap in endpoint templates; keep the Python view/template binding in mind before removing or renaming files.
- Any template with dynamic status cards or sync output is likely coupled to the JS files under `static/netbox_proxbox/js/`.
- Sync buttons in `home.html` carry `data-sync-url` for job-enqueue POST actions; job progress and log details are shown on NetBox Job pages through the Proxbox template extension fragments.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children:
  - [`base/CLAUDE.md`](./base/CLAUDE.md)
  - [`fastapi/CLAUDE.md`](./fastapi/CLAUDE.md)
  - [`home/CLAUDE.md`](./home/CLAUDE.md)
  - [`partials/CLAUDE.md`](./partials/CLAUDE.md)
  - [`proxmox/CLAUDE.md`](./proxmox/CLAUDE.md)
  - [`table/CLAUDE.md`](./table/CLAUDE.md)
  - [`test/CLAUDE.md`](./test/CLAUDE.md)
