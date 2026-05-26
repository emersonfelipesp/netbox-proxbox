# Version 0.0.18.post1

This post release prepares `netbox-proxbox` for NetBox Plugin Certification
and fixes a migration gap in the v0.0.18 endpoint schema.

## Changed

- Added PyPI project URLs, classifiers, and explicit Apache-2.0 license-file
  metadata.
- Added certification evidence docs and a family-level application packet.
- Documented the certification target release for `netbox-proxbox`,
  `netbox-pbs`, `netbox-pdm`, `netbox-ceph`, and `netbox-packer`.
- Updated public repository metadata in MkDocs.

## Fixed

- Added migration `0045_repair_pbs_pdm_endpoint_enabled` to repair existing
  v0.0.18 databases where `PBSEndpoint` and `PDMEndpoint` were missing the
  shared endpoint `enabled` column. The missing column could surface as a
  PostgreSQL `column netbox_proxbox_pbsendpoint.enabled does not exist` error
  during unrelated protected-object checks, including IP address deletion.

## Compatibility

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
| --- | --- | --- | --- | --- |
| >=4.5.8 | v0.0.18.post1 | v0.0.14 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8 | v0.0.18 | v0.0.14 | v0.0.8.post1 | v0.0.3.post1 |

No runtime sync behavior changed from `0.0.18`. Run
`python manage.py migrate netbox_proxbox` after upgrading so the repair
migration can add the missing PBS/PDM endpoint columns when needed.
