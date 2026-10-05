# Version 0.0.29

## Summary

This release hardens netbox-proxbox security. It gates sensitive credential
disclosure behind an explicit per-user grant, requires explicit approval of
every endpoint connection target before credentials are sent, scopes HA and
settings reads to what the caller may view, validates Proxmox identifiers
before they reach backend request paths, makes the server-side WebSocket sync
route side-effect free on GET, defaults new endpoints to HTTPS and TLS
verification, and raises dependency security floors. It also corrects cluster
virtual-machine bulk deletion and documents the validated Proxmox OCI
appliance.

## Release status

This is the final 0.0.29 release. It ships the validated `0.0.29` content unchanged.

Current backend-runtime pairing: netbox-proxbox 0.0.29 <-> proxbox-api 0.0.23.post3 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.29 | v0.0.23.post3 | v0.0.13 | v0.0.15 |

Version 0.0.28 is not used for this release line: its only published candidate
predates this release's schema change, and each release ships exactly one
migration.

## Upgrade notes

- **Migration:** this release adds the single migration
  `0104_security_hardening` after `0103_custom_fields_request_delay_help_text`.
  It creates the default-off sensitive-data grant table, adds the internal
  connection-target approval fields, changes the HTTPS and TLS-verification
  defaults for new rows only, and grants view-only settings access to the
  users behind already-configured backend tokens. Existing endpoints keep
  their stored transport settings, and no approval or sensitive grant is
  backfilled.
- **Connection approval:** every existing NetBox and Proxmox endpoint requires
  an explicit connection-target approval before credentials are sent again.
- **Sensitive data:** credential export, SSH secret reads, and runtime key
  disclosure require an active superuser or an explicit per-user sensitive-data
  grant that only an active superuser can change.
- **HA arm/disarm:** grant the `run_proxmox_action` additional action on a
  Proxmox endpoint object permission to operators who previously relied on
  `change_proxmoxendpoint`.
- **Automation:** API or import clients that create endpoints for a plain-HTTP
  proxbox-api must now send `use_https: false` explicitly.
- **Encryption keys:** new keys must be canonical Fernet keys; legacy raw keys
  still decrypt and should be rotated (system check `netbox_proxbox.W104`).
- **System checks:** `manage.py check --database default` reports insecure or
  incomplete existing configuration as `netbox_proxbox.W100` through
  `netbox_proxbox.W105`.

## Sensitive data and connection targets

- `ProxboxSensitiveDataAccess` holds a default-off per-user grant. Sensitive
  endpoint export, SSH credential secret reads, and the settings runtime key
  require it (or an active superuser) in addition to object and provider
  permissions.
- Change-log snapshots of credential-bearing objects are redacted.
- NetBox and Proxmox endpoints store an internal fingerprint of the approved
  connection target. Editing the target clears the approval, and credentials
  are not sent until the exact target is approved again.

## Security fixes

- HA arm/disarm (`ha/arm/`, `ha/disarm/`) now requires the grantable
  `run_proxmox_action` action on Proxmox endpoints instead of
  `change_proxmoxendpoint`, acts only on enabled endpoints the caller holds that
  action on under NetBox object permissions, and skips endpoints whose
  `allow_writes` flag is off (reported as
  `endpoint_writes_disabled` without a backend call). An optional
  `endpoint_id` POST field targets one endpoint. Previously a user with a
  permission scoped to one endpoint could arm or disarm HA on every cluster.
  The views accept CSRF-protected session requests only, and a result is
  reported as successful only when proxbox-api returns a non-empty result list
  whose every row has `status: ok`; HTTP 200 with a per-cluster error is now
  reported as a failure. **Upgrade note:** operators who used HA arm/disarm
  with `change_proxmoxendpoint` must be granted the `run_proxmox_action`
  additional action on a Proxmox endpoint object permission.
- Proxmox node names, storage names, guest types, and VM IDs are now
  validated and percent-encoded before they are placed in a proxbox-api request
  path. Previously a NetBox device name such as `../extras` could collapse the
  authenticated backend URL onto a different route. Invalid identifiers are now
  refused before any request is sent, and the affected page shows a clear
  message instead. Firewall pushes apply the same validation to security-group,
  alias, IP-set, node, and VNet names (`quote()` alone kept `..`), and an
  IP-set entry key must be a valid IP address or network, or a valid alias
  name. When a
  template's configuration cannot be read — no node, an invalid identifier, or
  a backend error — template sync now keeps the stored template instead of
  overwriting it with empty values, and counts it as skipped. Firewall preview
  returns the structured refusal (for example HTTP 400 `invalid_identifier`)
  instead of failing with HTTP 500.
