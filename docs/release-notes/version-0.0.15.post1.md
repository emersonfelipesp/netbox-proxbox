# Version 0.0.15.post1

Version `0.0.15.post1` is a post-release patch on stable `0.0.15`. It paires with backend `proxbox-api 0.0.11.post1` and ships several read-only-path fixes and resilience improvements.

## Fixes

- **VM/LXC resource API pagination** — `/api/plugins/proxbox/resources/virtual-machines/` and `/api/plugins/proxbox/resources/lxc-containers/` filter the full proxbox-tagged VM set before applying optional `limit` / `offset` pagination (fixes the 100-object truncation regression). Both endpoints order by VM name and preserve fully-unpaginated responses when no pagination parameters are supplied.
- **PVE 9.x HA rules in the cluster HA dashboard** — `ha.html` adds a "HA Rules (PVE 9.x)" card that conditionally renders when `summary.rules` is non-empty, populated by the new `rules` field on `proxbox-api`'s `/proxmox/cluster/ha/summary` response. Backward compatible — the card is hidden on pre-9.x clusters that return an empty rules list. Fixes #111.
- **Cloud image template updates** — REST API now accepts PUT/PATCH on cloud image templates via the `CloudImageTemplateSerializer` delegation through `NetBoxModelSerializer` (#444).
- **Bulk-delete fix** — `ProxmoxEndpointBulkDeleteView` is now wired in `urls.py` so the bulk-delete action from the proxmox endpoint list view no longer returns 404 (#446).
- **Serializer MRO** — `fix(api): delegate create/update through NetBoxModelSerializer MRO` ensures create/update payloads flow through the documented serializer pipeline.
- **Full-update resilience** — `fix(sync): skip optional stages on failure instead of aborting full sync` (#448): backups, snapshots, and task history can now fail individually without aborting the whole sync. Required stages still surface errors.

## Compatibility

No NetBox compatibility rotation ships in this patch release.
NetBox compatibility range: `4.5.8` - `4.6.99` (unchanged).

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|--------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.15.post1 | v0.0.11.post1 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8 | v0.0.15 | v0.0.11 | v0.0.8.post1 | v0.0.3.post1 |
