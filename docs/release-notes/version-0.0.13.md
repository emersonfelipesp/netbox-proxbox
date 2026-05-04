# Version 0.0.13

## Summary

Version 0.0.13 surfaces every `overwrite_*` flag in the plugin UI, adds a per-endpoint **Settings** tab on `ProxmoxEndpoint` detail, and enforces VM-sync device flags end-to-end through the proxbox-api stream. It pairs with `proxbox-api==0.0.9` and certifies NetBox `v4.6.0-beta2`.

`0.0.13.post1` is a packaging follow-up that pins `proxbox-api==0.0.9`, certifies NetBox `v4.6.0-beta2` against the published Docker Hub image, and re-publishes the documentation site with the endpoint import/export feature page surfaced.

`0.0.13.post2` re-pins `proxbox-api==0.0.9.post1` across `pyproject.toml`, the e2e and docs-screenshots workflows, and the nightly contract job. No runtime behavior change — only the compatibility matrix and the pinned proxbox-api version move forward.

`0.0.13.post4` re-pins `proxbox-api==0.0.9.post2`. The `0.0.9.post1` pairing in `0.0.13.post2` shipped with a `create_storages()` `TypeError` regression in `proxbox_api.app.full_update`; `0.0.9.post2` fixes the import to use the service-level `create_storages` (which accepts the `overwrite_flags` kwarg). This line is also certified for NetBox `4.5.8` and `4.5.9` for issue #349. (`0.0.13.post3` was tagged but its publish run failed validate-testpypi due to a stale `uv.lock`, so it never reached PyPI; `.post4` is the working release.)

## Compatibility

| NetBox         | netbox-proxbox  | proxbox-api  | netbox-sdk   | proxmox-sdk    |
|----------------|-----------------|--------------|--------------|----------------|
| >=4.5.8         | v0.0.13.post4   | v0.0.9.post2 | v0.0.7.post6 | v0.0.3.post1   |
| >=4.6.0-beta2  | v0.0.13.post2   | v0.0.9.post1 | v0.0.7.post6 | v0.0.3.post1   |
| >=4.6.0-beta2  | v0.0.13.post1   | v0.0.9       | v0.0.7.post6 | v0.0.3.post1   |
| >=4.6.0-beta1  | v0.0.13         | v0.0.9       | v0.0.7.post6 | v0.0.3.post1   |

NetBox compatibility range: `4.5.8` – `4.6.99`.

---

## New Features

### Per-Endpoint Settings Tab

`ProxmoxEndpoint` detail pages gain a dedicated **Settings** tab that exposes every per-endpoint overwrite control alongside global plugin defaults. The tab is wired through `register_model_view` and reuses the existing `ConditionalLoginRequiredMixin` permission flow. See `netbox_proxbox/views/settings.py`.

### All `overwrite_*` Flags Surfaced

Every `overwrite_*` column on `ProxmoxEndpoint` and `ProxboxPluginSettings` is now configurable from the UI with tri-state semantics:

- **Use plugin default** (None) — fall back to the global `ProxboxPluginSettings` value.
- **Always overwrite** (True) — the sync overwrites the NetBox value.
- **Never overwrite** (False) — preserve the existing NetBox value.

The 16 new per-endpoint columns ship in migration `0035_overwrite_fields_expansion`. See [`Sync Overwrite Flags`](../configuration/sync-overwrite-flags.md) for the full flag matrix.

### VM-Sync Device Flag Enforcement

When a VM sync runs, the per-endpoint `overwrite_device_*` flags are now read on the plugin side and forwarded as query parameters to the proxbox-api `full-update/stream` endpoint. The backend honors them when reconciling Proxmox node devices into NetBox. See PR #342.

### Endpoint Import/Export Feature Page

The CSV/JSON/YAML import and export pages for `ProxmoxEndpoint`, `NetBoxEndpoint`, and `FastAPIEndpoint` are now documented as a first-class feature. See [`Endpoint Import/Export`](../features/endpoint-import-export.md).

### Merge Semantics for `overwrite_vm_tags`

The `overwrite_vm_tags` form label and help text now make clear that the flag controls **merge vs replace** semantics for VM tags, not append-only behavior.

---

## Bug Fixes

| Area | Fix |
|------|-----|
| Sync | `_ensure_device` now resolves the existing NetBox device instead of creating a duplicate when a Proxmox node maps to an existing record |
| Exception handling | Narrowed broad `except Exception` clauses in `views/sync.py` enqueue paths and `templatetags/proxbox_tags.py` |
| CI | Reverted `NETBOX_IMAGE` to `v4.6.0-beta1` temporarily when `beta2` was unavailable on Docker Hub; restored to `v4.6.0-beta2` in `0.0.13.post1` |
| CI | Rebase before push in `docs-screenshots.yml` to avoid rejection when `develop` moves during a screenshot run |
| Settings | All `overwrite_vm_tags` references updated to reflect merge semantics |

---

## Database Migrations

- `0033_pluginsettings_controlled_fields` — adds the global `overwrite_*` defaults to `ProxboxPluginSettings`.
- `0034_proxmoxendpoint_overwrite_fields` — adds the initial set of per-endpoint `overwrite_*` columns to `ProxmoxEndpoint`.
- `0035_overwrite_fields_expansion` — adds the remaining 16 per-endpoint `overwrite_*` columns so every flag has tri-state semantics.

```bash
python manage.py migrate netbox_proxbox
```

---

## CI / Release Pipeline

- `e2e-docker.yml` certifies `netboxcommunity/netbox:v4.5.8`, `netboxcommunity/netbox:v4.5.9`, and `netboxcommunity/netbox:v4.6.0-beta2`; `docs-screenshots.yml` continues to use `v4.6.0-beta2`.
- The release pipeline gains a `dependency_mode` input (`dev` vs `published`) so pre-publish E2E runs against the proxbox-api source while post-publish E2E runs against the released Docker Hub image.
- `e2e-docker.yml` and `docs-screenshots.yml` pin `PROXBOX_API_RELEASE_VERSION=0.0.9`.
