# Version 0.0.17

## Summary

Version `0.0.17` adds **read-only Proxmox VE firewall sync** to the plugin
(closes issue [#326](https://github.com/emersonfelipesp/netbox-proxbox/issues/326))
and certifies the plugin against the newest patch release of NetBox 4.6.x.
It pairs with backend
[`proxbox-api 0.0.13`](https://github.com/emersonfelipesp/proxbox-api), which
ships the matching read-only `/proxmox/firewall/*` HTTP surface plus
operational tag helpers and stability fixes carried over from
`0.0.12.post2`.

There is **no DB migration** required for the firewall surface in this
release — firewall data is reflected through schemas exposed by the backend
and not yet persisted in NetBox. The NetBox compatibility range remains
`4.5.8` – `4.6.99` (`min_version` / `max_version` unchanged).

## What's New In The Plugin

- **Read-only PVE firewall sync (#326).** The plugin now consumes the
  backend's firewall surface for all Proxmox firewall zones — datacenter,
  per-node, per-VM (QEMU and LXC), and per-VNet (SDN). It surfaces
  firewall rules, security groups, IP sets, aliases, and zone options as
  read-only data without writing back to Proxmox.
- **NetBox `v4.6.1` certified.** Added to the certified support matrix
  alongside `v4.5.8`, `v4.5.9`, and `v4.6.0`. CI matrix updated.
- **Quick Edit button on the plugin home cards (#474).** Endpoint cards
  on the Proxbox home page now expose a Quick Edit modal so operators can
  fix endpoint URLs / tokens without leaving the dashboard.
- **`idna` upgraded to `3.15`** to clear Dependabot alert #75
  (CVE-2024-3651 bypass).

## What's New In The Backend (`proxbox-api 0.0.13`)

The plugin requires `proxbox-api >= 0.0.13`. The backend release adds:

- **`/proxmox/firewall/*` read routes** for every PVE firewall zone:
  datacenter (`/cluster/firewall/{rules,groups,ipset,aliases,options}`),
  per-node (`/nodes/{node}/firewall/{rules,options,log}`), per-VM
  (`/nodes/{node}/qemu|lxc/{vmid}/firewall/{rules,aliases,ipset,options,log,refs}`),
  and per-VNet (`/cluster/sdn/vnets/{vnet}/firewall/{rules,options}`).
  Twelve endpoints total. All read-only.
- **`PUT /intent/tag-pending-deletion` and
  `PUT /intent/untag-pending-deletion`** intent-tag helpers used by the
  plugin's safe-delete flow to mark Proxmox VMs with the
  `proxbox-pending-deletion` tag before authorized destruction.
- **Stability fixes** carried over from `0.0.12.post1` / `0.0.12.post2`:
  skip bootstrap when no NetBox endpoint is configured (#130), replace
  deprecated nginx `listen ... http2` with the `http2` directive (#137),
  add `PROXBOX_LOG_LEVEL` env var and suppress `netbox_sdk.client`
  verbosity at non-DEBUG levels (#133), bypass `cluster_status`
  preflight in `resolve_vm_config` (#134), and guard against
  FastAPI `Query` defaults leaking as `run_id` (#132).

## Compatibility

| NetBox   | netbox-proxbox | proxbox-api | netbox-sdk     | proxmox-sdk    |
|----------|----------------|-------------|----------------|----------------|
| >=4.5.8  | v0.0.17 | v0.0.13 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8  | v0.0.16 | v0.0.12 | v0.0.8.post1 | v0.0.3.post1 |

NetBox compatibility range: `4.5.8` – `4.6.99` (unchanged). Certified
simultaneously against NetBox `v4.5.8`, `v4.5.9`, `v4.6.0`, and
official `v4.6.1`.

## Upgrade Notes

- **No database migration** for the firewall surface — it is reflected
  read-only through the backend HTTP routes.
- **Upgrade the backend to `proxbox-api 0.0.13`** before the plugin so
  the `/proxmox/firewall/*` routes are available when the plugin asks
  for them.
- Restart the NetBox WSGI process so the updated plugin views and any
  bundled static assets are picked up.
- The read-only reflection path is unchanged for non-firewall objects.
  The opt-in NetBox → Proxmox intent path introduced in `0.0.15` is
  unchanged in `0.0.17`; the firewall surface is reflection-only and
  does not extend the intent path.

## Known Gaps

- Firewall objects are surfaced from the backend but are **not yet
  persisted** as Django models on the NetBox side. A follow-up release
  will add a `FirewallRule` / `SecurityGroup` model plus full bulk-import
  and CSV/JSON/YAML export parity with the existing endpoint pages.
- Write-back to Proxmox firewall objects is **out of scope** for
  `0.0.17`; the firewall integration is read-only by design and is not
  routed through the `/intent/*` apply path.
