# Version 0.0.17

## Summary

Version `0.0.17` introduces a sibling **read-only Ceph plugin** packaged as
`netbox-ceph 0.0.1` from this repository. It is the third integration
direction tracked by the Proxbox project, after read-only Proxmox →
NetBox reflection (`netbox-proxbox`) and opt-in NetBox → Proxmox intent
(also in `netbox-proxbox`, shipped in `0.0.16`). Ceph inventory is
**Proxmox-managed only** in v1: no direct Ceph Dashboard / Prometheus / RGW
/ RBD / external-cluster integration, and no NetBox → Ceph write path.

Tracking issues:

- Parent: [#424](https://github.com/emersonfelipesp/netbox-proxbox/issues/424)
- Sub-issues:
  [`#11` proxmox-sdk](https://github.com/emersonfelipesp/proxmox-sdk/issues/11),
  [`#92` proxbox-api](https://github.com/emersonfelipesp/proxbox-api/issues/92),
  [`#428` scaffold](https://github.com/emersonfelipesp/netbox-proxbox/issues/428),
  [`#430` sync job + HTTP client](https://github.com/emersonfelipesp/netbox-proxbox/issues/430),
  [`#429` docs + release + smoke](https://github.com/emersonfelipesp/netbox-proxbox/issues/429).

## What's new

### `netbox-ceph` sibling plugin

- New wheel `netbox-ceph 0.0.1` declared in `netbox_ceph/pyproject.toml`,
  installed alongside `netbox-proxbox` (`required_plugins = ["netbox_proxbox"]`).
- Nine Django models — `CephPluginSettings` (singleton), `CephCluster`,
  `CephDaemon`, `CephOSD`, `CephPool`, `CephFilesystem`, `CephCrushRule`,
  `CephFlag`, `CephHealthCheck` — with permissive `payload` JSON fields so
  the UI can render upstream data without lossy serialization.
- Initial migration `0001_initial` depends on `netbox_proxbox` + `extras`
  and namespaces every `UniqueConstraint` under `netbox_ceph_*`.
- `NetBoxModelViewSet` per model with
  `http_method_names = ("get", "head", "options")` mounted at
  `/api/plugins/ceph/`; generic `ObjectListView` / `ObjectView` per model
  with `register_model_view`; filter-only `NetBoxModelFilterSetForm` per
  model with lazy `ProxmoxEndpoint` queryset binding; child tabs on
  `CephCluster` for daemons, OSDs, and pools; plugin home view.

### Branch-aware `CephSyncJob`

- `netbox_ceph.jobs.CephSyncJob` runs on NetBox's `default` RQ queue with
  a `7200s` `job_timeout`, the same long-budget convention as
  `ProxboxSyncJob`.
- `netbox_ceph.services.http_client` calls `proxbox-api`'s `/ceph/status`
  and `/ceph/sync/{status,daemons,osds,pools,filesystems,crush,flags,full}`
  plain JSON GETs; reuses
  `netbox_proxbox.services.backend_context.get_fastapi_request_context` so
  no new authentication or endpoint-resolution path is introduced.
- `netbox_ceph.services.branch_lifecycle` re-exports the netbox-proxbox
  branch helpers and adds `branching_enabled_settings()` reading
  `CephPluginSettings.get_solo()` with defaults `prefix="ceph-sync"` and
  `on_conflict="fail"`. When branching is unavailable or disabled, the job
  runs against `main`.
- Per-resource progress is persisted under `job.data["ceph_sync"]` as a
  `{params, runtime_seconds, response: {stages: [...]}}` structure mirroring
  the Proxbox sync job's `proxbox_sync` key.
- On error, the branch is left open for inspection; on success with a
  branch, `merge_branch` is called.

### Documentation

- New feature doc: [Features → Ceph (Proxmox-managed)](../features/ceph.md).
- New installation doc:
  [Installation → Ceph Plugin](../installation/ceph-plugin.md).
- Top-level docs nav entries for both pages.

## Compatibility

- NetBox: `4.5.8` – `4.6.99` (unchanged from `0.0.16`).
- Paired backend: `proxbox-api >= 0.0.11` (same floor as `0.0.16`'s HA
  surface). The `/ceph/*` routes ship in the backend release that
  introduced the HA REST shim; no further backend bump is required.
- Companion Proxmox SDK: `proxmox-sdk` with `proxmox_sdk/ceph/` facade.

## Out of scope for v1

Deferred to future releases:

- Direct Ceph Dashboard API integration.
- Prometheus metric ingestion.
- RGW / S3 bucket inventory.
- RBD image inventory.
- External non-Proxmox Ceph clusters.
- Any NetBox → Ceph write operation (pool create, OSD `in/out`, daemon
  start/stop, flag mutation, CephFS destroy, etc.).

## Verification

- `uv run ruff check .` — clean.
- `uv run pytest tests/test_ceph_*.py -q` — 25 passed; AST/source-contract
  pattern (no Django bootstrap), matching the repo convention.
- Repo-wide collection: 794 tests (769 prior + 25 new), no collection
  errors.
- Live `proxbox-api` `/ceph/status` route returns `HTTP 401` (auth-gated,
  i.e. registered) from the dev endpoint at
  `http://10.0.30.207:8000/ceph/status`.
