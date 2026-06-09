# `netbox_proxbox.views.endpoints`

This directory contains NetBox generic model views for the three endpoint models.

## Files And Ownership

- [`proxmox.py`](./proxmox.py): list/detail/edit/delete, bulk import, export, and quick-add-token views for `ProxmoxEndpoint`.
- [`proxmox_sync_now.py`](./proxmox_sync_now.py): POST-only `ProxmoxEndpoint` action that queues an immediate full `ProxboxSyncJob` scoped to the endpoint being viewed.
- [`proxmox_export.py`](./proxmox_export.py): CSV/JSON/YAML export fieldname and serializer helpers for `ProxmoxEndpoint`.
- [`netbox.py`](./netbox.py): list/detail/edit/delete, bulk import, export, and quick-add-token views for `NetBoxEndpoint`.
- [`netbox_export.py`](./netbox_export.py): CSV/JSON/YAML export fieldname and serializer helpers for `NetBoxEndpoint`.
- [`fastapi.py`](./fastapi.py): list/detail/edit/delete, bulk import, export, quick-add-token views for `FastAPIEndpoint`, plus the OpenAPI tab that renders cached schema metadata.
- [`fastapi_export.py`](./fastapi_export.py): CSV/JSON/YAML export fieldname and serializer helpers for `FastAPIEndpoint`.
- [`__init__.py`](./__init__.py): re-exports endpoint view classes.

## Export Views

All three endpoint types expose an `ExportView` at `{model}_export` that supports CSV, JSON, and YAML output in two modes:

- **Safe export** (GET or POST without `include_sensitive=true`): Excludes all credential fields. Anyone with `view` permission on the model can download.
- **Sensitive export** (POST with `include_sensitive=true`): Includes credential fields in plain text. The requester must POST a valid NetBox API token to prove identity.

### Sensitive export token validation

`_validate_sensitive_export_token()` supports three input modes, selected by the `token_version` POST field:

| Mode | POST fields | Header constructed |
|---|---|---|
| `v1` (dropdown) | `token_id` (integer PK) | `Token <plaintext from DB>` |
| `v1` (manual) | `v1_manual_token` (raw value) | `Token <value>` |
| `v2` | `token_key` + `token_secret` | `Bearer <key>.<secret>` |
| Fallback (empty) | `netbox_token` | `Token <value>` or `Bearer <value>` |

The constructed header is placed into `request.META["HTTP_AUTHORIZATION"]` and authenticated with `TokenAuthentication`. The token user must also hold `view` permission on the exported model.

### Quick-add token views

Each endpoint type registers a `QuickAddTokenView` at `{model}_quick_add_token`. A POST to this endpoint creates a temporary v1 `Token` object under the current user's account and returns its PK, display string, and plaintext once in JSON. The export modal UI uses this to create a throwaway token when the user has no existing v1 token handy.

### Export helper modules

Each `*_export.py` file provides two functions used by the `ExportView`:

- `_*_export_fieldnames(include_sensitive)` — returns the ordered tuple of column names; credential columns appear only when `include_sensitive=True`.
- `_serialize_*_endpoint(endpoint, include_sensitive)` — serializes one model instance to a `dict[str, str]` row for CSV, JSON, or YAML output.

**Sensitive columns by model:**

| Model | Sensitive fields |
|---|---|
| `ProxmoxEndpoint` | `password`, `token_value` |
| `NetBoxEndpoint` | `token_key`, `token_secret` |
| `FastAPIEndpoint` | `token` |

## Bulk Import Views

All three endpoint types override `create_and_update_objects()` to strip any `id` column before NetBox processes the records. This makes CSV exports from one NetBox instance importable into another without "Object with ID N does not exist" errors; PKs are auto-assigned on create.

### Singleton import confirmation

`NetBoxEndpoint` and `FastAPIEndpoint` are singletons — the backend and dashboard always use the first row of each. Their `BulkImportView` subclasses enforce this constraint:

1. On the initial import POST, if a record already exists and `confirm_override` is not set, the view renders `singleton_import_confirm.html` with the raw POST data preserved in hidden fields.
2. The user reviews the existing record summary and clicks **Override existing** (adds `confirm_override=true` and re-submits) or **Cancel**.
3. On the confirmed POST, `create_and_update_objects()` deletes the existing singleton, then calls `super()` to create the replacement.

`ProxmoxEndpoint` allows multiple rows and has no confirmation step.

## IP Address Auto-Creation on Import

All three import forms use a plain `forms.CharField` for `ip_address` backed by a `clean_ip_address()` method that calls `IPAddress.objects.get_or_create(address=raw)`. This means a CIDR string that does not yet exist in IPAM is silently created at import time rather than causing a validation error — the same behavior Proxmox endpoints have had since an earlier fix.

## Dependencies

- Inbound: `views/__init__.py` imports and re-exports these classes, and `urls.py` mounts them via `get_model_urls(...)`.
- Outbound: matching models, tables, filtersets, forms, and the `*_export.py` helpers in this directory.

## Notes

- The export JS (token version toggle, dropdown population, quick-add, copy-to-clipboard) is inlined as an IIFE in each `*endpoint_list.html` template rather than loaded as an external `.js` file. This avoids requiring `collectstatic` for the modal to work.
- The ProxmoxEndpoint detail page exposes **Sync Now** through `proxmox_sync_now.py`; it requires the shared Proxbox sync enqueue permission, uses a CSRF-protected POST, refuses disabled endpoints, and passes the viewed endpoint PK in `proxmox_endpoint_ids`.
- Changes to list columns, validation, or field presentation typically happen outside this directory unless the view wiring itself changes.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
