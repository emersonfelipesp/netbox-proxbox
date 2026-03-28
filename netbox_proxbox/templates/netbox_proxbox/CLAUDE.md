# `templates/netbox_proxbox`

This is the main Django template namespace for the plugin.

## Main Templates

- Dashboard and informational pages: `home.html`, `community.html`, `contributing.html`, `devices.html`, `virtual_machines.html`.
- Endpoint pages: `proxmoxendpoint.html`, `proxmox_endpoint.html`, `proxmox-endpoints.html`, `netboxendpoint.html`, `fastapiendpoint.html`, and corresponding `*_edit.html` files.
- Sync and status pages: `sync_devices.html`, `sync_virtual_machines.html`, `sync_vm_backups.html`, `sync_full_update.html`, `syncprocess.html`, `proxbox-backend-status.html`, `status_badge.html`, `websocket_page.html`.
- VM backup pages: `vmbackup.html`, `vmbackup_list.html`, `vmbackup_bulk_delete.html`, `virtual_machine_backups.html`.
- Shared fragments: `footer.html`.
- Child subdirectories: `base`, `fastapi`, `home`, `partials`, `proxmox`, `table`, and `test`.

## Dependencies

- Inbound: views throughout `views/` render these templates.
- Outbound: static assets, NetBox base templates, and the JSON/HTML response contracts used by the views.

## Notes

- There is some historical naming overlap in endpoint templates; keep the Python view/template binding in mind before removing or renaming files.
- Any template with dynamic status cards or sync output is likely coupled to the JS files under `static/netbox_proxbox/js/`.

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
