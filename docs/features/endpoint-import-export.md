# Endpoint Import / Export

## Table of Contents

- [Export](#export)
- [Import](#import)
- [Sensitive fields by endpoint type](#sensitive-fields-by-endpoint-type)
- [Permissions](#permissions)
- [Sensitive-data grants](#sensitive-data-grants)

All three endpoint types (Proxmox, NetBox, FastAPI) support bulk import and export from the list view.

---

## Export

From the endpoint list page, click **Export** to open a dropdown:

| Option | Output |
|---|---|
| Export CSV | `.csv` file, no credentials |
| Export JSON | `.json` file, no credentials |
| Export YAML | `.yaml` file, no credentials |

Safe exports omit all credential fields (`password`, `token_value`, `token_key`, `token_secret`, `token`), including usable legacy NetBox token values. Inventory metadata can still be confidential. Follow your organization's data-sharing policy before distributing an export.

### Export with secrets

Click **Export with secrets** to open the export modal. This produces the same formats but includes credential fields in plain text.

Sensitive export requires an authenticated, active superuser or an explicit
`ProxboxSensitiveDataAccess.can_access_sensitive_data=True` grant. Endpoint view
and credential-provider permissions remain additional requirements. Staff,
group membership, endpoint change permission, and token-creation permission do
not grant sensitive access.

The authenticated request user remains the actor for queryset restrictions and
credential-provider resolution. Export no longer creates a NetBox token or asks
for a second user's token. Standard NetBox token management is unchanged.

The server rejects unauthorized sensitive requests with HTTP 403 before
resolving credentials. An explicit selection containing an inaccessible object
is rejected rather than silently reduced. The modal is hidden from users
without sensitive access, and its POST retains CSRF protection. Secret responses
set `Cache-Control: no-store`. Provider or decryption failures return a generic
HTTP 503 without exception text or partial export rows. Authorization failures
return HTTP 403. Protected responses include a server-generated
`X-Export-Correlation-ID`.

Sensitive-export audit records contain only the fixed result, actor ID, visible
object IDs, model, normalized format, and correlation ID. They never contain
credentials, submitted tokens, request headers, export rows, or provider errors.

Custom NetBox export templates are unavailable for endpoint lists because they
receive credential-bearing model objects outside the protected export contract.
Use the dedicated CSV, JSON, or YAML actions. Generic table exports remain
metadata-only. Nested API token objects and the NetBox endpoint token column
show only token identity metadata, never bearer material or token fragments.
The NetBox endpoint edit form never renders a stored or submitted token secret
into HTML. A blank v2 secret preserves the existing value only when the token
key and connection identity are unchanged. Changing that identity requires an
explicit replacement secret; this does not replace independent target approval.

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
| NetBoxEndpoint | Inventory metadata only | `token`, `token_key`, `token_secret` |
| FastAPIEndpoint | All others | `token` |

---

## Permissions

| Action | Required permission |
|---|---|
| Safe export | `netbox_proxbox.view_{model}` |
| Sensitive export | Endpoint view permission, active authenticated superuser or explicit sensitive-data grant, and credential-provider permission |
| Import | `netbox_proxbox.add_{model}` |
| Manage sensitive-data grants | Active authenticated superuser only |

## Sensitive-data grants

The plugin owns a one-to-one user extension named `ProxboxSensitiveDataAccess`.
Its `can_access_sensitive_data` Boolean defaults to `False`. Migration does not
enable grants for existing users. A superuser does not need a grant row.

Active superusers administer grants through the protected
`/api/plugins/proxbox/sensitive-data-access/` API, including its browsable API
interface. Its permission chain retains NetBox's read-only-token checks. Even
a superuser's read-only API token cannot create, change, or delete grants.
Ordinary model permissions cannot authorize this API. No generic
import or user-edit surface exposes grant administration.

Create a grant with the intended NetBox user ID and an explicit Boolean:

```json
{"user": 17, "can_access_sensitive_data": true}
```

Revoke access by setting the flag to `false` or deleting the grant. Authorization
reads the database on each sensitive request instead of trusting a cached user
relation. A missing grant or failed lookup denies access.

`GET /api/plugins/proxbox/sensitive-data-readiness/` returns only the
authenticated caller's current decision:

```json
{"schema_version": 1, "can_access_sensitive_data": false}
```

The readiness response contains no credentials and is not cached. It does not
grant object visibility, provider reveal rights, target approval, endpoint
writes, or infrastructure operation authority.

Runtime settings reveal the plugin encryption key only to users who pass the
same sensitive-data gate and independently have view access to the settings
row. A grant never provides that visibility. Settings-change permission alone
is insufficient.
Backend service accounts need an explicit grant unless they are superusers;
prefer constrained, flagged non-superuser accounts. Grant administration and
production provisioning remain operator-controlled actions.

## SSH secret access

Both by-node and by-endpoint SSH credential APIs require an active,
authenticated superuser or the explicit sensitive-data flag before resolving
local Fernet or OpenBao material. The backend's NetBox API token owner must
satisfy this rule; possession of a token or `view_nodesshcredential` alone is
insufficient. Grant revocation takes effect on the next request.

The existing API-token authentication, HTTPS requirement outside development,
endpoint enablement and SSH access-method gates, exact credential-object
visibility, and provider reveal permissions remain independent. Endpoint
provider reads use the authenticated request actor. Successful secret responses
set `Cache-Control: no-store`. Metadata and public host-key lookup retain their
separate permission contracts.

## Connection target approval

Proxmox and remote NetBox endpoint edits are configuration drafts until their
exact connection target has been approved. The internal
`approved_connection_target_fingerprint` binds the domain, fallback IP value,
port, TLS policy, and authentication identity. Display-name changes do not
invalidate it. Target edits, approval revocation, changed IPAddress values, and
stale loaded endpoint objects block credential payload creation before secret
resolution. Approval is checked again after material resolution and before a
backend write, including when it changes during the backend listing request.

Migration `0104_security_hardening` leaves existing approvals blank.
The endpoint detail page provides a **Connection target approval** panel. Review
every displayed destination, fallback IP address, port, TLS policy, and
authentication identity before selecting **Approve reviewed target**. Approval
requires sensitive-data access and independent view/change access to the endpoint.
Disabled endpoints cannot be approved for credential transmission. If the target
changes during review, select **Review again** and inspect the new values before
approving. A failed request never approves the endpoint.

After an upgrade, a successful FastAPI health check can coexist with failed
Proxmox connections: backend health does not establish approval of the Proxmox
destination. Review and approve each intended Proxmox endpoint and the remote
NetBox endpoint, then retry synchronization. Changing the backend's HTTP setting
does not restore missing target approval.

For API clients, use the protected action directly.
After upgrading, review each intended endpoint before resuming synchronization:

1. Read `GET /api/plugins/proxbox/endpoints/proxmox/{id}/connection-authority/`
   or `GET /api/plugins/proxbox/endpoints/netbox/{id}/connection-authority/`.
   The response contains only the target, its fingerprint, and approval state.
2. Review the exact target, including its fallback IP and TLS policy.
3. Submit `PUT` to the same URL with
   `{"target_fingerprint": "<the reviewed fingerprint>"}`.
   Approval requires sensitive-data access and independent view/change access
   to the exact endpoint. API tokens must permit writes.

An outdated fingerprint returns HTTP 409. Approval does not reveal material,
grant provider permissions, authenticate the remote service, or authorize
infrastructure changes. Ordinary endpoint serializers and forms cannot set the
internal fingerprint. Existing endpoint save hooks may synchronize an approved
configuration through their normal backend path.

Ordinary full saves preserve the database's current approval under a row lock;
they cannot restore an approval revoked after the object was loaded. Direct
partial writes to the internal approval field are rejected. A backend's existing
endpoint row does not substitute for local approval when synchronization decides
whether it can continue after a failed push.

FastAPI continues to use its existing durable HTTP/fallback-IP/WebSocket/TLS
fingerprint and authenticated key adoption. Editing an enabled backend target
requires sensitive-data access and object view/change authority before the old
key can be resolved or authenticated against the new target. Disabled backend
target edits remain drafts; enabling a target with stale approval requires the
same authority and the existing authentication flow.

## Changelog redaction

New NetBox ObjectChange snapshots mask settings encryption keys, endpoint and
SSH credentials, encrypted material, and provider credential references. The
same registry covers PBS/PDM, Firecracker agent tokens, cloud-init references,
and metrics query tokens. Non-sensitive metadata and caller-supplied snapshot
exclusions remain intact. Public cloud-init SSH keys are preserved.

Historical ObjectChange records created before this change can contain the
encryption key, plaintext tokens, or ciphertext. Access to those records must
be reviewed separately. This change does not sanitize production history or
rotate credentials.
