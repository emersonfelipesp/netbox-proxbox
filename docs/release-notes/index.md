# Release Notes

This section tracks the release line represented by this repository and keeps older historical placeholders explicit.

## Current Release Line

The plugin source in this repository is currently `0.0.13.post3`.

## Highlights By Version

| Version | Summary |
|---------|---------|
| `0.0.13.post3` | Re-pins `proxbox-api==0.0.9.post2` (fixes `create_storages()` `TypeError` regression in `0.0.9.post1`); no runtime behavior change |
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
