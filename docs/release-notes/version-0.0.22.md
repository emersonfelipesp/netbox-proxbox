# Version 0.0.22

netbox-proxbox `0.0.22` pairs with the `proxbox-api 0.0.19`
backend release, the `proxmox-sdk 0.0.12` Proxmox SDK, and
`netbox-sdk 0.0.10`. NetBox compatibility is unchanged: `4.5.8` through
`4.6.99` (validated against `4.5.8`, `4.5.9`, and `4.6.0` through `4.6.3`).

Current pairing: `netbox-proxbox 0.0.22 ↔ proxbox-api 0.0.19 ↔ proxmox-sdk 0.0.12 ↔ netbox-sdk 0.0.10`.

## Highlights

- **Proxmox SDN sync.** The optional `sync_mode_sdn` control is available both
  globally and per Proxmox endpoint. It defaults to `disabled`; the **All** sync
  selection includes the SDN stage, but stage gating skips it until the
  effective SDN mode is enabled.
- **Plugin SDN inventory.** New Proxbox inventory models preserve Proxmox SDN
  controllers, zones, VNets, subnets, and bindings with raw Proxmox payloads,
  sync status, conflict reasons, and links to the reflected NetBox objects.
- **NetBox SDN reconciliation.** The paired backend reconciles Proxmox SDN into
  NetBox built-ins: `vpn.L2VPN` (`EVPN` -> `vxlan-evpn`, `VXLAN` -> `vxlan`),
  `ipam.RouteTarget` for EVPN `rt-import` values as import targets only,
  `ipam.Prefix`, and conflict-safe `vpn.L2VPNTermination` rows.
  Reconciliation never overwrites a manual termination that already binds a
  target object to a different L2VPN.
- **Read-only Proxmox behavior.** SDN sync reads from Proxmox and writes only to
  NetBox and Proxbox inventory metadata. Unsupported Proxmox clusters are
  skipped, not failed, so mixed estates can keep using the same sync run.

## Compatibility

| NetBox  | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.22 | v0.0.19 | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.21 | v0.0.18.post5 | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.20.post3 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20.post2 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20.post1 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20 | v0.0.17 | v0.0.8.post1 | v0.0.11 |

`proxbox-api` is not a Python dependency of this plugin; the services
communicate over HTTP/SSE/WebSocket. Install the matching `proxbox-api 0.0.19`
backend separately. SDN sync requires `proxbox-api >= 0.0.19`. This release
supports NetBox `4.5.8` through `4.6.99` and requires Python `>=3.12`.

## Upgrade Notes

- Upgrade the plugin to `netbox-proxbox 0.0.22` and the backend to
  `proxbox-api 0.0.19`.
- Use `proxmox-sdk 0.0.12` and `netbox-sdk 0.0.10` in the paired backend
  environment.
- Run the normal NetBox plugin upgrade flow: install the package, run
  `python manage.py migrate netbox_proxbox`, collect static files, and restart
  NetBox/RQ workers.
- Migration `0055` adds the SDN inventory models. Existing installations keep
  SDN sync disabled until `sync_mode_sdn` is enabled globally or per endpoint.
