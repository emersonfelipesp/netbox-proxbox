# Endpoint Import / Export

All three endpoint types (Proxmox, NetBox, FastAPI) support bulk import and export from the list view.

---

## Export

From the endpoint list page, click **Export** to open a dropdown:

| Option | Output |
|---|---|
| Export CSV | `.csv` file, no credentials |
| Export JSON | `.json` file, no credentials |
| Export YAML | `.yaml` file, no credentials |

Safe exports omit all credential fields (`password`, `token_value`, `token_key`, `token_secret`, `token`) — they are safe to share or commit.

### Export with secrets

Click **Export with secrets** to open the export modal. This produces the same formats but includes credential fields in plain text.

Because credentials are sensitive, you must authenticate with a NetBox API token before the download is served. The modal provides three input modes:

**v1 token — select existing**
: Choose a token from the dropdown (populated from `/api/users/tokens/?version=1`). If you have no v1 token, use **Quick add token** to create a temporary one. The plaintext appears once in the modal — copy it before closing.

**v1 token — enter manually**
: Paste a 40-character v1 token value directly. Useful when you have the token string but it is not in the current NetBox instance.

**v2 token**
: Provide the token key (starts with `nbt_`) and the token secret separately.

After export, delete any token created solely for this purpose.

---

## Import

Click **Import** to reach the standard NetBox bulk-import form. Supported formats: CSV, JSON, YAML.

### Cross-instance imports

CSV exported from one NetBox instance includes an `id` column with local PKs. The import views strip this column before processing, so rows are always created with fresh auto-assigned PKs. You do not need to remove the `id` column manually.

IP addresses in the `ip_address` column are looked up or created automatically. If the CIDR string does not exist in IPAM it is created at import time — you do not need to pre-populate IP Address objects before importing endpoints.

### NetBox and FastAPI singleton import

`NetBoxEndpoint` and `FastAPIEndpoint` are singletons — each should have at most one record, because the backend proxy and dashboard always use the first row.

If you import when a record already exists, the import is intercepted and a confirmation page is shown:

1. The existing record's name, domain, IP address, and port are displayed.
2. Click **Override existing** to delete the current record and create the imported one.
3. Click **Cancel** to return to the list without making any changes.

Proxmox endpoints allow multiple rows and have no such confirmation step.

---

## Sensitive fields by endpoint type

| Endpoint | Safe columns | Sensitive columns (export-with-secrets only) |
|---|---|---|
| ProxmoxEndpoint | All others incl. `token_name` | `password`, `token_value` |
| NetBoxEndpoint | All others incl. `token` (FK key) | `token_key`, `token_secret` |
| FastAPIEndpoint | All others | `token` |

---

## Permissions

| Action | Required permission |
|---|---|
| Safe export | `netbox_proxbox.view_{model}` |
| Sensitive export | `netbox_proxbox.view_{model}` + valid NetBox API token |
| Import | `netbox_proxbox.add_{model}` |
| Quick add token | `users.add_token` |
