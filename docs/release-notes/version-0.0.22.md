# Version 0.0.22

netbox-proxbox `0.0.22` pairs with the `proxbox-api 0.0.19.post4`
backend release, the `proxmox-sdk 0.0.12` Proxmox SDK, and
`netbox-sdk 0.0.10`. NetBox compatibility is unchanged: `4.5.8` through
`4.6.99` (validated against `4.5.8`, `4.5.9`, and `4.6.0` through `4.6.4`).

Current pairing: netbox-proxbox 0.0.22 <-> proxbox-api 0.0.19.post4 <-> proxmox-sdk 0.0.12 <-> netbox-sdk 0.0.10.

## Highlights

- **Per-endpoint access methods.** `ProxmoxEndpoint.access_methods` adds the
  API-only vs API+SSH transport gate with choices `api` and `api_ssh`. New
  endpoints default to API-only, existing endpoint rows are backfilled to
  API+SSH during the migration to preserve existing terminal behavior, and the
  selected value is pushed to `proxbox-api` in the backend endpoint payload.
- **SSH operator workflow.** The Proxmox endpoint form now exposes the
  Proxmox-side write-permission toggle, `ssh_credential_source` selection for
  dedicated vs reused endpoint credentials, and a **Fetch host key** button
  that asks the backend to scan the endpoint host key and fill the pinned
  SHA-256 fingerprint field.
- **Tenant and endpoint operations.** Proxmox endpoints support tenant
  allowlists for NMS Cloud endpoint visibility, cluster-tenant inheritance for
  synced VMs, and bulk enable/disable actions that update only the local
  `enabled` flag without triggering backend or Proxmox calls.
- **PDM, SDN, and certification refresh.** PDM endpoint detail pages and Sync
  Now remote discovery are available when the companion PDM plugin is present.
  Optional SDN inventory and sync controls are included, with migration fixes
  for NetBox 4.5 compatibility. The E2E and screenshot matrices now certify
  NetBox `4.6.4` while keeping the declared `4.5.8` through `4.6.99` range.
- **REST API and safety hardening.** The plugin exposes REST API viewsets for
  PBS endpoints, PDM endpoints/remotes, `DeletionRequest`, and
  `ProxmoxApplyJob`; `DeletionRequest` and `ProxmoxApplyJob` remain read-only
  audit surfaces. Firecracker serializer tenant handling was tightened so
  malformed tenant payloads are rejected earlier.
- **UI and documentation hardening.** Disabled endpoint status cards no longer
  poll live status, paginator markup is rendered correctly on plugin list
  pages, the homepage navigation highlight is scoped to the real home route,
  and agent/developer docs record the safety contracts for endpoint access,
  credentials, and destructive operations.

## Compatibility

| NetBox  | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.22 | v0.0.19.post4 | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.21 | v0.0.18.post5 | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.20.post3 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20.post2 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20.post1 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |

`proxbox-api` is not a Python dependency of this plugin; the services
communicate over HTTP/SSE/WebSocket. Install the matching
`proxbox-api 0.0.19.post4` backend separately. This release supports NetBox
`4.5.8` through `4.6.99` and requires Python `>=3.12`.

## Upgrade Notes

- Upgrade the plugin to `netbox-proxbox 0.0.22` and the backend to
  `proxbox-api 0.0.19.post4`.
- Use `proxmox-sdk 0.0.12` and `netbox-sdk 0.0.10` in the paired
  backend environment.
- Run the normal NetBox plugin upgrade flow: install the package, run
  `python manage.py migrate netbox_proxbox`, collect static files, and restart
  NetBox/RQ workers.
- Review `ProxmoxEndpoint.access_methods` after migration. Existing endpoints
  are backfilled to `api_ssh` to avoid disabling previously available SSH
  terminal access; newly created endpoints default to `api`.
- Review the Proxmox endpoint **Allow Proxmox-side writes** toggle separately
  from `access_methods`. The access method controls transport availability;
  write permission remains the operational trust boundary.
