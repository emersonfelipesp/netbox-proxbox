# Version 0.0.18

## Summary

Version `0.0.18` adds **full Proxmox VE 9.2 support** to the plugin, including
persisted Django models for SDN fabrics, route maps, prefix lists, and custom
datacenter CPU models; automated sync services for these new objects; completed
node- and VM-level firewall sync; and HA arm/disarm action views. It pairs with
backend [`proxbox-api 0.0.14`](https://github.com/emersonfelipesp/proxbox-api),
which ships the SDN, CPU-model, and datacenter-options endpoints that power
the new sync services.

The NetBox compatibility range remains `4.5.8` – `4.6.99` (`min_version` /
`max_version` unchanged). Django migration `0041_pve_9_2.py` adds four tables
and one new column; run `manage.py migrate netbox_proxbox` after upgrade.

## What's New In The Plugin

- **SDN model scaffolding.** Three new Django models persist Proxmox VE SDN
  objects: `ProxmoxSdnFabric` (WireGuard / BGP / VXLAN / OSPF fabrics),
  `ProxmoxSdnRouteMap`, and `ProxmoxSdnPrefixList`. Full CRUD views, REST API
  viewsets, and a new **SDN** navigation group are included.
- **Datacenter CPU model scaffolding.** New `ProxmoxDatacenterCpuModel` model
  with full CRUD and REST API; listed under the **Infrastructure** navigation
  group.
- **SDN and CPU-model sync services.** `services/sync_sdn.py` calls
  `GET /proxmox/sdn/fabrics`, `/sdn/route-maps`, and `/sdn/prefix-lists`.
  `services/sync_datacenter.py` calls `GET /proxmox/datacenter/cpu-models`.
  Both upsert records and mark removed rows stale.
- **Completed firewall sync.** `services/sync_firewall.py` gains
  `sync_node_firewall()` (calls `GET /proxmox/firewall/nodes/{node}/rules`)
  and `sync_vm_firewall()` (calls `GET /proxmox/firewall/vms/{vmid}/rules`)
  so per-node and per-VM `ProxmoxFirewallRule` rows are populated automatically.
- **HA arm/disarm action views.** `HaArmView` and `HaDisarmView` proxy to
  `POST /proxmox/cluster/ha/arm` and `POST /proxmox/cluster/ha/disarm` on
  the backend. Both require `change_proxmoxendpoint` permission and return
  JSON for AJAX callers.
- **`ProxmoxNode.location` field.** Stores the geographic or physical location
  of a node as reported by PVE 9.2+.

## What's New In The Backend (`proxbox-api 0.0.14`)

The plugin requires `proxbox-api >= 0.0.14`. The backend release adds:

- `GET /proxmox/sdn/fabrics`, `GET /proxmox/sdn/route-maps`,
  `GET /proxmox/sdn/prefix-lists` — per-cluster SDN topology reads.
- `GET /proxmox/datacenter/cpu-models` — custom CPU model enumeration.
- `GET /proxmox/datacenter/options` — datacenter-level options including
  CRS (Cluster Resource Scheduling) settings.
- `POST /proxmox/cluster/ha/arm` and `POST /proxmox/cluster/ha/disarm` —
  cluster HA arm/disarm verbs (write-gated by `allow_writes`).
- `GET /proxmox/cluster/ha/manager-status` — HA manager state endpoint.
- Extended node config: `location` field in node config responses.
- Access token management endpoints.

## Compatibility

| NetBox   | netbox-proxbox | proxbox-api | netbox-sdk     | proxmox-sdk    |
|----------|----------------|-------------|----------------|----------------|
| >=4.5.8  | v0.0.18 | v0.0.14 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8  | v0.0.17 | v0.0.13 | v0.0.8.post1 | v0.0.3.post1 |

NetBox compatibility range: `4.5.8` – `4.6.99` (unchanged). Certified
simultaneously against NetBox `v4.5.8`, `v4.5.9`, `v4.6.0`, and `v4.6.1`.

## Upgrade Notes

- **Run `manage.py migrate netbox_proxbox`** — migration `0041_pve_9_2.py`
  creates the `proxmoxsdnfabric`, `proxmoxsdnroutemap`, `proxmoxsdnprefixlist`,
  and `proxmoxdatacentercpumodel` tables and adds the `location` column to
  `proxmoxnode`.
- **Upgrade the backend to `proxbox-api 0.0.14`** before the plugin so the
  `/proxmox/sdn/*` and `/proxmox/datacenter/cpu-models` routes are available.
- Restart the NetBox WSGI process after migration and static-file collection.
- The read-only reflection path for existing objects is unchanged.
