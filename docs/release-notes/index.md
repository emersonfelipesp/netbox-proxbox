# Release Notes

This section tracks the release line represented by this repository and keeps older historical placeholders explicit.

## Current Release Line

The plugin source in this repository is currently `0.0.21` on the
development line. The sibling plugins (`netbox-pbs`,
`netbox-ceph`, and `netbox-pdm`) live in standalone repositories under
[@emersonfelipesp](https://github.com/emersonfelipesp) and declare
`netbox-proxbox>=0.0.18,<0.1.0` as an install-time dependency.
`netbox-packer` is installable standalone but is prepared for certification as
part of the same plugin family.

## Highlights By Version

| Version | Summary |
|---------|---------|
| `0.0.21` | Sync-mode filtering at source: per-record VM and VM-template filtering enforced by `proxbox-api 0.0.18.post5` using `sync_mode_vm`/`sync_mode_vm_template` query params — a `disabled` mode no longer creates dependent NetBox objects for skipped VMs. Two-phase VM batch processing and per-VM dispatch failure isolation. Interface-dense guest alias matching by name and partial-failure stream frame. Pairs with backend [`proxbox-api 0.0.18.post5`](https://github.com/emersonfelipesp/proxbox-api), `proxmox-sdk 0.0.12`, and `netbox-sdk 0.0.10`. |
| `0.0.20.post3` | Endpoint enablement hardening: disabled endpoint-like rows remain visible inventory records but no longer trigger proxbox-api, NetBox, Proxmox, PBS, PDM, OpenAPI, keepalive, registration, startup/signal, or sync network attempts. Adds LLM/developer documentation and regression tests for PBSEndpoint/PDMEndpoint shared enabled-field contracts. Pairs with backend [`proxbox-api 0.0.17.post1`](https://github.com/emersonfelipesp/proxbox-api), `proxmox-sdk 0.0.11.post1`, and `netbox-sdk 0.0.9.post1`. |
| `0.0.20.post2` | Read-only homepage visibility patch: the Proxbox homepage now renders a **Latest Sync Jobs** table with the five most recent Proxbox sync jobs after the additional plugin endpoint cards, plus a **View all sync jobs** button. Pairs with backend [`proxbox-api 0.0.17.post1`](https://github.com/emersonfelipesp/proxbox-api), `proxmox-sdk 0.0.11.post1`, and `netbox-sdk 0.0.9.post1`. |
| `0.0.20.post1` | Post-release patch for the NP-F1 VM-template sync fix: `sync_vm_templates()` was implemented but never called, so `ProxmoxVMTemplate` inventory was never populated. The stage is now wired into `ProxboxSyncJob` through commits `0f843083` and `aae76f13`. Pairs with backend [`proxbox-api 0.0.17.post1`](https://github.com/emersonfelipesp/proxbox-api), `proxmox-sdk 0.0.11.post1`, and `netbox-sdk 0.0.9.post1`. |
| `0.0.20` | IP-address ownership safety and interface-batch settings persistence. The paired backend prevents VM-interface IP sync from taking over an address that already belongs to another interface, and plugin Settings page values for `interface_batch_size` / `interface_batch_delay_ms` now persist to the database. Pairs with backend [`proxbox-api 0.0.17`](https://github.com/emersonfelipesp/proxbox-api). |
| `0.0.19` | Database and integration compatibility fixes: `allow_writes` in ProxmoxEndpoint API, `verify_ssl` migration guards, FastAPI endpoint token-drift fix, PBS/PDM host/timeout_seconds bridging properties. Pairs with backend [`proxbox-api 0.0.16`](https://github.com/emersonfelipesp/proxbox-api). |
| `0.0.18.post1` | Certification-readiness post release: package metadata, project URLs, Apache-2.0 evidence, certification checklist, family application packet, support links, and a database-only repair migration for missing `PBSEndpoint.enabled` / `PDMEndpoint.enabled` columns on affected v0.0.18 installs. No runtime sync behavior changes. |
| `0.0.18` | Full PVE 9.2 support: SDN fabric/route-map/prefix-list models and sync, custom datacenter CPU model persistence, completed per-node firewall sync (per-VM sync implemented, not yet wired automatically), HA arm/disarm action views, and `ProxmoxNode.location` field. Migration `0041_pve_9_2.py`. Pairs with backend [`proxbox-api 0.0.14`](https://github.com/emersonfelipesp/proxbox-api). |
| `0.0.17` | Adds read-only Proxmox VE firewall sync (closes [#326](https://github.com/emersonfelipesp/netbox-proxbox/issues/326)): consumes the backend's `/proxmox/firewall/*` surface for datacenter, node, per-VM (QEMU + LXC), and per-VNet (SDN) zones — rules, security groups, IP sets, aliases, and options. Certifies NetBox `v4.6.1` alongside `v4.5.8` / `v4.5.9` / `v4.6.0`. Pairs with backend [`proxbox-api 0.0.13`](https://github.com/emersonfelipesp/proxbox-api), which ships the matching twelve firewall read routes plus `PUT /intent/tag-pending-deletion` and `PUT /intent/untag-pending-deletion` intent-tag helpers and the `0.0.12.post1` / `0.0.12.post2` stability fixes. No DB migration; firewall objects are reflected read-only through HTTP and are not yet persisted as Django models. |
| `0.0.16` | Fixes the operational Cluster Dashboard panel on the Proxmox endpoint detail page (issue [#455](https://github.com/emersonfelipesp/netbox-proxbox/issues/455)): preserves API-reported `nodes_total` / `nodes_online` when live rows are a strict subset of the cluster membership, broadens `build_local_node_rows` to fall back to all `ProxmoxNode` rows under the cluster name when scoped sibling lookup is empty, and renders placeholder rows (`status="unknown"`) for cluster members named by the API status payload that have not yet been synced. Pairs with backend `proxbox-api 0.0.12`. No DB migration, no model change, no NetBox compatibility rotation. |
| `0.0.15.post2` | Post-release patch on stable `0.0.15`: lands the `PBSEndpoint` / `PDMEndpoint` / `PDMRemote` Django models with ForeignKey wiring (`PDMEndpoint.proxmox_endpoints` M2M -> `ProxmoxEndpoint`, `pbs_endpoints` M2M -> `PBSEndpoint`) per [#449](https://github.com/emersonfelipesp/netbox-proxbox/issues/449); adds the `build-pve-template` REST action on `ProxmoxEndpointViewSet` (#452); pairs with backend `proxbox-api 0.0.11.post2`, which lifts the `proxmox-sdk` pin to `0.0.5.post1` so the new `proxmox_sdk.pdm` subpackage is available to the backend. Migration `0048_pdm_pbs_endpoint_models` creates the three tables; UI / API surfaces land in Phase 2/3 of #449. No NetBox compatibility rotation. |
| `0.0.15.post1` | Post-release patch on stable `0.0.15`: VM/LXC resource API pagination (fixes 100-object truncation), PVE 9.x HA rules in the cluster HA dashboard, cloud image template PUT/PATCH support, `ProxmoxEndpointBulkDeleteView` bulk-delete 404 fix, `NetBoxModelSerializer` MRO delegation for create/update, and full-update resilience (skip optional stages on failure). Paired with backend `proxbox-api 0.0.11.post1`. No NetBox compatibility rotation. |
| `0.0.15` | Adds the opt-in **NetBox → Proxmox intent** path (issue #377, twelve sub-PRs A–L): typed-confirmation master flag, branch-merge `post_merge` hook, plan validator, CREATE/UPDATE dispatchers, safe-delete with `DeletionRequest` four-eyes approval flow, cloud-init payload mapping, and the apply-job + deletion-request UIs. Also decouples HTTPS scheme from `Verify SSL` on `FastAPIEndpoint` (issue #352); adds `overwrite_ip_address_dns_name` so the backend can populate `IPAddress.dns_name` from Proxmox guest hostnames (issue #354); ships a per-VM **HA tab**, a cluster-wide **HA Status** page (issue #243), and the forward-compatible SSH hardware-discovery credential surface for issue #374. Pairs with backend `proxbox-api 0.0.11`, which ships both the reflection/HA surface and the `/intent/*` HTTP surface. With `netbox_to_proxmox_enabled=False` (default), no behavior changes from the read-only reflection path. |
| `0.0.14` | Certification bump for the separate `proxbox-api` backend release `0.0.10.post2`. No plugin source changes; REST / SSE / WebSocket / auth / overwrite-flag contracts remain compatible with backend `0.0.9.post2`. Backend internally adopts `netbox-sdk==0.0.8.post1` and supports NetBox `4.5.8`, `4.5.9`, and official `4.6.0`. |
| `0.0.13.post4` | Re-pins `proxbox-api==0.0.9.post2` (fixes `create_storages()` `TypeError` regression in `0.0.9.post1`); certifies NetBox `4.5.8` and `4.5.9` for issue #349. Supersedes `0.0.13.post3` which never reached PyPI due to a stale `uv.lock`. |
| `0.0.13.post2` | Re-pins `proxbox-api==0.0.9.post1`; adds matrix row for the new pair; no runtime behavior change |
| `0.0.13.post1` | Bumps `proxbox-api==0.0.9` pin; certifies NetBox `v4.6.0-beta2`; documents endpoint import/export page; CI screenshot rebase fix |
| `0.0.13` | Per-endpoint Settings tab on ProxmoxEndpoint detail; surfaces all `overwrite_*` flags in the plugin UI with tri-state semantics; VM-sync device flag enforcement (overwrite_device_*) honored end-to-end; merge-semantics label for `overwrite_vm_tags`; `_ensure_device` fix; narrowed broad except handlers in sync views and template tags |
| `0.0.12` | NetBox 4.6.x support; native `VirtualMachineType` sync (QEMU / LXC); Clusters list page and API; site/tenant on ProxmoxEndpoint; ships with proxbox-api v0.0.8.post1 |
| `0.0.11` | Backup Routines, individual sync buttons, live job panel, Backend Logs, encryption key, endpoint CSV import/export, auto-push NetBox config to backend, three-tier error severity, extended storage/replication views, and many bug fixes |
| `0.0.10` | Cluster and node tracking with NetBox Cluster/Device links; Mode field fix on endpoint detail |
| `0.0.9.post4` | Follow-up migration fixes for upgrade paths and storage schema issues |
| `0.0.9` | Storage relationships, task history, per-VM sync, settings, dashboard, and richer live job UX |
| `0.0.8` | NetBox Jobs-based scheduling, SSE-backed sync jobs, VM snapshots, virtual disk sync, and NetBox 4.5 alignment |
| `0.0.7` | Historical release in the path to the modern NetBox 4.5-compatible line |
| `0.0.1`-`0.0.6` | Early project history retained as lightweight archive pages |

## Notes

- `0.0.7` through `0.0.9.post4` are the most relevant pages for current upgrade planning.
- Older pages are intentionally brief because the repository does not preserve fuller release-note prose for those versions.


> **Current release:** netbox-proxbox `0.0.20.post3` pairs with proxbox-api `0.0.17.post1` (NetBox `4.5.8`–`4.6.99`).
