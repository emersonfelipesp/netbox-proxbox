# Version 0.0.19

## Summary

Version `0.0.19` fixes database and integration compatibility issues between
the plugin and the companion `proxbox-api` backend, resolves a FastAPI
endpoint token-drift regression, and adds bridging properties to the
`PBSEndpoint` and `PDMEndpoint` Django models.

It pairs with backend [`proxbox-api 0.0.16`](https://github.com/emersonfelipesp/proxbox-api).

The NetBox compatibility range remains `4.5.8` – `4.6.99`. No new Django
migrations are required; run `manage.py migrate netbox_proxbox` only if
upgrading from a pre-`0.0.18` baseline.

## What's New In The Plugin

- **FastAPI endpoint token drift fix.** `FastAPIEndpoint.save()` now detects
  explicit token changes on existing rows and calls
  `_register_key_with_backend(skip_bootstrap_check=True)` so operators can
  recover from a proxbox-api key rotation without direct database surgery.
- **PBS/PDM `host` compatibility property.** `PBSEndpoint` and `PDMEndpoint`
  now expose a `host` property (`domain or ip or ""`) that bridges the field-
  name difference with `proxbox-api`'s SQLite `PBSEndpoint.host` column.
- **PBS/PDM `timeout_seconds` compatibility property.** Both models now expose
  a `timeout_seconds` property (`timeout or 30`) to match the proxbox-api
  SQLite column name.

## What's New In The Backend (`proxbox-api 0.0.16`)

The plugin requires `proxbox-api >= 0.0.16`. Key fixes:

- `allow_writes` exposed in `ProxmoxEndpointCreate`, `ProxmoxEndpointUpdate`,
  and `ProxmoxEndpointPublic` — was permanently locked to `False` with no API
  path to enable VM operational verbs.
- `verify_ssl` migration guards added to `_migrate_proxmox_endpoint_columns()`,
  `_migrate_pbs_endpoint_columns()`, and `_migrate_pdm_endpoint_columns()` so
  upgraded deployments always have a defined SSL-verification column.
- `PBSEndpointCreate.verify_ssl` default aligned to `False` (matching the
  `PBSEndpoint` SQLModel default for self-signed cert environments).
- `APIKeyAuthMiddleware` now offloads `bcrypt.checkpw()` to the thread pool via
  `asyncio.to_thread()` — was blocking the event loop on every request.

## Compatibility

| NetBox   | netbox-proxbox | proxbox-api | netbox-sdk     | proxmox-sdk    |
|----------|----------------|-------------|----------------|----------------|
| >=4.5.8  | v0.0.19 | v0.0.16 | v0.0.8.post1 | v0.0.9 |
| >=4.5.8  | v0.0.18 | v0.0.14 | v0.0.8.post1 | v0.0.3.post1 |

NetBox compatibility range: `4.5.8` – `4.6.99` (unchanged). Certified
simultaneously against NetBox `v4.5.8`, `v4.5.9`, `v4.6.0`, and `v4.6.1`.

## Upgrade Notes

- No new Django migrations — no `manage.py migrate` required unless upgrading
  from a pre-`0.0.18` baseline.
- **Upgrade proxbox-api to `0.0.16`** before the plugin — the `allow_writes`
  and `verify_ssl` migration guard fixes are in the backend.
- Restart the NetBox WSGI process after upgrade and static-file collection.
