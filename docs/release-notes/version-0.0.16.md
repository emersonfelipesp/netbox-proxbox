# Version 0.0.16

Version `0.0.16` is a patch release for the proxbox VM/LXC resource API.

## Fixes

- `/api/plugins/proxbox/resources/virtual-machines/` no longer slices proxbox-tagged VM IDs to the first 100 before filtering by QEMU type.
- `/api/plugins/proxbox/resources/lxc-containers/` uses the same corrected order of operations for LXC filtering.
- Both endpoints now order results by VM name and honor DRF `limit` / `offset` query parameters while preserving full unpaginated responses when no pagination parameters are supplied.

## Compatibility

No NetBox compatibility or backend pairing rotation ships in this patch release.
NetBox compatibility range: `4.5.8` - `4.6.99` (unchanged).

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|--------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.16 | v0.0.11 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8 | v0.0.15 | v0.0.11 | v0.0.8.post1 | v0.0.3.post1 |
