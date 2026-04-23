# Version 0.0.12

## Summary

Version 0.0.12 adds native `VirtualMachineType` support for NetBox 4.6, a new Clusters list page and API endpoint, site and tenant fields on `ProxmoxEndpoint`, and several stability and compatibility fixes. It targets NetBox `4.6.0-beta1` and is the first release to ship with proxbox-api `v0.0.8.post1`.

## Compatibility

| NetBox         | netbox-proxbox | proxbox-api   | netbox-sdk   | proxmox-sdk    |
|----------------|----------------|---------------|--------------|----------------|
| >=4.6.0-beta1  | v0.0.12        | v0.0.8.post1  | v0.0.7.post6 | v0.0.3.post1   |

NetBox compatibility range: `4.6.0-beta1` – `4.6.99` (verified on `v4.6.0-beta1`).

---

## New Features

### Native VirtualMachineType Support

Proxbox now syncs Proxmox guest type (QEMU / LXC) into NetBox's native `VirtualMachineType` field introduced in NetBox 4.6. Previously the type was stored in a custom field; it is now written directly to the core model.

### Clusters Resource List Page and API

A new **Clusters** page under Plugins → Proxbox lists all synced `ProxmoxCluster` objects with filterable columns. A matching REST API endpoint is exposed at `/api/plugins/proxbox/clusters/` with full read and filter support.

### Site and Tenant on ProxmoxEndpoint

`ProxmoxEndpoint` gains optional `site` and `tenant` foreign-key fields, letting operators associate a Proxmox environment with a NetBox site or tenant for grouping and access-control purposes.

---

## Bug Fixes

| Area | Fix |
|------|-----|
| NetBox 4.6 compat | Replaced `site` attribute access with `_site` to satisfy `CachedScopeMixin` in NetBox 4.6 |
| API serializers | Replaced all removed NetBox nested serializer classes with `nested=True` pattern |
| API views | Exposed nodes, clusters, and virtual-machines at correct top-level API paths |
| API views | Added device status and Proxmox metrics to `NodesAPIView` response |
| Models | Widened `VMTaskHistory.status` and `VMTaskHistory.exitstatus` to `TextField` to accommodate long Proxmox task status strings |
| Migrations | Made migration `0032` idempotent with `ADD COLUMN IF NOT EXISTS` |
| Migrations | Removed obsolete `0032_merge` migration; renumbered `0031→0032` for timeout/retry fields |
| N+1 queries | Fixed N+1 `COUNT` queries in cluster sync by batching node lookups |
| VM type | Deduplicated `vm_type` resolution to avoid redundant Proxmox API calls |
| CI | Bumped NetBox image to `v4.6.0-beta1`; pinned proxbox-api to PyPI release instead of editable local source |
| Tests | Added SSE schema contract tests; pre-create custom fields before device sync |

---

## Database Migrations

Migration `0032` adds timeout and retry fields to `ProxboxSyncJob`. It is idempotent and safe to run on existing databases.

```bash
python manage.py migrate netbox_proxbox
```

---

## API Changes

| Route | Notes |
|-------|-------|
| `/api/plugins/proxbox/clusters/` | New — full read and filter support for `ProxmoxCluster` |
| `/api/plugins/proxbox/nodes/` | Now includes device status and Proxmox resource metrics |
| `/api/plugins/proxbox/virtual-machines/` | Now exposed at top-level path |