- The server-side WebSocket route `websocket/<kind>` no longer starts a
  backend sync on GET. A sync now requires a CSRF-protected POST and the
  `core.add_job` permission, so a cross-site link or image can no longer start
  one for a logged-in user. Reading buffered messages uses a per-client
  `after` cursor and no longer removes messages that other users have not read.
  The route now also requires view permission on the specific FastAPI endpoint
  that the shared WebSocket worker serves (object-permission constraints are
  honoured), keeps buffered messages per endpoint, and reports cursors from
  another worker process or evicted messages through the
  `X-Proxbox-Cursor-Reset` and `X-Proxbox-Cursor-Gap` headers. The browser
  polling helper keeps polling through empty pages, completes only on the
  terminal message for the requested sync kind (a full update completes only
  on the VM-stage terminal; silence is reported as a timeout, never as
  success), and reports a cursor reset or gap as an error. Only one sync kind
  runs at a time, each queued command is bound to the worker that authorized
  it and dropped if a different worker would send it, terminal messages and
  the release of their sync button are published atomically, and a running
  sync latch expires after ten minutes without backend activity so a lost
  terminal cannot block syncs indefinitely.
- New backend endpoints now default to **Use HTTPS** and new Proxmox endpoints
  to **Verify SSL** (migration `0104_security_hardening`, state-only;
  existing rows keep their stored values). CSV imports that omit the
  `use_https` or `verify_ssl` column also keep these secure defaults for new
  rows, while an explicit `false` is still honoured. The plugin no longer sets the
  process-wide `REQUESTS_CA_BUNDLE` to the mkcert root when a backend URL merely
  contained `localhost`, which changed TLS trust for every later request in the
  NetBox process. New plugin encryption keys must be canonical Fernet keys (44
  url-safe base64 characters in their strict canonical spelling); raw
  32-character secrets, which were used without
  key derivation, are rejected when written, while an already stored legacy key
  keeps decrypting. New `netbox_proxbox.W101`–`W104` database system checks
  report existing plain-HTTP or unverified endpoints and a legacy raw key, and
  `W100` reports when those settings could not be inspected. Key rotation now
  compares decoded key material, so a rotation between two spellings of the
  same key is refused.
  **Upgrade note:** automation that creates a backend endpoint for a plain-HTTP
  proxbox-api must now send `use_https: false`; rotate a legacy raw encryption
  key to a generated Fernet key through the verified rotation workflow.
- Plugin settings reads (`/api/plugins/proxbox/settings/` and its `runtime/`
  route) now require `view_proxboxpluginsettings` instead of any authenticated
  user, and HA data (status page, VM HA tab, HA REST API) is scoped to the
  Proxmox endpoints the caller may view, so anonymous callers with
  `LOGIN_REQUIRED = False` no longer see HA state unless endpoint viewing is
  exempt. Released proxbox-api clients fall back to their defaults when a
  settings read is denied, so migration `0104_security_hardening`
  grants a view-only permission on the settings model to the users behind the
  NetBox tokens already configured on enabled NetBox endpoints. **Upgrade
  note:** for backend tokens configured later, grant
  `view_proxboxpluginsettings`; the new `netbox_proxbox.W105` system check
  reports a backend token that cannot read the settings or cannot be resolved.

## Fixes

- Cluster virtual-machine bulk deletion resolves the selected virtual machines
  defensively, limits deletion to the active cluster, preserves unrelated
  selections, and reports missing or mismatched records instead of raising an
  internal server error.

- The Proxbox home page and the NetBox endpoint list no longer fail with an
  internal server error on NetBox 4.7 when listing NetBox endpoints; the token
  column shows only the token's identity.
- The device sync-state API supports exact `proxmox_node_name` and
  `proxmox_cluster_name` filters, so proxbox-api resolves a node's NetBox
  device without reporting that several devices claim the same node.

## Known limitations

- Node device identity is not yet scoped by Proxmox endpoint. When two Proxmox
  endpoints use the same cluster name and the same node name, the first
  synchronization of the second endpoint can match the first endpoint's node
  device. Give each endpoint's cluster or nodes distinct names until a later
  release adds endpoint scoping to device sync state.

## Dependencies

- Raised security floors for Django, oauthlib, PyJWT, social-auth-core,
  `urllib3>=2.8.0`, and `virtualenv>=21.7.13`, with every NetBox requirements
  hash lock regenerated.

## Documentation

- The validated Proxmox OCI appliance deployment is documented.
- The security policy and threat model are documented.

## Validation

- Mocked regression suite and real-NetBox Django suites for every security
  change; migration upgrade from the 0.0.27.post1 boundary and from a fresh
  database; `makemigrations --check`.
