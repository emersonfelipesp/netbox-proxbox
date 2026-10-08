# Version 0.0.29.post2

## Summary

This maintenance release adds a system check that explains a Proxbox
synchronization outage seen after upgrading to 0.0.29. It adds no database
migration and changes no runtime behavior.

## Release identity

The package and plugin source both identify this maintenance release as
`0.0.29.post2`.

## Backend token sensitive-data access

0.0.29 returns the plugin encryption key from the settings runtime endpoint
only to an active superuser or a user with an explicit sensitive-data grant.
proxbox-api reads that key with the token configured on the enabled NetBox
endpoint. If proxbox-api relies on the plugin key instead of its own key and
that token's user has no grant, every Proxbox synchronization fails with HTTP
503.

The new system check `netbox_proxbox.W107` (`manage.py check --database
default`) names each enabled NetBox endpoint whose token user cannot receive the
key. Prefer provisioning proxbox-api's own encryption key. If it must keep
using the plugin key, an active superuser can create the grant through
`POST /api/plugins/proxbox/sensitive-data-access/` with the user ID and
`can_access_sensitive_data: true`. The grant is deliberately not created by a migration, because endpoint
configuration alone does not prove that a user should hold global
sensitive-data access.

## Upgrade

Upgrade from 0.0.29 or 0.0.29.post1 with the usual package upgrade and
`manage.py migrate`; this release adds no migration. Then run
`manage.py check --database default` and resolve any `netbox_proxbox.W107`
warning before the next synchronization.

Use proxbox-api 0.0.27.post2 or later: earlier backends could also block the
plugin key after the plugin's per-sync endpoint push until they restarted.

## Compatibility baseline

The support contract was NetBox `4.5.8` through `4.7.0` GA when this maintenance
source was cut. Current source widens the plugin ceiling to `4.7.99` so NetBox
4.7 patch releases such as `4.7.2` load without a plugin update. This
maintenance source retains the preceding backend pairing.

Current backend-runtime pairing: netbox-proxbox 0.0.29.post2 <-> proxbox-api 0.0.23.post3 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.29.post2 | v0.0.23.post3 | v0.0.13 | v0.0.15 |
