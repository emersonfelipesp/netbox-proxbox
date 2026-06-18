# Version 0.0.21

netbox-proxbox `0.0.21` pairs with the `proxbox-api 0.0.18.post5`
backend release, the `proxmox-sdk 0.0.12` Proxmox SDK, and
`netbox-sdk 0.0.10`. NetBox compatibility is unchanged: `4.5.8` through
`4.6.99` (validated against `4.5.8`, `4.5.9`, and `4.6.0` through `4.6.3`).

## Highlights

- **Sync-mode filtering at source.** Per-record VM and VM-template filtering is
  now enforced by the `proxbox-api` backend using the `sync_mode_vm` /
  `sync_mode_vm_template` query parameters transmitted by the plugin.  A
  `disabled` mode no longer creates dependent NetBox objects (manufacturer,
  device-type, cluster, site, node-device, role) for VMs that will never sync,
  because the backend skips those records before dependency precompute.
- **VM sync reliability.** Two-phase VM batch processing eliminates event-loop
  starvation on large clusters.  Per-VM dispatch failures are isolated so one
  VM error counts against `failed_vms` rather than aborting the whole queue.
- **Interface-dense guest fixes.** Guest-agent alias entries are matched by name
  (not MAC) and aggregated into their parent interface.  A partial-failure bulk
  reconciliation now raises and emits a failed stream frame instead of silent
  empty/partial success.
- **Template forwarding contract test.** `tests/test_sync_mode_forwarding.py`
  pins the two sync-mode query params that the plugin transmits to the backend.

## Compatibility

| NetBox  | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.21 | v0.0.18.post5 | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.20.post3 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20.post2 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20.post1 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20 | v0.0.17 | v0.0.8.post1 | v0.0.11 |

`proxbox-api` is not a Python dependency of this plugin; the services
communicate over HTTP/SSE/WebSocket. Install the matching
`proxbox-api 0.0.18.post5` backend separately. This release supports NetBox
`4.5.8` through `4.6.99` and requires Python `>=3.12`.

## Upgrade Notes

- Upgrade the plugin to `netbox-proxbox 0.0.21` and the backend to
  `proxbox-api 0.0.18.post5`.
- Use `proxmox-sdk 0.0.12` and `netbox-sdk 0.0.10` in the paired
  backend environment.
- Run the normal NetBox plugin upgrade flow: install the package, run
  `python manage.py migrate netbox_proxbox`, collect static files, and restart
  NetBox/RQ workers.
- No model or migration changes are included in this release.
