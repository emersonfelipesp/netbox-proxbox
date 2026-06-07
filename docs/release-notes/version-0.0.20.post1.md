# Version 0.0.20.post1

netbox-proxbox `0.0.20.post1` pairs with the `proxbox-api 0.0.17.post1`
backend release, the `proxmox-sdk 0.0.11.post1` Proxmox SDK, and
`netbox-sdk 0.0.9.post1`. NetBox compatibility is unchanged: `4.5.8` through
`4.6.99` (validated against `4.5.8`, `4.5.9`, `4.6.0`, and the official
`4.6.1`).

## Highlights

- **VM template sync is now wired into `ProxboxSyncJob`.** `ProxmoxVMTemplate`
  inventory was never populated before because `sync_vm_templates()` was
  implemented but never called; commits `0f843083` and `aae76f13` connect the
  template stage to the scheduled/full sync job path.

## Compatibility

| NetBox  | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.20.post1 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20 | v0.0.17 | v0.0.8.post1 | v0.0.11 |
| >=4.5.8 | v0.0.19 | v0.0.16 | v0.0.8.post1 | v0.0.9 |

`proxbox-api` is not a Python dependency of this plugin; the services
communicate over HTTP/SSE/WebSocket. Install the matching
`proxbox-api 0.0.17.post1` backend separately. This release supports NetBox
`4.5.8` through `4.6.99` and requires Python `>=3.12`.

## Upgrade Notes

- Upgrade the plugin to `netbox-proxbox 0.0.20.post1` and the backend to
  `proxbox-api 0.0.17.post1` together.
- Use `proxmox-sdk 0.0.11.post1` and `netbox-sdk 0.0.9.post1` in the paired
  backend environment.
- Run the normal NetBox plugin upgrade flow: install the package, run
  `python manage.py migrate netbox_proxbox`, collect static files, and restart
  NetBox/RQ workers.
- After upgrade, run a full Proxbox sync to populate `ProxmoxVMTemplate`
  inventory through the newly wired template stage.
