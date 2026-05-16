# Version 0.0.15.post2

Version `0.0.15.post2` is a post-release patch on stable `0.0.15`. It pairs with backend `proxbox-api 0.0.11.post2`, adds the `build-pve-template` REST action on the proxmox endpoint viewset, and is the foundation cut before the plugin-side Proxmox Datacenter Manager (PDM) work tracked in [#449](https://github.com/emersonfelipesp/netbox-proxbox/issues/449).

## Changes

- **Build PVE template action** — `ProxmoxEndpointViewSet` exposes a `build-pve-template` REST action so operators can build PVE-installer cloud-init templates against an endpoint without leaving NetBox. Backed by the new `/cloud/templates/pve` route added in `proxbox-api 0.0.11.post2` (#452).
- **Backend pickup of proxmox-sdk 0.0.5.post1** — Paired backend lifts the `proxmox-sdk` pin from `0.0.4.post3` to `0.0.5.post1`, picking up the new `proxmox_sdk.pdm` subpackage (full PDM SDK + CLI + TUI + mock server). No new plugin-side PDM surface ships in this release; the model + UI work lands incrementally behind it per [#449](https://github.com/emersonfelipesp/netbox-proxbox/issues/449).
- Carries forward every fix shipped in `v0.0.15.post1` (VM/LXC resource API pagination, PVE 9.x HA rules, cloud template PUT/PATCH, `ProxmoxEndpointBulkDeleteView`, `NetBoxModelSerializer` MRO delegation, full-update stage resilience).

## Compatibility

No NetBox compatibility rotation ships in this patch release.
NetBox compatibility range: `4.5.8` - `4.6.99` (unchanged).

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|--------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.15.post2 | v0.0.11.post2 | v0.0.8.post1 | v0.0.5.post1 |
| >=4.5.8 | v0.0.15.post1 | v0.0.11.post1 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8 | v0.0.15 | v0.0.11 | v0.0.8.post1 | v0.0.3.post1 |
