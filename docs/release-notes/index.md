# Release Notes

This section tracks the release line represented by this repository and keeps older historical placeholders explicit.

## Current Release Line

The plugin source in this repository is currently `0.0.16` on the `v0.0.16` branch. Starting with `v0.0.16`, the sibling plugins (`netbox-pbs`, `netbox-ceph`, `netbox-pdm`, `netbox-packer`) have been extracted to their own standalone repositories under [@emersonfelipesp](https://github.com/emersonfelipesp); each declares `netbox-proxbox>=0.0.16` as an install-time dependency. The `v0.0.17` line continues in those repositories.

## Highlights By Version

| Version | Summary |
|---------|---------|
| `0.0.17` (split out) | The `0.0.17` line is no longer shipped from this monorepo. Sibling plugins now live in standalone repositories: [`netbox-pbs`](https://github.com/emersonfelipesp/netbox-pbs), [`netbox-ceph`](https://github.com/emersonfelipesp/netbox-ceph), [`netbox-pdm`](https://github.com/emersonfelipesp/netbox-pdm), and [`netbox-packer`](https://github.com/emersonfelipesp/netbox-packer). Each declares `netbox-proxbox>=0.0.16` as a dependency and reuses the shared `proxbox-api` backend. |
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
