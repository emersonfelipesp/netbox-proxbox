# netbox-proxbox Codebase Guide

## Repository Destination Policy (Hard Rule)

This project is owned and changed only through the Emerson repositories:

- Development, issues, branches, commits, and pull requests:
  `https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox.git`
- Approved public promotion, mirroring, and releases through
  `deploy-workflow` only:
  `https://github.com/emersonfelipesp/netbox-proxbox.git`

`https://github.com/edgeuno/netbox-proxbox` and
`/root/personal-context/edgeuno/netbox-proxbox/` are read-only vendor/reference
sources. Never create or update EdgeUno issues, PRs, comments, branches,
commits, tags, releases, packages, mirrors, or deployments; never configure
EdgeUno as a writable remote, upstream, fallback, or PR base; and never edit,
stage, or commit the local EdgeUno vendor submodule. Reading, fetching,
grepping, and comparing it are permitted.

Before every external write, resolve and inspect the exact owner, repository,
and remote URL. Abort unless it matches one of the two exact Emerson
destinations above. A stale cross-repository PR may automatically display new
commits from its source branch without a write to its base. Never rewrite,
delete, recreate, or force-push an Emerson branch to alter an EdgeUno PR. Do
not attempt to close it from Emerson workflows; closure requires the PR author
or an actor authorized on the EdgeUno base repository.

> **LLM Agent Safety — Destructive Operations:** netbox-proxbox protects VM
> destruction behind a five-lock chain. **Never autonomously set
> `apply_destroy_confirmed=True`, submit the confirmation phrase
> `"allow-edit-and-add-actions"` on a user's behalf, or approve a
> `DeletionRequest` as the same user who created it.**
> The `DeletionRequest` REST endpoint is read-only (`GET`/`HEAD`/`OPTIONS`
> only). See `AGENTS.md` §"LLM Agent Safety Guardrails" for the full five-lock
> chain protocol.

## Pre-commit Checklist

**Before committing ANY change:**

1. Run syntax check: `python -m compileall netbox_proxbox tests`
2. Run linter: `rtk ruff check .`
3. Run mocked tests: `rtk pytest -p no:django tests/`
4. Run type checker: `rtk ty check proxbox_cli`

---

## Framework stack preference

Follow the same dependency order agents use (see [`AGENTS.md`](./AGENTS.md)):

1. **NetBox plugin layer** — Reuse this plugin’s established patterns and NetBox’s plugin APIs (registration, plugin paths, `NetBoxModel` / `NetBoxModelViewSet`, tables and filtersets consistent with other plugin code here).
2. **NetBox core** — Prefer `utilities.forms.fields`, `utilities.forms.widgets`, `utilities.views`, and other `utilities.*` / `netbox.*` primitives before inventing parallel implementations.
3. **Django** — Use `django.forms`, `django.http`, ORM, and related stdlib-backed APIs when NetBox does not offer a specific helper.

**Third-party packages:** Do not introduce new PyPI dependencies for capabilities NetBox or Django already cover. The project already declares `requests`, `websockets`, and optional CLI-related packages in [`pyproject.toml`](./pyproject.toml); add new deps only for integration needs that have no NetBox/Django path, not as shortcuts for UI or API patterns the core stack handles.

**Example:** NetBox may remove or rename widgets (for example legacy Select2 helpers under `utilities.forms.widgets`). Prefer current NetBox field/widget pairs such as `DynamicModelMultipleChoiceField` with API-driven multi-select rather than pulling in extra front-end or Python widget libraries. For form layout and field choices in this plugin, see [`netbox_proxbox/forms/CLAUDE.md`](./netbox_proxbox/forms/CLAUDE.md).

## Security and permissions

- **Registered CRUD** (via `register_model_view` and `netbox.views.generic`) inherits NetBox `ObjectPermissionRequiredMixin`: model permissions plus `queryset.restrict()` for object-level rules.
- **Custom views** should use `utilities.views.ConditionalLoginRequiredMixin` (respects `LOGIN_REQUIRED`) instead of Django’s unconditional `login_required`, and `TokenConditionalLoginRequiredMixin` where REST tokens should authenticate browser-style endpoints.
- **Operational endpoints** (sync actions, schedule job, WebSocket bridge): `ContentTypePermissionRequiredMixin` with permissions defined in [`netbox_proxbox/views/proxbox_access.py`](./netbox_proxbox/views/proxbox_access.py) — typically `add` on core `Job` for queueing sync work, `delete` on core `Job` for cancel actions, and `view` on `FastAPIEndpoint` for read-only WebSocket test UI.
- **Dashboard and JSON helpers**: plugin home requires at least one of `view` on `ProxmoxEndpoint` / `NetBoxEndpoint` / `FastAPIEndpoint` when the user is authenticated; endpoint lists use `.restrict(request.user, "view")`. Proxmox card and keepalive JSON resolve objects through restricted querysets (`get_object_or_404(...restrict(...))`). Tagged devices and VMs use `Device.objects.restrict` / `VirtualMachine.objects.restrict` before listing.
- **Plugin REST API** remains on `NetBoxModelViewSet` with standard NetBox/DRF permission classes. Its read-only `mcp/` manifest only describes existing permission-gated routes for a future compatible netbox-sdk bridge; it must not grow a parallel MCP server or credential store. No released SDK identity is currently activated: keep the checked activation artifact blocked until one exact released version and its clean full-commit package blobs, fixed module origin, explicit provisioning, and paired CI all agree. Schema version 1 identifies the generic descriptor protocol, not a frozen Proxbox payload. The scheduling API rejects the entire request when any explicit Proxmox endpoint ID is unknown or disabled—never filter an explicit scope down to empty, because empty deliberately means all enabled endpoints to the job runner. Omission alone may request that all-endpoint behavior: explicitly empty Proxmox or NetBox scopes are rejected. Endpoint PKs are positive signed-64-bit integers. Integer JSON literals retain the full range; integral float/Decimal forms normalize only through `9007199254740991`, while unsafe larger floats, bool/string/fraction/non-finite values reject. Recurrence value and unit are a required pair. Bridge v1 also rejects unknown properties, duplicate list items, nonpositive/out-of-range endpoint IDs, RFC 3339 leap seconds outside a normalized UTC month boundary, unrepresentable instants, and job names longer than 200 characters. The 13 advertised stages control the SSE pipeline only; endpoint preflight and scoped cluster/node, firewall, datacenter, and normally VM-template passes still mutate inventory. The exact full unique set becomes internal `[all]` for recurring/repair identity. Advertise scheduling as destructive because reconciliation may remove stale NetBox inventory records, even though it does not delete Proxmox guests or infrastructure. Keep the manifest, DRF serializer, producer-owned fixture, executable documentation examples, blocked activation artifact, immutable paired-SDK gate, and pure/real-Django tests aligned; the consumer and operator contract is [`docs/api/semantic-mcp-bridge.md`](./docs/api/semantic-mcp-bridge.md).

---

This repository packages the `netbox_proxbox` NetBox plugin. The plugin adds endpoint inventory for Proxmox, NetBox, and the companion ProxBox FastAPI backend; UI pages for sync operations, cluster summaries, status checks, and job actions; REST API endpoints for the core plugin models; Firecracker host-pool, image-template, and micro-VM inventory for NMS Cloud; and a small amount of browser-side JavaScript and styling for the plugin pages.

## Installation documentation truths

- The plugin supports both traditional host/venv NetBox deployments and Docker-based NetBox deployments (for example `netbox-community/netbox-docker`).
- Docker-based plugin installation docs are maintained at [`docs/installation/3-installing-plugin-docker.md`](./docs/installation/3-installing-plugin-docker.md), including `plugin_requirements.txt` and `configuration/plugins.py` usage.
- Backend Docker examples map host `8800` to container `8000` (`-p 8800:8000`) because the published `proxbox-api` image serves through nginx on container port `8000`.
- **That `8800` default is the standalone-container case only.** `FastAPIEndpoint.port` defaults to `8800` to match the published host port, which is correct when the backend runs as its own `docker run` container. It is **wrong** when the backend is a service in the *same Compose project* as NetBox: a host port published on `127.0.0.1` is unreachable from inside the NetBox container, so that record needs the Compose **service name** plus the **container-internal** port (`8000`). The same reasoning runs the other way for the `NetBoxEndpoint` record — it is consumed by the *backend* container, so it needs netbox-docker's service name and in-container port (`8080`), never `localhost` and never the browser-visible address. Documented in [`docs/installation/3-installing-plugin-docker.md`](./docs/installation/3-installing-plugin-docker.md) § "Endpoint Addresses in a Compose Deployment"; keep both cases side by side rather than replacing one with the other.
- **The credential encryption key belongs on the installation path.** The backend refuses to store any Proxmox credential until it has one, and reports that only when the first Proxmox endpoint is created — after the operator believes setup is finished. [`docs/installation/backend-setup.md`](./docs/installation/backend-setup.md) covers generating a Fernet key and supplying it via `PROXBOX_ENCRYPTION_KEY` (recommended), the plugin settings field, or a backend-local key, plus what happens on key change: verified all-or-nothing plugin rotation, a permission-gated destructive reset when the old key is lost, and the `GET /admin/encryption/status` attestation that blocks plugin rotation while a backend is still on the old key. The setting *semantics* stay in [`docs/configuration/plugin-settings.md`](./docs/configuration/plugin-settings.md); the install page cross-links rather than duplicating them.
- **A backend-local encryption key is not persisted by the Docker image's volume.** The image declares `VOLUME ["/data"]` and defaults `PROXBOX_DEFAULT_DATABASE_PATH=/data/database.db`, but `credentials.py::_DEFAULT_KEY_FILE` resolves to `<package parent>/data/encryption.key` — `/app/data/encryption.key` in the container, which is **not** on that volume. Recreating the container therefore destroys the key while the database survives, stranding every encrypted credential. `PROXBOX_ENCRYPTION_KEY` avoids it entirely; otherwise set `PROXBOX_ENCRYPTION_KEY_FILE=/data/encryption.key`. Any Compose example added to the docs must also name the `/data` volume, or `docker compose down` orphans the endpoint configuration.

The current plugin config lives in [`netbox_proxbox/__init__.py`](./netbox_proxbox/__init__.py). It declares plugin version `0.0.25` and sources its NetBox contract from [`netbox_proxbox/compat.py`](./netbox_proxbox/compat.py): **stable** `4.5.8` through `4.6.99` (validated at `4.5.8`-`4.5.10` and `4.6.0`-`4.6.6`) plus **experimental** evaluation of exact canonical `4.7.0-beta2`. `min_version`/`max_version` are `PLUGIN_MIN_VERSION`/`PLUGIN_MAX_VERSION`; the numeric maximum is `4.7.0`. Because NetBox passes that same bare value for beta2, later prereleases, and GA, `validate()` reads canonical `release.yaml` once and requires `version: "4.7.0"` plus `designation: "beta2"`; optional `local/release.yaml` is read once and may contain only informational `build`. It never trusts overlaying `load_release_data()`. Other 4.7 identities raise `IncompatiblePluginError`, so NetBox warns, omits the plugin from its installed registry, and continues startup. Runtime attests identity only; source SHA, Python archive, and dependency provenance remain CI/operator evidence. `compat.py` is vendored byte-identically across netbox-proxbox, netbox-ceph, netbox-packer, netbox-pbs, and netbox-pdm; change it in one repo and you must change it in all five. It must not import Django at module scope, because NetBox imports it while `netbox/settings.py` is still executing. Current backend-runtime pairing: netbox-proxbox 0.0.25 <-> proxbox-api 0.0.20 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge. The `0.0.25` release moves **Sync Jobs** to a dedicated Proxbox-only page at `/plugins/proxbox/jobs/`, anonymizes the failed-job bug-report export, and consolidates the credential-redaction vocabulary into one module shared by the job-log redactor and the public scrubber. The previous `0.0.24` release added NetBox 4.6.6 certification, settings/storage compatibility fixes, blank-key encryption recovery, and immutable Gitea-first release provenance while retaining bounded endpoint auto-configuration and the universal `guest_os_model` behavior. Existing backend rows authorize only their exact persisted target; rowless discovery is restricted to configured or same-site targets derived from NetBox's trusted public origin, and any unproved target remains pending. The previous stable `0.0.23.post2` release introduced bounded endpoint auto-configuration. `proxbox-api` is not a Python dependency of this plugin; the services communicate over HTTP.

**Companion repos (cross-link map):**

- Backend service: [`emersonfelipesp/proxbox-api`](https://github.com/emersonfelipesp/proxbox-api) — the full v0.0.17 feature set (firewall model scaffolding, intent tag helpers at `PUT /intent/tag-pending-deletion` and `PUT /intent/untag-pending-deletion`, HA REST shim) requires `proxbox-api >= 0.0.13`. HA endpoints alone require `>= 0.0.12`. Firecracker Cloud provisioning uses proxbox-api `/cloud/firecracker/provision` and `/cloud/firecracker/provision/stream` after this plugin creates or exposes the NetBox-side `FirecrackerMicroVM` record. See its [`docs/api/cluster-ha.md`](https://github.com/emersonfelipesp/proxbox-api/blob/main/docs/api/cluster-ha.md) for the upstream HA contract this plugin proxies.
- Workspace context: [`personal-context/claude-reference/netbox-proxbox.md`](https://github.com/emersonfelipesp/personal-context/blob/main/claude-reference/netbox-proxbox.md) — N-MultiCloud workspace-level notes (cross-repo deps, NetBox compatibility rotation policy).

## Architecture Summary

- `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `ProxmoxCluster`, `ProxmoxNode`, `ProxmoxStorage`, `ProxmoxStorageVirtualDisk`, `BackupRoutine`, `Replication`, `VMBackup`, `VMSnapshot`, `VMTaskHistory`, `GuestVMInterface`, `GuestVMInterfaceAddress`, and `ProxboxPluginSettings` are the plugin's core Proxmox reflection models.
- **Typed custom-field sidecars (migration 0065/0066).** The legacy Proxbox
  custom-field payload is now mirrored into plugin-owned
  `Proxbox*SyncState` sidecar models in `models/sync_state.py`, one row per
  affected NetBox core object. The shared abstract `ProxboxSyncStateBase`
  stores `proxmox_last_updated` (from the legacy custom field) and
  `last_run_id` (from `proxbox_last_run_id`) so those recurrent fields are not
  duplicated across 14 concrete models. `last_updated` remains the
  NetBox-managed row timestamp used for API ETags. VM/device sidecars replace raw
  `proxmox_endpoint_id`, `proxmox_node`, and `proxmox_cluster` custom fields
  with nullable FKs to existing `ProxmoxEndpoint`, `ProxmoxNode`, and
  `ProxmoxCluster`, while preserving unresolved values in fallback name fields
  and `proxmox_endpoint_raw_id`. Cluster sidecars preserve the legacy cluster
  numeric value in `proxmox_cluster_raw_id`. Virtual-disk and VM-interface
  sidecars promote the legacy `proxbox_storage_id` / `proxbox_bridge` JSON
  values to nullable `proxbox_storage` / `proxbox_bridge` FKs while retaining
  numeric unresolved IDs in `*_raw_id` and non-numeric/malformed raw payloads
  in `*_raw_value` text fallbacks. This runs through the retry-safe
  `0067`/`0068`/`0069` split: additive staging schema, non-atomic idempotent
  data conversion with a data-preserving reverse, then guarded atomic
  cleanup/promotion to final field names. The VM sidecar additionally stores
  `proxmox_last_synced_role_id` as a nullable
  scalar snapshot of the DeviceRole last written by sync. It is not a foreign
  key so role deletion cannot erase ownership evidence. Migration 0078
  backfills valid values from the deprecated VM custom field without deleting
  legacy data; proxbox-api uses the typed value to preserve operator-edited
  roles and writes a new snapshot only after successful reconciliation. The
  core NetBox `virtualization.Cluster` payload lives in
  `ProxboxClusterSyncState`, not on `ProxmoxCluster`, because `ProxmoxCluster`
  is endpoint-scoped (`endpoint`, `name`) and only optionally links to a
  NetBox cluster. Sync-state API duplicate/occupied-parent preflight returns an
  exact `409`; attempts to change a sidecar's parent to an unoccupied object
  remain `400`. Device/node and cluster/proxmox-cluster relations must point
  back to the same NetBox parent. Writable storage and bridge relations resolve
  through request-restricted querysets, and hidden nested endpoint/node/cluster,
  storage, and bridge relations are masked or filtered from API responses. These
  sidecars are now the standard source of truth: the proxbox-api writer/reader
  switch has landed, so a normal sync writes and reads the sidecars (rebuilt from
  live Proxmox data). The legacy reflection custom fields are deprecated and
  gated behind `ProxboxPluginSettings.custom_fields_enabled` (default `False`);
  by default proxbox-api does not write, read, or reconcile custom fields.
  Setting the flag `True` restores legacy custom-field behavior for a transition
  and emits deprecation warnings. Full custom-field removal is a later cleanup;
  no data is deleted while the flag exists.
- Companion endpoint models: `PBSEndpoint`, `PDMEndpoint`, `PDMRemote` for Proxmox Backup Server and Datacenter Manager inventory.
- SSH and hardware discovery: `NodeSSHCredential` stores per-node SSH credentials for the optional hardware-discovery pass.
- `ProxmoxEndpoint.access_methods` (migration 0056, choices `api` / `api_ssh`, default `api`) is the per-endpoint **transport access method**, orthogonal to `allow_writes`. `api` = Read+Write over the Proxmox API only; `api_ssh` = API + SSH. SSH only complements API; **SSH-only is not a selectable choice**. It is the load-bearing gate for the browser SSH terminal: the credential-serving API views in `netbox_proxbox/api/ssh_credentials.py` (`ProxmoxEndpointSSHCredentialSecretsAPIView` for endpoint targets and `NodeSSHCredentialSecretsAPIView` for node targets, the latter via the owning `ProxmoxNode.endpoint`) return 403 and withhold secrets when the endpoint is API-only, which is what blocks the terminal. New endpoints default to `api`; existing rows are backfilled to `api_ssh` on upgrade (non-breaking). The value is pushed to the proxbox-api backend by `_proxmox_backend_payload()` so the backend can gate its own SSH paths.
- `ProxmoxEndpoint.allow_packer_template_builds` (migration 0082, default
  `False`) is the narrow operator capability for netbox-packer Cloud-Init
  template-image creation. It is effective only while the endpoint is enabled
  and `allow_writes=True`, grants no other mutation, and is propagated by
  `_proxmox_backend_payload()` only as that effective three-gate value;
  `allow_writes` remains a separately managed backend trust boundary. Backend
  row currency compares both `enabled` and the effective narrow flag so
  revocation forces a push. A save that disables an existing endpoint performs
  a credential-free policy-only backend update (`enabled=False` and narrow
  grant false), but never creates a backend row. Missing fields on a rolling
  upgrade fail closed. The post-save push is registered with
  `transaction.on_commit()` and re-reads the committed row; a rolled-back save
  therefore cannot grant remote authority. The internal read-only
  `packer_template_builds_backend_authorized` field records the last
  successfully pushed effective grant. Local/model/UI/REST deletion and
  local-only bulk toggles remain blocked while either the requested narrow flag
  or that confirmed backend state is true, so a failed revocation cannot orphan
  an active backend grant. Both template-build REST actions require
  `core.run_proxmox_action`, check enabled/broad/narrow before backend access,
  and resolve the immutable `(nb:<pk>)` identity to proxbox-api's own row ID.
- **Terminal-tab credential modal (store vs one-shot).** When a Terminal-tab
  target (a `ProxmoxNode`, or the endpoint) has **no** stored SSH credential,
  the browser JS (`static/.../js/ssh_terminal.js`) opens a modal instead of
  dead-ending on "No SSH credential registered". The operator enters
  username/password (or key), fetches + accepts the host-key fingerprint
  (`GET ssh-credentials/by-node/<id>/host-key-fingerprint/`), and chooses
  **Use once** (one-shot) or **Store for future sessions**. The session view
  (`ProxmoxEndpointSSHTerminalSessionView.post`) reads a `credential` object +
  `store` flag: on **store** it persists an encrypted `NodeSSHCredential` (needs
  `add`/`change_nodesshcredential` + the plugin encryption key, else 403/503)
  then opens a normal stored session; on **one-shot** it forwards the inline
  creds to proxbox-api as `one_shot_credential` and stores nothing. Both paths
  re-enforce `open_ssh_terminal` and `ssh_access_enabled` (the one-shot path
  bypasses the stored-credential access gate, so the view checks the access
  method explicitly). Per-node stored-credential readiness (`ssh_ready`) and the
  store-capability flag (`can_store_credentials`) come from
  `ProxmoxEndpointSSHTerminalView.get_extra_context`. **Pairing:** the one-shot
  path requires a proxbox-api release whose `POST /ssh/sessions` accepts the
  optional `one_shot_credential` field; the plugin degrades gracefully against an
  older backend (which rejects the extra field), and the store path works against
  any backend.
- **Proxmox endpoint service monitoring:** opt-in, agentless, pull-based systemd
  service status collection for `ProxmoxEndpoint`. Eligibility is deliberately
  tied to `allow_writes=True`, `access_methods="api_ssh"`, and complete endpoint
  SSH credentials. netbox-proxbox does not open SSH or run shell commands; it
  creates a soft-optional `netbox-rpc` `RPCExecution` for
  `os.linux.proxmox.show_systemctl_services` with params
  `{proxmox_endpoint_id, units}` and `assigned_object` set to the endpoint. The
  RPC backend uses the endpoint's own SSH credential. Projection is asynchronous:
  `collect_systemctl_services()` creates the execution plus a pending
  `ProxmoxServiceCollection`, and `project_completed_collections()` later reads
  `execution.result` into `ProxmoxServiceSample`, latest `ProxmoxServiceStatus`,
  and endpoint heartbeat fields. Never add a synchronous netbox-rpc run path.
- VM lifecycle models: `ProxmoxVMTemplate` (VM template inventory with optional FK to `VirtualMachine`), `ProxmoxVMCloudInit` (cloud-init config), `CloudImageTemplate` (Firecracker/image factory catalog), `ProxmoxApplyJob` (intent apply job), `DeletionRequest` (auditable delete-request workflow).
- **`ProxmoxVMCloudInit` create-time intent (migration 0064).** In addition to
  the read-only reflection columns (`ciuser`/`sshkeys`/`ipconfig0`/
  `sshkeys_truncated`, patched from `qm config` by proxbox-api), the model now
  stores the **create-time cloud-init intent** the NMS stack sent at VM/LXC
  create time: `is_intent`, `hostname`, `search_domain`, `dns_servers`
  (comma-separated), `bridge`, `vlan_tag`, `gateway`, `ip_cidr`, `ssh_pwauth`,
  `enable_agent`, and a soft `nms_credential_id` (integer PK of the netbox-nms
  `CloudVMCredential` holding the encrypted password / SSH private key — **not a
  FK; netbox-proxbox never imports netbox-nms**). SSH public keys captured at
  create time are Fernet-encrypted at rest in `sshkeys_enc` (accessors
  `set_sshkeys`/`get_sshkeys`, `has_sshkeys`, reusing
  `models/primary_secrets.py`); the API writes them through the **write-only**
  `sshkeys_intent` serializer field and never returns the raw bundle (only
  `has_sshkeys`). The intent fields are deliberately kept **out** of proxbox-api's
  `CLOUDINIT_PATCHABLE_FIELDS`, so a later reflection sync never clobbers them,
  and the plaintext `sshkeys` reflection mirror is left untouched.
- VM interface modeling uses a dual representation under `ProxboxPluginSettings.vm_interface_sync_strategy="guest_os_model"` (the default): Proxmox config NICs stay as core `virtualization.VMInterface` rows with canonical names such as `net0`; guest-agent OS names such as `ens18` are stored in plugin `GuestVMInterface` rows. `GuestVMInterface.vm_interface` is nullable for agent-only interfaces, and `GuestVMInterfaceAddress` links guest interfaces to the same core `ipam.IPAddress` objects used by the core VM interface assignment. The old `use_guest_agent_interface_name` toggle is deprecated and applies only when the strategy is `legacy_rename`.
- Datacenter config: `ProxmoxDatacenterCpuModel` (custom CPU models synced from PVE).
- Metrics metadata: `ProxmoxMetricsInfluxDB` maps a Proxmox endpoint and cluster
  to an InfluxDB URL, organization, and bucket for observability consumers. It
  stores only `nms-secret:<uuid>` references for query/writer tokens and never
  persists plaintext InfluxDB credentials.
- Firewall inventory (6 models, read-only): `ProxmoxFirewallSecurityGroup`, `ProxmoxFirewallRule`, `ProxmoxFirewallIPSet`, `ProxmoxFirewallIPSetEntry`, `ProxmoxFirewallAlias`, `ProxmoxFirewallOptions`.
- SDN inventory (PVE 9.2+): controllers, zones, VNets, subnets, bindings, fabrics, route maps, and prefix lists.
- Firecracker Cloud uses separate `FirecrackerHostPool`, `FirecrackerHost`, `FirecrackerImageTemplate`, and `FirecrackerMicroVM` models. A micro-VM is not a NetBox core `VirtualMachine`; API clients identify it with `kind="firecracker"` and `instance_ref="firecracker:<id>"`.
- `ProxmoxEndpoint.allowed_tenants` is the tenant allow-list for NMS Cloud endpoint visibility. Empty means default/global visibility. Non-empty pins the endpoint to those tenants. The paired backend must hide the default/global pool for a tenant as soon as any explicit endpoint grant matches that tenant.
- `ProxboxPluginSettings` includes sync mode fields `sync_mode_vm_interface` and `sync_mode_mac` (migration 0051), `vm_interface_sync_strategy` (default `guest_os_model`), and interface-batch tunables `interface_batch_size` (default 5) and `interface_batch_delay_ms` (default 100).
- `ProxboxPluginSettings.netbox_openapi_persist` (migration 0057, default `True`) controls whether proxbox-api caches the resolved NetBox OpenAPI schema on disk. Disabling it runs the backend's schema resolution fully in-memory (no filesystem read/write) for read-only or no-disk-write deployments; the backend resolves it as env `PROXBOX_NETBOX_OPENAPI_PERSIST` > this setting > default. Documented in `docs/configuration/plugin-settings.md` and `docs/api/settings.md`; source-contract-tested in `tests/test_settings_netbox_openapi_persist.py`.
- `ProxboxPluginSettings` cloud-customer network fields (migration 0059) store the operator-designated IPAM Prefix ID, bridge, VLAN tag, gateway, and lock flag used by proxbox-api and nms-backend to resolve customer-facing cloud networking without hardcoded estate values. Populate them with `python manage.py ensure_cloud_customer_network --prefix ... --vlan ... --gateway ... [--enable-lock]`; the command is idempotent and documented in `docs/configuration/plugin-settings.md`.
- `ProxboxPluginSettings` Ceph timing fields (migration 0077) persist bounded task timeout (`300`, range `1–3600`), poll interval (`1`, range `0.1–60`, never greater than the timeout), and durable run lease (`360`, range `1–3600`). proxbox-api resolves environment override → plugin value → default once per adapter request, normalizes environment-derived polling, independently renews the lease, and persists its immutable snapshot on each operation run. Keep model/form/API validation, JSON-number documentation, template, English docs, and backend timing defaults aligned.
- **`NetBoxEndpoint` and `FastAPIEndpoint` are singletons** — the backend proxy and dashboard always use the first row of each, so only one should exist. Their bulk-import views enforce this by prompting for confirmation before replacing an existing record.
- **Primary endpoint secrets are encrypted at rest.** `ProxmoxEndpoint.password`, `ProxmoxEndpoint.token_value`, `FastAPIEndpoint.token`, `PBSEndpoint.token_secret`, and `PDMEndpoint.token_secret` are public Python properties backed by Fernet-encrypted `*_enc` model fields. Runtime setters use `ProxboxPluginSettings.encryption_key` and create one when storing a primary secret if it is blank; do not reintroduce plaintext model fields for those secrets.
- **Plugin encryption recovery is registry-driven and atomic.**
  `services/encryption_recovery.py::ENCRYPTED_FIELD_FAMILIES` must contain every
  plugin model `*_enc` field plus the optional netbox-pbs
  `PBSPluginSettings.proxbox_api_key_enc` field and the trust fingerprints
  invalidated by a destructive reset. An optional app is omitted only when both
  its Django registration and known database table are absent; dormant table
  ciphertext and installed owners with unresolved models/tables fail closed.
  Ordinary settings/model/API saves may not clear or replace
  `ProxboxPluginSettings.encryption_key` while registry ciphertext exists, and
  its default/base-manager `QuerySet.update()`, `bulk_update()`, and conflict
  upsert paths reject direct key mutation. Verified rotation owns the sole
  exact-value, settings-locked queryset permit for changing the key.
  Registered model saves (including optional netbox-pbs) lock the settings row,
  validate their ciphertext under that key, and persist within that transaction;
  direct queryset/bulk encrypted-field writes are rejected before SQL through
  both the default and base manager. Conflict upserts cannot update registered
  reset trust/operational fields unless the exact call holds the private
  settings-locked internal permit. The only
  raw-ciphertext exception is a private, one-call recovery/adoption update that
  holds the settings-row lock and validates every outgoing non-empty ciphertext
  against the key currently stored there; bulk create/update has no bypass.
  Rotation uses the
  same settings-row order followed by deterministic PostgreSQL table locks, then verifies every value with the old key before any
  write and updates all values plus the key in one transaction. When the stored
  setting drifted, successful verification of every registered ciphertext proves
  the supplied old key and repairs the setting during rotation; with no ciphertext,
  the supplied old key must still match the stored value. Lost-key reset
  is separately permissioned (`reset_encrypted_secrets`), explicitly confirmed,
  selective at the individual failed-ciphertext level, preserves healthy fields
  and rows, disables only affected endpoints (or marks affected Firecracker hosts
  offline), and uses `QuerySet.update()` so endpoint save signals do not fire.
  Partial saves and direct trust/operational bulk updates use recovery snapshots
  so delayed writers cannot restore reset state. Rotation also requires every
  enabled, adopted, operational proxbox-api target to authenticate and return
  the versioned attestation that its active cached key is independent
  (`env`/`local`) and decrypts every stored backend credential; the legacy
  source-only response, plugin-key fallback, unreachable target, or invalid
  response blocks it. Disabled, pending, retired, and trust-drifted backend rows
  rotate locally with zero network access. The target URL and trust fingerprint
  come from one immutable capture so a related-IP update cannot rebind the
  credentialed request. Recovery POST values, settings serializer mutation
  frames, and the settings model save frame that loads the active key are
  exception-reporter-sensitive; each attempt emits a secret-free NetBox
  changelog event.
  Keep this plugin-at-rest key separate from proxbox-api's own database
  encryption key and the FastAPI endpoint authentication key. Ordinary settings
  serializers withhold it; the backend-only runtime route retains its existing
  permission-gated compatibility response until a paired proxbox-api migration
  removes that fallback.
- **Backend API-key adoption is fail-closed.** `FastAPIEndpoint.save()` and
  every UI/import/API persistence path share
  `services.backend_key_adoption.adopt_rotated_backend_key()`. Keys are never
  exposed or recovered from the backend. A new disabled row stays keyless and
  performs no discovery. An enabled save without an explicit candidate commits
  a pending row with a blank fingerprint and encrypted candidate, then invokes
  `services.endpoint_autoconfiguration` through `transaction.on_commit`. The
  service treats the exact UI-persisted URL/IP, port, and TLS policy as its entire
  allowlist, probes identity/readiness without credentials, and authenticates
  the existing encrypted key. It generates and retains a key only for a
  confirmed empty backend's one-time bootstrap. If no row exists, startup
  discovery is bounded to plugin configuration and same-site names derived
  from NetBox's trusted origin; it never scans or follows redirects. An
  initialized backend with no locally held key stays pending. Explicit token
  submission remains the manual rotation/recovery path. A credential-free
  `backend_key_target_fingerprint` durably binds the ciphertext to the
  canonical primary HTTP target, fallback IP, TLS flags, and WebSocket target
  flags; every runtime credential lookup recomputes it using a fresh IP FK and
  fails closed on drift. HTTP and WebSocket adoption rejects redirects, the
  WebSocket client disables ambient proxies and rechecks trust throughout its
  lifetime, and endpoint saves cancel stale clients. The same redirect rule
  covers every **runtime** request plugin-wide: every direct `requests` call in
  `netbox_proxbox/` sends `allow_redirects=False` (sole exception: the
  unauthenticated public-content fetches in `github.py`), enforced structurally
  by `tests/test_outbound_redirect_policy.py`, and the proxy/readiness paths
  additionally treat any 3xx as a terminal transport failure — so the API key
  is never replayed to a redirect target; a 401 retry proceeds only
  from one freshly re-authenticated, identity-bound request context or fails
  closed (see `services/CLAUDE.md`). Never treat HTTP 409 as
  success, expose token previews, or include response or transport text in key
  errors. Keep the state machine and automated evidence aligned with
  [`docs/developer/endpoint-autoconfiguration.md`](./docs/developer/endpoint-autoconfiguration.md).
- NetBox UI routes live in [`netbox_proxbox/urls.py`](./netbox_proxbox/urls.py) and are implemented primarily in `netbox_proxbox/views/`.
- The plugin also exposes a NetBox plugin API under `netbox_proxbox/api/`, using serializers, filtersets, and standard `NetBoxModelViewSet` classes. The root advertises a version 1 semantic producer manifest at `mcp/`; only a future exact SDK identity activated by the checked immutable gate may validate and invoke its fixed plugin-local targets through the normal API client.
- Sync actions enqueue NetBox background jobs (`ProxboxSyncJob`) on NetBox's default RQ queue and call the external ProxBox FastAPI SSE endpoints to record progress/result on the Job row.
- **Operator sync-state repair UX (issue #217, hardened in #255).** The
  **Repair / Rebuild Proxbox sync-state** card lives on a dedicated page at
  `/plugins/proxbox/sync-state/` (`SyncStateRepairPageView`). The page is
  **deliberately absent from the plugin navigation menu** — it is an operator
  recovery action, not a routine one — so its only entry point is the
  **Repair / Rebuild sync-state** link in the footer of the Proxbox Home page.
  The card is always visible on that page; it no longer renders inline on Home
  or Settings. Its inline JS auto-checks
  `services/backend_proxy.py::get_backend_bootstrap_status()`
  (`GET /extras/bootstrap-status`, gated by `view` on `FastAPIEndpoint`) on page
  load and flags a genuine backend-reported problem (`ok:false` with
  `http_status == 200`, e.g. the "Invalid v1 token" bootstrap warnings); a
  healthy or unreachable/unconfigured backend is not a needs-attention state. A
  **repair-only** user (has `core.add_job` but not `view` on `FastAPIEndpoint`)
  keeps the repair affordance with no bootstrap payload exposed. Included on any
  other page the card keeps its original hidden-until-needed behaviour, guarded
  by `proxbox_repair_page`. The POST action at
  `/plugins/proxbox/sync-state/repair/` uses a
  session-gated `RepairSyncStateView`, requires `core.add_job` via
  `permission_enqueue_proxbox_sync()`, calls
  `POST /extras/custom-fields/reconcile`, then enqueues a normal
  `ProxboxSyncJob` full sync for enabled Proxmox endpoints. **The reconcile is a
  best-effort first step, not a gate:** because it authenticates with the same
  (possibly stale/invalid) NetBox credential that produced the bootstrap
  failure, a reconcile error is recorded as `reconcile_warning` and the rebuild
  sync is still queued — its preflight re-pushes the NetBox/Proxmox endpoint
  credentials to proxbox-api and rebuilds the typed `Proxbox*SyncState` sidecars
  from live Proxmox data, which is the actual recovery. Only permission-denied,
  active-job, and enqueue failures are hard errors; all are flash messages that
  never return a 500.
- The dashboard and Job detail pages are extended by template extensions so Proxbox jobs get run-now/cancel controls and live stream/log helpers. Sync jobs that end in an error/unknown state also get a **Bug report** button whose modal packages job metadata + logs (copy-to-clipboard) and links to a prefilled netbox-proxbox GitHub *new issue* — logic in [`netbox_proxbox/bug_report.py`](./netbox_proxbox/bug_report.py), rendered by [`inc/bug_report_button.html`](./netbox_proxbox/templates/netbox_proxbox/inc/bug_report_button.html). **That payload is anonymized** by [`netbox_proxbox/anonymize.py`](./netbox_proxbox/anonymize.py) before it is displayed — see §"Bug-report anonymization" below.
- **Sync Jobs is a plugin page, not `core:job_list`.** The nav entry points at `plugins:netbox_proxbox:job_list` (`/plugins/proxbox/jobs/`, [`views/jobs.py`](./netbox_proxbox/views/jobs.py)), a subclass of core's `JobListView` whose queryset is filtered by `jobs.proxbox_sync_job_q()`. It previously linked to NetBox's `core:job_list`, which lists **every** job in the instance — reports, scripts, other plugins — so operators had to find the Proxbox rows by eye.
- **Sync Jobs are also a REST endpoint: `GET /api/plugins/proxbox/sync-jobs/`** ([`api/sync_jobs.py`](./netbox_proxbox/api/sync_jobs.py)). It is the API twin of the page above — same `jobs.proxbox_sync_job_q()` queryset, so the two can never disagree about which rows are ours — serialised with core's own `JobSerializer` so a sync job is byte-identical to the same row on `/api/core/jobs/`. It exists because `/api/core/jobs/` **cannot filter on `data`**, which is the only reliable discriminator: a run scheduled with a custom `job_name` keeps that name verbatim, so no name filter finds it. Without this, every API consumer re-implements the predicate client-side and scans the whole job table — on production that is ~29 sync jobs among 24,000 rows, ~140 MB of transfer, which is exactly what `nbx proxbox jobs` had to do. The filterset **subclasses core's `JobFilterSet`** (so a NetBox release that adds a job filter adds it here too) and pushes the `data`-derived ones into SQL: `sync_type`, `proxmox_endpoint_id`, `cluster_id`, `node_id`, `netbox_vm_id`, `run_id`, `batch_object_type`, `errored`. Three semantics are deliberate and match `nbx proxbox jobs` exactly, so one question cannot get two answers: an **open endpoint scope** (absent, JSON `null`, or `[]`) means *every* endpoint; `sync_types: ["all"]` — or no types recorded — covers every requested type; and an **empty VM list is not a wildcard**. `errored` is broader than a failure status because a run can finish `completed` while recording a stage error. `log_entries` is omitted from list responses (a single full-sync row reaches 130 KB); `?include_log_entries=true` restores it, and the detail route always returns it. **Ids inside `job.data` are stored as strings** (`_serialize_sync_params` casts with `str()`), so a numeric jsonb containment test never matches — the filter casts, and `tests/test_sync_jobs_api_django.py` names that failure.
- Browser updates can flow over SSE streams or the existing WebSocket channel.
- Templates and static assets are conventional Django plugin assets under `netbox_proxbox/templates/` and `netbox_proxbox/static/`.
- All three endpoint types support **CSV/JSON/YAML export** (safe and sensitive modes) and **bulk import** with IP auto-creation and id-stripping. See [`netbox_proxbox/views/endpoints/CLAUDE.md`](./netbox_proxbox/views/endpoints/CLAUDE.md).
- The Proxmox endpoint list at `/plugins/proxbox/endpoints/proxmox/` shows `Enabled` by default and exposes **Enable Selected** / **Disable Selected** list actions. These actions bulk-update only `ProxmoxEndpoint.enabled` via `queryset.update()` so they do not fire the ProxmoxEndpoint `post_save` backend-registration/sync signal. Endpoints carrying `allow_packer_template_builds=True` are excluded from bulk toggle and delete paths; revoke the narrow capability through a normal save first so the backend policy row is disabled before local deletion.
- The Proxmox endpoint detail page carries a **Templates** tab (`.../endpoints/proxmox/<pk>/templates/`, `views/proxmox_templates_tab.py`) that reads templates **live** from proxbox-api for that endpoint (`GET /cloud/vm/templates?cloud_init_only=false` + `GET /cloud/lxc/templates`, via `get_fastapi_request_context()` + `resolve_backend_endpoint_id()`), grouped into three client-side filters: **Cloud-Init**, **plain QEMU/KVM (no cloud-init)**, and **LXC**. Cloud-init classification derives from `cloud_init_drives`/`cicustom`, not the always-`True` `cloud_init` field. The tab also offers a "Create Cloud-Init template image" action linked to the optional **netbox-packer** plugin (soft-detected by `integrations/packer.py::is_netbox_packer_installed()`, mirroring `integrations/rpc.py`). It is enabled only when the plugin route exists and the endpoint is enabled with both `allow_writes` and `allow_packer_template_builds` true; every refusal keeps a disabled button with a stable explanatory tooltip.
- The Templates tab also exposes a per-row **Create new instance** wizard for QEMU and LXC templates. The action posts directly to proxbox-api (`/cloud/vm/provision` or `/cloud/lxc/provision`) through `views/proxmox_create_instance.py`, defaults QEMU to linked clone (`full_clone=false`), uses a 90-second request timeout, retries QEMU VMID collisions from the datacenter `next_id` hint, and runs `sync_individual("sync/individual/vm", ...)` afterward so the new VM/container appears in NetBox. Writes are gated in four layers: UI disables the button when `ProxmoxEndpoint.allow_writes=False`, the plugin view pre-checks the same flag before backend calls, proxbox-api 403 `reason`/`detail` is surfaced unchanged, and the view requires `core.run_proxmox_action` via `permission_run_proxmox_action()`.

## Bug-report anonymization

The failed-job **Bug report** modal exists so an operator can hand a sync
failure to a public issue tracker. A Proxbox sync error or log line routinely
carries Proxmox node hostnames and FQDNs, management addresses, API URLs,
`user@pam` realm principals, `PVEAPIToken` values, and `Authorization` headers,
so [`netbox_proxbox/anonymize.py`](./netbox_proxbox/anonymize.py) scrubs the
payload before it is rendered. Three invariants are load-bearing:

- **The prefilled GitHub URL is the real egress path.** `_build_issue_url()`
  embeds the report body in a `?body=` query parameter, so scrubbing only the
  modal textarea would still publish the raw text the moment the reporter clicks
  *Open a new issue*. `build_bug_report_context()` therefore scrubs the metadata,
  error, and log lines **first** and composes `report_text` and the issue URL
  from those already-scrubbed parts — including the over-length truncation
  branch, which is a separate code path. Never scrub the composed string instead;
  the two outputs must not be able to disagree.
- **One `Anonymizer` per report.** Placeholders are stable per instance
  (`<host-1>`, `<ip-2>`), so a node named in both the error and a log line keeps
  one token and the report stays correlatable. A fresh instance per field would
  renumber and destroy that.
- **Credential keys are matched by *marker*, in both `:` and `=` forms,
  anywhere in the text.** An enumerated key list missed `token_value` and
  `token_secret` -- field names on this plugin's own models -- and
  `X-Proxbox-API-Key`; anchoring the `:` form to the start of a line made it
  dead code, because `_format_log_lines` prepends `[timestamp] LEVEL ` before
  anything is scrubbed. A bare `Bearer <jwt>` is swept separately, since a
  credential quoted into prose has no key in front of it. Marker matching
  deliberately over-redacts (`tokenizer=` is redacted too): losing a word from
  a report is recoverable, publishing a credential is not.
- **One module owns the vocabulary, and there is only one matcher.**
  `netbox_proxbox/redaction.py` holds the markers, the authentication schemes,
  and the single-pass scanner both redactors use: `anonymize.py` for the public
  report, `views/error_utils.py` for the job log. They previously each carried a
  copy and drifted -- `error_utils` matched by marker while `anonymize` matched
  exact names, which is how `token_value` was caught in the job log and
  published to GitHub. The module is dependency-free (`re` and nothing else)
  because `anonymize` must stay importable without Django, and `error_utils` is
  only reachable through a package whose `__init__` needs it.
- **The marker is not searched for inside the key.** The scanner captures a
  whole candidate name and asks `is_sensitive_key` about it. Matching the marker
  inside the key was both slow and wrong: every occurrence of `token` in a long
  identifier run started a fresh scan to the end of it -- quadratic, and
  `"token_aaaa" * 20000` took ~34 s -- while the caps added to hide that cost
  silently dropped longer names, which is a disclosure regression because a
  Pydantic 422 renders arbitrary field names into `msg` and those land in the
  job log. It also needed a second spelling of the vocabulary as a regex
  fragment, and the two disagreed about separators, so `api__key` was a
  sensitive *key* that no text matcher caught. One matcher removes all three
  problems, and every length and separator cap with them.
- **A non-credential name is skipped by resuming after its separator, never
  after its value.** That keeps the pass linear on input like `a:a:a:...`, where
  a value would otherwise swallow the rest of the string, and it is what lets an
  assignment nested inside a non-credential one still be found:
  `input_value={'token': 'nbt_...'}` is exactly that shape, and consuming the
  outer value hid the credential completely.
- **A name may not span a space, except in a two-word marker.** Allowing
  arbitrary space-joined words redacted the tail of ordinary prose
  (`token_version mismatch: expected 2 got 1`) and produced candidates that
  overlapped the next real assignment and hid it. But forbidding spaces
  outright dropped `API key:` and `private key=`, which the previous
  implementation did match -- so the two-word markers are recognised as fixed
  literal pairs, which cannot join arbitrary text. Any other spaced name is
  still caught where it occurs, as a mapping key.
- **A value that is truncated, nested or long must not publish its remainder.**
  An unterminated quote fell through to the unquoted alternative and redacted
  only the first fragment; a JSON document embedded inside a JSON string is
  doubly escaped, where `\\` is an escaped backslash and reading it as a
  delimiter ended the value early; and a capped scheme sweep replaced exactly
  the cap and left the rest. Once a quote opens the value now runs to its real
  terminator or the end of the line, and the scheme sweep is uncapped.
- **Free text fails closed on a value echo; structured payloads do not.** A
  Pydantic error prints the rejected field on one line and `input_value='...'`
  on another, so free text has nothing to correlate them with -- and the echoed
  value is exactly where a rejected credential is. `is_sensitive_or_echo_key`
  therefore redacts it, while `redact_sensitive` keeps reading `loc` and can
  still tell a rejected token from a rejected integer. The one exception is an
  echo whose value is a *structure*: redacting there would replace only the
  opening fragment and expose the rest, so the scanner descends and matches the
  real name inside it.
- **An `Authorization` value is consumed whole, whatever the scheme.**
  Enumerating known schemes in the value branch matched `Token` alone and
  published the credential behind it -- and `Token` is the scheme NetBox's own
  API uses. Multi-line key material (PEM blocks, OpenSSH public keys) is swept
  separately, because the generic value stops at the first whitespace.
- **The `Authorization` rule fires only in header position** -- line start, or
  after the `[timestamp] LEVEL ` prefix `_format_log_lines` adds. Letting it
  match anywhere destroyed the reports it exists to enable: `Proxmox
  authorization: denied; missing Sys.Audit on /nodes/pve01/storage/local`
  collapsed to `<redacted>`, erasing the privilege, path and cause of exactly
  the permission failure being reported. Prose falls through to the generic
  rule, which takes only the first token.
- **Single-label node names are caught where something names them as a host**
  (`node=pve1`, `on node pve-node-01`), with a stop-word list so `node is not
  reachable` stays readable. A bare identifier in prose is still not caught --
  that is the documented best-effort limit.
- **A bracketed IPv6 URL authority is matched atomically.** A plain
  `[^/\s:?#]+` authority stops at the literal's first colon, which published
  most of a management address and left a fragment the IPv6 pass could no
  longer recognise.
- **Every quantifier that precedes a required literal is bounded.** Job logs
  carry remote-controlled text, so an unbounded greedy class in front of a
  literal that turns out to be absent makes the engine re-scan the tail from
  every start position -- quadratic, and reached from the job page. Four
  regexes had this shape; at 2,000 dotted labels (an 18 KB string)
  `_FQDN_RE` alone took ~2.1 s, versus ~17 ms bounded. Do not "simplify" a
  bound back to `+` or `*`.
- **`anonymize.py` must not import Django.** `tests/test_bug_report.py`
  exec-loads `bug_report.py` with only `core.choices` stubbed; it pre-seeds a
  stub `netbox_proxbox` package plus a path-loaded `netbox_proxbox.anonymize` in
  `sys.modules` so the import resolves from cache rather than executing the real
  package `__init__`. A Django import anywhere in that path breaks the harness.

Two deliberate limits, both documented in the module and surfaced to the user as
a "best-effort — review before submitting" caution in the modal:

- **Hostname matching uses a curated suffix allowlist** (`_HOST_SUFFIXES`) and
  lowercase-only labels. Matching "any trailing word" turned every dotted path in
  a traceback (`django.db.utils.OperationalError`) into `<host-1>`, destroying
  exactly the text a maintainer needs. A host under an unlisted TLD is missed
  when it appears bare; inside a URL it is still caught, because there the
  authority is identified positionally rather than by suffix.
- **A bare single-label node name in prose** (`pve-node-01`) is
  indistinguishable from any other identifier and is not scrubbed.

Version metadata (`netbox-proxbox`, `NetBox`) is excluded from scrubbing by
`_UNSCRUBBED_METADATA_LABELS`: a four-segment version is shaped exactly like an
IPv4 address and would otherwise be reported as `<ip-1>`.

The prefilled issue body is **budgeted per block**. Dropping the job logs is not
enough on its own: a single verbose backend traceback can exceed
`_MAX_ISSUE_BODY_CHARS` by itself, and an unbudgeted error produced a ~20,500
character body against a 6,000 limit -- which GitHub rejects or silently drops,
costing the reporter the prefill entirely. Metadata and error each have a
sub-budget and are truncated with an explicit notice; the full text always
remains in the clipboard copy.

A known, accepted limit: a credential key spelled with **homoglyphs**
(`passwоrd=` with a Cyrillic `о`) is not matched. Detecting that needs a
confusables table, and the spelling does not arise from the systems that
produce these logs.

## Backend integration notes

- **Single enabled FastAPI row:** HTTP and WebSocket helpers such as `get_fastapi_request_context()` in [`netbox_proxbox/services/backend_proxy.py`](./netbox_proxbox/services/backend_proxy.py), `websocket_client`, and several dashboard views resolve the backend via the first `FastAPIEndpoint` with `enabled=True` (or the first enabled row from a restricted queryset). If multiple enabled FastAPI endpoints exist, whichever row sorts first is used; plan automation and operator docs accordingly.
- **Backend-key preflight is a job-wide gate:** a manual or scheduled sync must
  authenticate the selected FastAPI endpoint before batch creation or SSE. The
  selected endpoint ID is then threaded through endpoint preflight, batch sync,
  and every pre-SSE service pass so no phase silently re-resolves a different
  enabled backend. Authentication failure aborts the entire job before any
  partial sync can start.
- **Background Proxbox sync jobs (RQ):** `ProxboxSyncJob` enqueues on NetBox’s **`default`** RQ queue (`RQ_QUEUE_DEFAULT`) so a stock **`manage.py rqworker`** (no queue arguments) picks them up. NetBox’s default worker only listens to **`high`**, **`default`**, and **`low`**; the extra django-rq queue **`netbox_proxbox.sync`** is legacy only. Older Job rows may still show **`netbox_proxbox.sync`** in **Queue**; cancel/RQ lookup uses the stored name. Jobs call proxbox-api **SSE** via [`run_sync_stream`](./netbox_proxbox/services/backend_proxy.py) until a terminal `complete` event.
- **Disabled endpoint rows are a hard no-connection gate:** any endpoint-like row with `enabled=False` (`ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `PBSEndpoint`, `PDMEndpoint`, or companion plugin endpoint objects such as `PBSServer`) remains visible through the API/UI for inventory, but operational paths must return before proxbox-api or remote-service network calls. This includes startup/signal pushes, OpenAPI fetches, keepalive/status probes, backend-id resolution, dashboard/API live reads, and scheduled/manual sync scopes. The sole control-plane exception is a normal `ProxmoxEndpoint.save()` while disabled: its post-save signal may authenticate to an already configured proxbox-api and update only an already existing backend row to `enabled=False, allow_packer_template_builds=False`. That policy revocation never contacts Proxmox, creates a backend row, or sends endpoint credentials. Bulk enable/disable deliberately remains local-only because it uses `queryset.update()` and fires no signal; endpoints carrying the narrow capability are excluded from bulk toggle/delete paths until a normal save revokes it.
  **The gate is decided from NetBox's own rows, never from what proxbox-api still
  holds.** The backend's stored endpoint state is not evidence that a disabled row
  is safe to use — it may carry credentials issued before the row was disabled, or
  credentials for a different NetBox instance entirely. Six sync-job behaviors
  enforce this explicitly and must not be relaxed: zero enabled `NetBoxEndpoint`
  rows block the preflight **unconditionally**, without consulting the backend's
  list at all; zero enabled `ProxmoxEndpoint` rows fail the run loudly rather than
  issuing an **unscoped** stage request, which proxbox-api would read as "sync every
  endpoint you hold"; a failed NetBox push with stored backend rows continues only
  when `backend_holds_netbox_endpoint()` proves a row points at *this* NetBox by
  **resolved connection target** — `(domain or ip_address)` plus `port`, exactly
  what proxbox-api's own `NetBoxEndpoint.url` property dials, so once a domain is
  set the address is a field nobody reads — and **never** by name, since the
  backend NetBox endpoint is a singleton updated by position and its name is free
  text, and **never** off the push payload, whose synthetic `127.0.0.1` fallback
  every domain-only NetBox sends identically — and identity alone is not enough,
  since a row can name this NetBox while describing a **superseded** posture, so
  `_netbox_row_is_current()` also requires the pushed `verify_ssl` and
  `token_version` to match and reads a *missing* one as drifted (the secret itself
  is not comparable: `NetBoxEndpointResponse` withholds `token`/`token_key`) —
  and because that singleton is **positional**, a listing returning more than
  one row is refused outright whatever those rows say: the push overwrites entry
  `[0]` and entry `[0]` is what the backend dials, so accepting a match found
  further down would vouch for a row proxbox-api is not using while a stale one
  ahead of it drives the sync;
  a failed NetBox push whose backend
  listing *also* failed blocks rather than warning, because "unknown" must not read
  as "ours" — unless some other enabled row pushed successfully, which already wrote
  this NetBox's credentials into the singleton; the selected-object **batch**
  sync path runs the same preflight before its first write, because it reaches
  proxbox-api through `sync_individual()` but writes NetBox objects identically;
  and that same batch path resolves the same enabled-`ProxmoxEndpoint` scope and
  refuses the run when none resolves, because the individual-sync routes take
  proxbox-api's `ProxmoxSessionsDep`, which reads a **missing**
  `proxmox_endpoint_ids` as "use every endpoint I hold" — so an unscoped
  selected-object sync is the *widest* request the backend accepts, not a
  narrower one, and the scope must also travel as an explicit argument through
  the recursive dependency syncs, whose `_CONTEXT_KEYS` rebuild would otherwise
  drop it. That job-wide scope is still not narrow enough on its own: a
  selected-object request names only a cluster/node/VMID, which are unique **per
  endpoint** and not across the estate, so each object is additionally pinned to
  the single backend id its own `ProxmoxCluster → ProxmoxEndpoint` chain names,
  an object whose owner was skipped from the scope is refused with HTTP 424
  rather than asked of the remaining endpoints, and so is an object whose cluster
  is claimed by **two or more** endpoints — that is proof the duplicated
  namespace exists here, so widening would ask both and keep whichever answered.
  An owner that cannot be determined **at all** — nothing has reflected this
  cluster yet — falls back to the job-wide scope only while that scope names a
  **single** endpoint, where falling back and pinning are the same request, so a
  first-ever sync can still discover it; a run spanning two or more endpoints
  refuses the object with 424 instead, because "we cannot tell who owns this" is
  not a licence to ask everybody in exactly the estate where a duplicated
  identifier is possible. *Unknown* and *ambiguous* remain deliberately different
  states — ambiguous never widens at all.
  Whatever those per-object refusals amount to, they also **fail the enclosing
  job**: every object in a selected-object run was named by an operator, so a
  non-zero `failed` count raises rather than finishing **completed** with the
  errors buried in `job.data` — after `job.data` is persisted, and before the
  branch merge, so a partial result is never promoted into main.
  Details in [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md) →
  `jobs.py`.
- **Disabled Proxmox status badges are static inventory state:** Proxmox endpoint list/detail/dashboard status elements must render a gray `Disabled` badge without `data-service-status-url` when `enabled=False`. Direct keepalive calls still return `status="disabled"` defensively, but the UI must not schedule status polling for disabled Proxmox rows.
- **RQ timeout vs HTTP stream:** NetBox’s default **`RQ_DEFAULT_TIMEOUT`** (often **300s** via `configuration.py`) applies to RQ jobs unless overridden. Long syncs were previously killed by RQ while `requests` was still reading the SSE body. The plugin sets a default **`job_timeout`** of **`PROXBOX_SYNC_JOB_TIMEOUT`** (7200s) in [`ProxboxSyncJob.enqueue`](./netbox_proxbox/jobs.py); pass a larger `job_timeout=` to `enqueue()` if needed. That is separate from the HTTP **between-chunk read** timeout (3600s) inside [`run_sync_stream`](./netbox_proxbox/services/backend_proxy.py).
- **HTTP timeouts for large syncs:** VM sync operations and full-update runs use a 3600-second (1-hour) read timeout instead of the default 5 seconds. VMs with 50+ interfaces require extended time because each interface needs multiple sequential API calls to NetBox (VLAN, bridge, MAC, IPs). See [`http_timeout_for_sync_path`](./netbox_proxbox/services/backend_auth.py) for timeout configuration per sync path.
- **When a job looks “stuck”:** **pending** usually means **no RQ worker** is running (or it does not listen to **`default`**). **running** for a long time usually means proxbox-api is still syncing or the stream is slow/buffered; **errored** with **`JobTimeoutException`** means RQ’s wall-clock limit was hit—increase `job_timeout` or `PROXBOX_SYNC_JOB_TIMEOUT`. Inspect the job **log** and **error** fields before changing code.
- **Cancel on Job detail:** For Proxbox Sync rows in **pending**, **scheduled**, or **running** state, the plugin adds **Cancel job** (POST to `proxbox-cancel`). It requires **delete** permission on the core **Job** model, cancels or stops the linked RQ job when possible, then marks the NetBox job **failed** with a “Cancelled by user.” message. Stopping a **running** job is best-effort (RQ stop + long HTTP reads may not abort instantly). The same logic is exposed as a **REST endpoint** — `POST /api/plugins/proxbox/jobs/<pk>/cancel/` (`api/jobs.py::ProxboxJobCancelAPIView`, gated on `core.delete_job`) — so a stuck/zombie sync `core.Job` (one left `running` by a dead RQ worker whose timeout never fired) can be cleared through the nms-backend proxy without the UI or SSH: today via `nms virt raw POST jobs/<pk>/cancel/`, and via the first-class `nms virt cancel-job <pk>` wrapper once the paired nms-cli command ships. It reuses the exact UI cancel helper; a terminal job is a safe no-op.
- **Run now on Job detail:** Shown only when the job is in a **terminal** state (**completed**, **errored**, or **failed**), including after **Cancel** (failed). It is **not** shown for **pending**, **scheduled**, or **running**—use **Cancel** first if a queued run should be abandoned, then **Run now** on the finished row to queue a new sync with the same parameters.
- **Full update (UI vs jobs):** The plugin home may still use non-streaming helpers such as [`sync_full_update_resource`](./netbox_proxbox/services/backend_proxy.py) for JSON/redirect flows. Scheduled or immediate **Proxbox Sync** jobs expand selected sync types in [`sync_types.py`](./netbox_proxbox/sync_types.py) and call one backend `/stream` path per stage: devices, storage, virtual machines, task history, virtual disks, backups, snapshots, network interfaces, VM interfaces, IP addresses, SDN, replications, and backup routines. The VM-stage request always carries `sync_task_history=false`; the dedicated supplementary task-history stage is its only owner, preventing duplicate discovery and keeping task-history failures out of the required VM stage. This pairs with the proxbox-api bounded task-history implementation: deploy the wire-compatible backend first and the plugin second; plugin-first is non-breaking but leaves the timeout remediation incomplete until the backend is upgraded. The SDN stage is included by **All** but skipped by default while `sync_mode_sdn=disabled`; optional BGP projection inside that stage is separately gated by `sync_mode_sdn_bgp`.
- **Proxmox connection tuning is resolved by the endpoint model:** nullable `ProxmoxEndpoint.timeout`, `max_retries`, and `retry_backoff` fields inherit the matching `ProxboxPluginSettings` values through `effective_connection_tuning()`. Endpoint values win whenever they are not `None`, including zero retries/back-off. Backend registration must send those concrete resolved values and never forward inheritance as JSON `null`. `backend_holds_proxmox_endpoint()` compares all three public tuning values before the soft preflight budget may skip a refresh; otherwise a global default change could leave proxbox-api using an old request timeout indefinitely.
- **`ip-addresses` implies `vm-interfaces` (stage dependency).** `expanded_sync_stages()` auto-appends the **VM interfaces** stage whenever **IP addresses** is selected without it (mirroring the `network-interfaces` → `vm-interfaces` bundle). The backend IP stage (`proxbox-api` `_sync_vm_ips`) can only attach an IP to a VM interface that already exists in NetBox and silently skips the IP otherwise, so an IP-only run whose interfaces are stale/missing would reconcile nothing. Stage ordering (`_STAGE_ORDER_INDEX`) keeps interfaces before IPs, and the `vm_interface` → `ip_address` sync-mode cascade still skips both when `sync_mode_vm_interface=disabled`. **All** already ran interfaces before IPs, so it is unaffected.
- **VM interface sync strategy forwarding.** `_build_base_query_params()` sends both `use_guest_agent_interface_name` and `vm_interface_sync_strategy` to proxbox-api. New backend writers should honor `guest_os_model` by creating/updating `GuestVMInterface` and `GuestVMInterfaceAddress` through `/api/plugins/proxbox/guest-vm-interfaces/` and `/api/plugins/proxbox/guest-vm-interface-addresses/`, while preserving core `VMInterface` names from Proxmox config.

### SSL Certificate Verification

The `verify_ssl` setting that controls whether proxbox-api verifies NetBox's SSL certificate **belongs in proxbox-api, not in this plugin**. It is configured in the proxbox-api admin UI (typically `http://proxbox-api-host:8000`), not in the NetBox plugin settings.

**Common mistake:** Users encountering SSL verification errors may look for the setting in the NetBox Proxbox plugin or the `FastAPIEndpoint.verify_ssl` field in NetBox. These are incorrect locations. The relevant setting is:
- **In:** proxbox-api admin UI → **NetBox Endpoint** → **Verify SSL** checkbox
- **Not in:** NetBox Proxbox plugin settings
- **Not in:** `FastAPIEndpoint.verify_ssl` (that field controls the plugin's connection to proxbox-api, not proxbox-api's connection to NetBox)

**Minimum version:** proxbox-api **v0.0.14+** (released May 2026) is required for SSL verification settings to work correctly. Earlier versions had a bug where `verify_ssl=False` was ignored due to missing database migrations and incorrect connector logic. If you are experiencing "SSL certificate verify failed" errors despite unchecking `verify_ssl` in the proxbox-api admin UI, upgrade to **v0.0.14 or later** (see [issue #544](https://github.com/emersonfelipesp/netbox-proxbox/issues/544) for details).

**Manual workaround** (before upgrading):
```bash
sqlite3 /path/to/proxbox-api/database.db \
  "UPDATE netboxendpoint SET verify_ssl = 0 WHERE name = 'your-endpoint-name';"
```
Then restart proxbox-api.

## Plugin settings and configuration

**Configuration policy — prefer DB-backed plugin settings.**
When adding a new runtime tunable that proxbox-api or this plugin needs to read,
default to making it a [`ProxboxPluginSettings`](./netbox_proxbox/models/plugin_settings.py)
field (NetBox-UI-editable, persisted in the NetBox database). On the proxbox-api side
it is read via `proxbox_api.runtime_settings.get_int / get_float / get_bool / get_str`,
which resolves **env var (override) → `ProxboxPluginSettings` → built-in default**
with a 5-minute settings cache.

Only fall back to a pure `.env` variable on the backend when the value is needed
**before** the NetBox connection exists or is **operator-only infrastructure** that
has no business in the UI: `PROXBOX_BIND_HOST`, `PROXBOX_RATE_LIMIT`,
`PROXBOX_ENCRYPTION_KEY` / `PROXBOX_ENCRYPTION_KEY_FILE`, `PROXBOX_STRICT_STARTUP`,
`PROXBOX_SKIP_NETBOX_BOOTSTRAP`, `PROXBOX_GENERATED_DIR`,
`PROXBOX_CORS_EXTRA_ORIGINS`. Anything that controls sync behavior, batching,
concurrency, caching, or feature toggles belongs in `ProxboxPluginSettings`.

Do **not** invent shadow config layers (parallel JSON/YAML files, ad-hoc dotenv
sections, module-level constants meant as overrides) to dodge the migration cost.
A new field touches all five wiring points — model, migration, form, serializer, and
template — and the existing fields plus migration
[`0037_v0_0_15_release.py`](./netbox_proxbox/migrations/0037_v0_0_15_release.py)
show the pattern (`SeparateDatabaseAndState` + `IF NOT EXISTS` for production-safe
additive schema changes).

SSH-discovered physical-NIC MAC writes use the dedicated
`hardware_discovery_sync_nic_macs` plugin setting. It defaults to `False` and
is effective only when the existing `hardware_discovery_enabled` master flag is
also `True`. This separate opt-in prevents an upgrade from creating native
`dcim.MACAddress` rows for operators who previously enabled discovery only for
chassis and NIC link facts.

## Sync Mode Controls

Per-resource sync modes let operators control how each Proxmox resource type is
reflected into NetBox. Three modes are available:

- **`always`** (default) — sync on every run; objects are created, updated, and deleted as Proxmox changes.
- **`bootstrap_only`** — sync the object once on first discovery, tag it with `bootstrap-only` in NetBox, and leave it completely untouched on all subsequent runs.
- **`disabled`** — skip this resource type entirely; existing objects are not modified or removed.

Controlled resource types: `sync_mode_vm`, `sync_mode_vm_template`, `sync_mode_vm_interface`, `sync_mode_mac`, `sync_mode_cluster`, `sync_mode_node`, `sync_mode_storage`, `sync_mode_ip_address`, `sync_mode_sdn`, `sync_mode_sdn_bgp`.

`sync_mode_sdn` and `sync_mode_sdn_bgp` default to `disabled` globally and per
endpoint. The **All** sync option includes the SDN stage after VM
interface/IP-address stages, but that stage is skipped until the effective SDN
mode is enabled. SDN sync is read-only against Proxmox: it reflects
controllers, zones, VNets, subnets, fabrics, route maps, prefix lists, and
runtime bindings into NetBox plugin metadata, and it maps EVPN/VXLAN VNets into
NetBox built-ins (`vpn.L2VPN`, `vpn.L2VPNTermination`, `ipam.RouteTarget`,
`ipam.Prefix`) when enough source data is available. `sync_mode_sdn_bgp`
controls optional projection of SDN BGP data into the `netbox_bgp` plugin inside
the SDN stage and is forced disabled whenever `sync_mode_sdn` is disabled.
Unsupported older Proxmox clusters are counted as skipped warnings, not failed
syncs.

Resolution priority: **endpoint-level setting takes priority over the global default**. An endpoint field set to null inherits the global `ProxboxPluginSettings` value.

Effective sync modes resolve through a parent-to-child cascade before stage gating and backend query forwarding. A resource is effectively `disabled` when its own mode is `disabled` or any ancestor is effectively `disabled`; child modes never affect parent modes. The hierarchy is:

```
cluster
└── node

vm + vm_template (both disabled only)
└── vm_interface
    ├── ip_address
    └── mac

sdn
└── sdn_bgp
```

### VM Templates

Proxmox VM templates (`template=True` in the Proxmox API) are stored in the dedicated `ProxmoxVMTemplate` model, NOT as `virtualization.VirtualMachine` rows. Key fields:

- `proxmox_endpoint` (required FK → ProxmoxEndpoint)
- `cluster`, `node` (optional FKs, SET_NULL)
- `source_vm` (optional FK → VirtualMachine, SET_NULL) — the VM this template was made from
- `cloned_vms` (optional M2M → VirtualMachine) — VMs cloned from this template
- Full config snapshot: `vcpus`, `memory`, `disk`, `os_type`, `net_config`, `disk_config`, `raw_config`

`sync_mode_vm` and `sync_mode_vm_template` are independent — disabling VMs does not disable template sync.
Per-record VM/template filtering is enforced by the proxbox-api backend
(proxbox-api >= 0.0.18) from the `sync_mode_vm` and `sync_mode_vm_template`
query parameters the plugin forwards on stage requests. The plugin only applies
whole-stage skip behavior; the `virtual-machines` stage is skipped entirely only
when both VM and VM-template modes are `disabled`.

### Bootstrap-only tag

The `bootstrap-only` tag (slug `bootstrap-only`) is auto-created by `netbox_proxbox/netbox_bootstrap.py`. The tag is attached to objects when they are first created in `bootstrap_only` mode. Removing the tag manually causes the next sync to treat the object as a normal `always`-mode resource.

### Key files

- `netbox_proxbox/choices.py` — `SyncModeChoices` (always / bootstrap_only / disabled)
- `netbox_proxbox/constants.py` — `SYNC_MODE_FIELDS`, `SYNC_MODE_RESOURCE_TYPES`
- `netbox_proxbox/models/plugin_settings.py` — global `sync_mode_*` fields
- `netbox_proxbox/models/proxmox_endpoint.py` — per-endpoint nullable `sync_mode_*` fields + `effective_sync_mode(resource_type)` method
- `netbox_proxbox/models/vm_template.py` — `ProxmoxVMTemplate` model
- `netbox_proxbox/migrations/0046_sync_modes.py` — migration for sync mode fields
- `netbox_proxbox/migrations/0047_proxmox_vm_template.py` — migration for ProxmoxVMTemplate table
- `netbox_proxbox/migrations/0055_sdn_sync_controls_and_inventory.py` — SDN sync mode and SDN inventory tables
- `netbox_proxbox/models/sdn_inventory.py` — Proxmox SDN controller/zone/VNet/subnet/binding metadata
- `netbox_proxbox/sync_stages.py` — `_has_bootstrap_only_tag()`, `_bootstrap_only_should_skip_existing()`, `_add_bootstrap_only_tag()`
- `netbox_proxbox/netbox_bootstrap.py` — `ensure_proxbox_tags()`, `ensure_bootstrap_only_tag()`
- `netbox_proxbox/services/sync_vm_template.py` — `sync_vm_templates()` service
- `docs/configuration/sync-modes.md` — user-facing documentation

## CI/CD Workflows

Gitea pull-request CI serializes `docs-and-package` after `quality` on the
capacity-bounded `ci-untrusted-python312` host. One fixed concurrency group
covers every ref without auto-cancellation, so feature churn cannot preempt
protected-branch or immutable-tag evidence. Both jobs must require 384 MiB free
and log measured/required KiB before environment creation. This floor preserves
more than 150 MiB above the measured 195,498 KiB quality environment and 42,021
KiB source tree. Keep `UV_NO_CACHE=1`, and always clean environments, tool
caches, outputs, and generated bytecode. Quality uses the optional `test`,
`dev`, and `cli` extras
with `--no-dev`; the similarly named dependency-group `dev` contains MkDocs and
is owned only by the docs job together with the exact `publish` packaging group.
Distribution builds must use `--no-isolation` so the build backend also comes
from that lock. Do not parallelize these environments, float package tools, or
restore a persistent workspace uv cache without proving runner capacity first.
Both jobs must run `ci/clean-generated-workspace.sh startup` immediately after
checkout. It removes stale managed state before use and fails closed after
safely unlinking any generated-state symlink without traversing its target.

### Authenticated Django matrix bootstrap (issue #300; no consumer)

`scripts/wait_for_github_django_matrix.py` is a reviewed target-branch artifact
for a future **base-pinned external supervisor**. Prefer base-owned credential
ingress through `GH_MATRIX_READ_TOKEN_FILE`, naming a private file readable only
by the waiter; `GH_MATRIX_READ_TOKEN` remains a fallback. The waiter verifies
that the base-owner GitHub App user access token exposes exactly one app
installation with the expected owner, exact read permissions, and
single-repository selection,
pins `.github/workflows/django-tests.yml` by Git blob identity, and accepts only
the successful `push` attempt matching the trusted candidate branch, full SHA,
repository, GitHub's bare workflow path, and required expected run-ID/attempt
pair. A UTC not-before time is only an optional additional bound. Discovery
polls only `/actions/runs/{run_id}/attempts/{attempt}` from the outset and
treats 404 as a bounded not-yet-visible state, so workflow-run list ordering or
flooding cannot displace the trusted pair. Branch provenance is independently
bound by `head_branch` and the exact run-name ref. All API I/O, parsing,
retries, rate-limit handling, and polling share one deadline and a hard request
budget.

When `django-tests.yml` changes, the waiter retains the previously reviewed
blob pin. The workflow lands and is reviewed first; a second, separately
reviewed base-artifact change may then update the pin. Candidate code never
self-authorizes its own workflow blob.

Environment fallback ingress cannot erase the token from the process's
original environment block: same-runner processes with proc access can still
read it from `/proc/<pid>/environ`, and Python startup hooks run before the
waiter can remove it. File ingress avoids those environment exposures. Process
and namespace isolation are external-supervisor obligations that this waiter
cannot enforce.

This commit intentionally has no Gitea caller. The public matrix remains
**non-security evidence** because candidate code owns the installed package and
tests; the workflow pin alone does not change that boundary. A consumer may be
enabled only in a later reviewed change after the external supervisor is
base-pinned and the token is proven to remain outside every candidate checkout,
environment, process, and log. Keep the architecture and bootstrap order in
[`docs/developer/ci-e2e-workflows.md`](./docs/developer/ci-e2e-workflows.md)
aligned with the script and tests.

Within that non-security evidence boundary, every NetBox source-matrix row must
remain reproducible: pin the checkout by full commit, verify its
`netbox/release.yaml` identity and upstream `requirements.txt` checksum, and
install the matching reviewed Python 3.12/Linux lock from
`ci/netbox-requirements/` with artifact hashes, an explicit PyPI first-index
policy, and the repository-pinned uv version. Update the `.in` snapshot, lock,
matrix metadata, source-contract tests, and compatibility docs together.

### Gitea-to-GitHub mirror (`.gitea/workflows/mirror-github.yml`)

Gitea is the source of truth for normal branch work. The mirror workflow runs
from Gitea Actions and mirrors only the approved branches to the equivalent
GitHub repository: `develop` and `main`. `develop` is the staging branch and
`main` is the production branch.

The job requires the Gitea Actions secrets `GH_MIRROR_TOKEN` for GitHub and
`SOURCE_MIRROR_TOKEN` for authenticated Gitea source fetches, plus the
dedicated `mirror-host` runner label. It installs `gh` when missing,
authenticates with `gh`, validates the GitHub repo, configures GitHub git
credentials with `gh auth setup-git`, and pushes only
`HEAD:refs/heads/${{ gitea.ref_name }}`. It must never sync tags, use
`git push --all`, or use `git push --mirror`.

### Gitea Package Registry publish (`.gitea/workflows/publish-gitea.yml`)

Handles `push: tags:` only. It deliberately does not subscribe to Gitea's
overlapping `create` event: Gitea emits both events for one tag, which would
race duplicate immutable release requests. The tag must equal current
`develop`; writer-controlled commit statuses are ignored, and the newest
authenticated `ci.yml` Actions run plus its required jobs must prove a
successful first push attempt for that exact SHA,
trusted actor, expected job, and the exact sole `ci-untrusted-python312` runner
label. The two release-request jobs themselves use the repository-unique
`ci-release-netbox-proxbox` label so user/organization runners cannot satisfy
release evidence. Workflow concurrency is global to this repository, preventing
different release refs from racing the sole release label. Before candidate
processing, both jobs run a checksum-pinned
gate that requires the live runner ID, name, and sole label to equal the
canonical acceptance record plus a fresh signed external-supervisor attestation
bound to repository/first-attempt run/job/source and the exact workflow
path/digest, complete registered labels, runtime image, and network/runtime
policy. Validation and build have independent pinned
repository-registration scope digests. Zero/empty identity and all-zero key/image/policy
digests keep tag releases disabled. Both jobs are explicitly
limited to `actions: read` and `contents: read`, and the build's step-scoped
Gitea token is not passed across the candidate boundary. The build fetches the
validated public source without checkout credentials.
Because this repository is public, Gitea's repository permission floor can
still authorize a job token to read public Actions data even when the job omits
that scope; do not claim otherwise. Gitea also injects an artifact runtime token
into the outer job. The enforced boundary therefore runs all candidate-controlled
dependency installation, PEP 517 build, Twine check, and manifest generation as
a separate numeric UID with a minimal allowlisted environment, no-new-privileges
and resource limits, no read access to the root parent's `/proc/.../environ`,
and post-build process cleanup. A fail-closed x86-64 Landlock ABI 3+ ruleset permits
filesystem writes only below the per-run build root, so candidate code cannot
modify runner workflow-command files or consume shared writable temporary
storage. A fail-closed x86-64 seccomp filter denies every candidate socket
syscall, all `io_uring` entry points, and every x32-tagged syscall; all three
paths are live-probed before dependency/build code. The immutable
wheelhouse manifest is revalidated in-container, and the locked publish group
includes Hatchling for the configured PEP 517 backend. The
`ci-release-netbox-proxbox` activation canary must separately prove
that the exact repository-scoped release runner/container denies management and
production network access and bind that immutable result plus the runtime
digest to the same runner ID in the acceptance record; an online runner label
alone is insufficient evidence. The supervisor must sign fresh job-bound
evidence so a historical canary cannot authorize drift after restart.
Only reviewed outer shell/Python code
regains the runtime-bearing environment. Candidate output is captured with a one-MiB limit
and is never relayed raw to the runner command parser; legacy `set-env` and
`add-path` probes must not affect the next step. The job fails closed unless
cgroup v2 proves hard one-CPU/2-GiB/zero-swap/64-PID ceilings and `/nmc-build` is a hard
one-GiB/50,000-inode tmpfs. A 900-second wall limit therefore bounds cumulative
CPU; live-plus-reaped CPU/RSS/PID, logical-size/filesystem-block/file-count,
per-process memory/CPU/file-size, and descriptor checks provide defense in
depth. Linux CPU
records are parsed after the process-name delimiter so whitespace in a candidate
process name cannot evade aggregate accounting. The outer handoff opens the exact
two artifacts and manifest through no-follow directory/file descriptors,
requires bounded regular files only, copies exact names, and independently
re-hashes the copies before upload. After candidate process cleanup, the
root-only external supervisor signs a canonical completion statement binding
the initial attestation, its independently derived repository-registration
scope digest, live job/runner policy, request digest, and every final artifact
byte; candidate code cannot access its signer socket. The target client and
controller require that signed scope digest to equal the pinned acceptance
value. Candidate code
receives no package, mirror, job, runtime, or write credential.

Two job-bound ephemeral `ci-release-netbox-proxbox` registrations provide
distinct validation and build runner identities; each advertises only that
release label and terminates after its one assigned job. Every RC, final, or
> **Current state — publication is restored to in-repository jobs.**
> The locked control plane described below is **implemented and reviewed
> in-tree but not active**, because the isolated runner fleet it requires
> (`ci-release-netbox-proxbox`, `release-builder`, `release-publisher`) does not
> exist — no runner in the estate advertises those labels, and
> `N-MultiCloud/release-control` has zero runners. `.gitea/workflows/publish-gitea.yml`
> therefore publishes directly on the existing `mirror-host` runner: it builds
> the wheel/sdist, uploads to the Gitea Package Registry, verifies the package,
> pushes the tag to the authorised GitHub repository, and creates the GitHub
> Release for final tags only.
>
> This restores the path that shipped `0.0.23`. It is a deliberate, tracked
> deferral of the hardening, not a regression, and it is consistent with the
> rule stated below: an unprovisioned control repository is a release freeze,
> not a reason to remove publication. Re-landing the control plane is tracked as
> a follow-up and requires the runner fleet first.

post request requires a freshly registered and reviewed pair. The build job produces
the manifest-bound wheel/sdist and uploads
exactly six data files: wheel, sdist,
`release-manifest.json`, canonical `release-request.json`, canonical
`runner-completion-attestation.json`, and
`runner-completion-attestation.sig`. The request
binds repository ID, source/tag/version, first-attempt run identity, target
workflow digest, manifest digest, and artifact inventory. The target workflow
has no package or GitHub-mirror credential and cannot publish or push tags.
The separately administered `N-MultiCloud/release-control` workflow must be
manually dispatched with this repository name, the exact target run ID, and
the request SHA-256. Its isolated builder independently verifies the
policy-pinned target workflow, supervisor completion signature, and sealed bytes; only its isolated publisher
can read the package/mirror credentials or invoke the fixed digest-locked
publication tooling. Public no-authority downloads must match the manifest
before the durable ledger advances.

Do not merge this data-only target cutover until the private control repository
has a positive policy-pinned repository ID and its protected workflows, host
boundaries, sockets, and repository-scoped runners have passed readiness checks.
Until then the existing target publisher must remain active; an unprovisioned
control repository is a release freeze, not a reason to remove publication.

The control plane pushes only RC tags to GitHub so the RC-only public tag
trigger can validate TestPyPI. Final tags stay private until the exact Gitea
package is linked, verified, and deployed through NMS using `latest_package` by default.
Only after production validation may canonical-main `promote-final-tag.yml`
verify the package and host-issued deployment receipt and push the final tag to the exact
authorized GitHub repository; the operator then creates the GitHub Release
that authorizes PyPI.

### Branch-tier deployment (`.gitea/workflows/deploy-production.yml`)

Pushes to `develop` deploy this plugin to the staging NetBox endpoint at
`https://staging.netbox.nmulti.cloud`. Production is an NMS-dispatched manual
workflow on canonical `main`: `latest_package` requires the exact Gitea version
and is the default; `main_branch` is an explicit override. After a healthy
package deployment, the root-owned fixed helper emits schema-2 completion
evidence containing the source SHA, exact artifact hashes, manifest digest,
observed versioned import path, production environment, and workflow-run
identity. The workflow may only export, validate, and publish those host-issued
bytes; it cannot construct production evidence itself.

### E2E Docker workflow (`e2e-docker.yml`)

Accepts four main inputs:

| Input | Values | Default | Effect |
|-------|--------|---------|--------|
| `install_source` | `local`, `pypi`, `testpypi`, `container`, `both` | `both` | How netbox-proxbox is installed inside the NetBox container |
| `dependency_mode` | `dev`, `published`, `testpypi-package`, `pypi-package` | `dev` | How the separate proxbox-api container is built or installed |
| `proxbox_api_version` | version string | `PROXBOX_API_RELEASE_VERSION` fallback | Exact proxbox-api version for package-index E2E modes |
| `netbox_image` | full image ref | NetBox matrix | NetBox image override for focused runs |

**`dependency_mode: dev`** — clones `emersonfelipesp/proxbox-api` at HEAD and builds the `raw` Docker target locally. Use this for pre-publish E2E to verify against the latest source.

**`dependency_mode: published`** — pulls `emersonfelipesp/proxbox-api:<PROXBOX_API_RELEASE_VERSION>` from Docker Hub. Use this for post-publish E2E to verify the released image works end-to-end.

**`dependency_mode: testpypi-package`** — builds a temporary proxbox-api container by installing `proxbox-api==<proxbox_api_version>` from TestPyPI.

**`dependency_mode: pypi-package`** — builds a temporary proxbox-api container by installing `proxbox-api==<proxbox_api_version>` from PyPI.

### Release pipeline (`publish-testpypi.yml`)

```
prepare-release (downloads exact linked Gitea artifacts; final requires the protected host-issued deployment receipt)
├── validate-gitea-artifacts (wheel + sdist on Python 3.12/3.13)
├── TestPyPI lane
│   ├── publish-testpypi
│   ├── validate-testpypi
│   └── e2e-docker-testpypi (install_source=testpypi, dependency_mode=testpypi-package)
└── PyPI lane
    ├── validate-pypi-candidate
    ├── e2e-docker-pypi-candidate (install_source=local, dependency_mode=pypi-package)
    ├── publish-pypi
    ├── validate-pypi
    └── e2e-docker-pypi (install_source=pypi, dependency_mode=pypi-package)
```

`rcN` tag pushes (pattern `v*rc*`) publish to TestPyPI for release-candidate validation. **Official releases (`vX.Y.Z`, `vX.Y.Z.postN`) are triggered exclusively by GitHub release creation (`release: published`) — non-rc plain tag pushes no longer trigger the publish workflow.** Manual dispatch is TestPyPI-only and requires an RC version.

TestPyPI validation installs both `netbox-proxbox` and the configured `proxbox-api` from TestPyPI. PyPI candidate/final validation uses PyPI `proxbox-api` for backend package-index E2E.

Package uploads intentionally do not use `twine --skip-existing`; if a version is consumed by TestPyPI/PyPI and validation later fails, fix forward with the next `.postN` or `rcN`.

For public docs, keep [`docs/developer/ci-e2e-workflows.md`](./docs/developer/ci-e2e-workflows.md) and [`docs/developer/release-publishing.md`](./docs/developer/release-publishing.md) aligned with this section.

### Release Procedure (manual steps around the workflow)

**Two trigger rules — official releases use the immutable tag created from the
reviewed `develop` commit, after package-first production validation.**

| Trigger | Use for | Publishes to |
|---------|---------|--------------|
| `push: tags: v*rc*` (plain tag push) | Release candidates `vX.Y.ZrcN` | TestPyPI |
| `release: published` (GitHub release) | Official `vX.Y.Z` and `vX.Y.Z.postN` | PyPI (created by the operator after the NMS production gate) |

Plain non-rc tag pushes (`vX.Y.Z`, `vX.Y.Z.postN`) **do not** trigger the
publish workflow — the trigger pattern is `v*rc*`, so only rc tags fire it.
This makes the GitHub release creation the **single, authoritative trigger**
for official PyPI publishing and eliminates the duplicate-run problem the
old dual-trigger flow created.

`.gitea/workflows/publish-gitea.yml` only emits the six-file signed data request. The
locked control plane publishes the exact Gitea bytes and pushes RC tags to
GitHub, but deliberately does not promote final tags or create public
releases. Final promotion remains an operator action after Gitea-package
verification and the NMS package-first production health gate.

**RC flow (TestPyPI gate, repeatable):**

1. From an rc branch, bump to `X.Y.ZrcN` in `pyproject.toml`,
   `netbox_proxbox/__init__.py`, and `uv.lock`. Local verify:
   ```bash
   python -m compileall netbox_proxbox tests
   rtk ruff check .
   rtk pytest -p no:django tests/
   ```
2. Create the annotated tag and push it to Gitea. Wait for the target workflow,
   hash its canonical `release-request.json`, then dispatch the locked
   `validate.yml` workflow with `repository=netbox-proxbox`, its exact run ID,
   and that request SHA-256. After validation succeeds, dispatch the separate
   irreversible `publish.yml` workflow with the same three exact inputs. The
   control publisher promotes only the RC tag to GitHub:
   ```bash
   git tag -a vX.Y.ZrcN -m "Release vX.Y.ZrcN"
   git push gitea vX.Y.ZrcN
   gh run watch <run-id> --repo emersonfelipesp/netbox-proxbox
   ```
3. If anything fails, fix-forward with `rcN+1` — never `twine --skip-existing`.

**Official-release flow (cut from `develop`):**

1. **Merge the validated rc line into `develop`.** Once `rcN` is green on
   TestPyPI + the full E2E matrix + Page Coverage, bump versions on the rc
   branch to the final `X.Y.Z`, commit, then merge that branch into
   `develop` with a normal merge commit (`git merge --no-ff`). Push
   `develop`. The released version's commits MUST be on `develop` before
   the GitHub release is created.
2. **Verify `develop` has the version bumps you intend to release:**
   ```bash
   git log --oneline origin/develop | head -5
   grep '^version' pyproject.toml
   grep 'version = ' netbox_proxbox/__init__.py
   ```
3. **Publish and verify the final package in Gitea, then deploy it through NMS.**
   Use the target's default `latest_package` source; `main_branch` is permitted
   only when explicitly selected by the operator. Validate production health
   before public promotion.
4. **Promote the exact final tag and create the GitHub release.**
   This is the only step that fires the public publish workflow:
   ```bash
   gh release create vX.Y.Z \
     --repo emersonfelipesp/netbox-proxbox \
     --verify-tag \
     --title vX.Y.Z \
     --notes-file docs/release-notes/version-X.Y.Z.md
   ```
   - `--verify-tag` is mandatory. Push the final tag to the authorized GitHub
     repository only after the NMS gate; never let `gh release create` invent or
     move the tag.
   - Use `--notes-file` to point at the curated release notes; fall back to
     `--generate-notes` only for posts that have no curated file.
5. **Watch the publish run:**
   ```bash
   gh run list --repo emersonfelipesp/netbox-proxbox --event release \
     --limit 3 --json databaseId,name,status,conclusion
   gh run watch <run-id> --repo emersonfelipesp/netbox-proxbox
   ```
6. **Verify the dist is live on PyPI:**
   ```bash
   curl -s https://pypi.org/pypi/netbox-proxbox/json | jq '.releases | keys'
   ```
7. **Delete the rc branch** (local + remote) once PyPI is green. Only
   `develop` and `gh-pages` should remain on `origin`.

**Do not:**

- Do not push a non-rc tag with `git push origin vX.Y.Z` and expect publish
  to fire. The trigger pattern is `v*rc*`; the tag push will succeed on
  GitHub but no workflow runs. Use `gh release create` instead.
- Do not cut official releases from a `release/*` or `vX.Y.Z` branch and
  then merge into `develop` afterwards. The new policy is the reverse:
  land on `develop` first, then create the GitHub release pointing at
  `develop`.
- Do not add `twine --skip-existing`. Fix forward with `.postN` per PEP 440.
- Do not force-push to a published tag. Tags on the remote are immutable.

What was done for v0.0.17 (first release under the develop-first policy):

- `0.0.17rc1` → `0.0.17rc10` cycled on TestPyPI via `push: tags: v*rc*`
  fix-forward until Page Coverage + full E2E matrix (NetBox v4.5.8 / v4.5.9
  / v4.6.0 × pve/pbs/pdm) + TestPyPI validate all went green.
- Merged `release/v0.0.17` into `develop` with a normal merge commit
  resolving the firewall.py conflict (took the `_choices_2tuple` helper
  side, the validated rc10 fix). Pushed `develop`.
- Created the GitHub release with
  `gh release create v0.0.17 --repo emersonfelipesp/netbox-proxbox
  --target develop --verify-tag --title v0.0.17 --notes-file
  docs/release-notes/version-0.0.17.md`. That single command fired the
  `release: published` event and the publish workflow. **No duplicate run
  to cancel** — the workflow trigger had already been narrowed to
  `v*rc*` plus `release: published`, so the tag itself (which existed at
  the rc10 commit before `gh release create`) did not re-fire publish.
- Deleted the `release/v0.0.17` branch locally and on the remote.

What was done for v0.0.16 / v0.0.16.post3 (legacy dual-trigger flow):

- Released `0.0.16`, `0.0.16.post1`, `0.0.16.post2`, and `0.0.16.post3`
  in sequence (PEP 440 fix-forward — never `twine --skip-existing`). Final
  PyPI dist is `netbox-proxbox 0.0.16.post3`.
- After PyPI was green, merged the `v0.0.16` branch into `develop` via a
  two-parent merge commit (`merge --no-ff`, parents `[136966c, 934fd8a]`).
  Pushed the resulting commit (`4eec556`) as a fast-forward of `develop`.
- Created the GitHub release with
  `gh release create v0.0.16.post3 --repo emersonfelipesp/netbox-proxbox
  --title v0.0.16.post3 --generate-notes`.
- Cancelled the duplicate `Release validation and publish` run that the
  GitHub release spawned with `gh run cancel`. **This duplicate-run cancel
  step is no longer needed under the v0.0.17+ workflow trigger config.**
- Deleted the `v0.0.16` branch locally and on the remote. Only `develop`
  and `gh-pages` remain on origin.

What was done for v0.0.16.post4 → v0.0.16.post6 (fix-forward series):

- **v0.0.16.post4** — migration squash: folded migrations 0038–0047 into
  `0038_v0_0_16_release` so fresh installs run one squashed migration instead of
  ten incremental ones. Added companion-plugins documentation (netbox-pbs,
  netbox-pdm, netbox-ceph, netbox-packer) in `docs/companion-plugins/`.
- **v0.0.16.post5** — migration fix-forward: dropped `replaces` from
  `0037_v0_0_15_release` and `0038_v0_0_16_release` to resolve post-squash
  migration graph errors that appeared on upgrades from 0.0.15.
- **v0.0.16.post6** — security: upgraded `idna` to 3.15 to resolve
  CVE-2024-3651 (domain label validation bypass). Published with
  `gh release create v0.0.16.post6 --repo emersonfelipesp/netbox-proxbox
  --title v0.0.16.post6 --generate-notes`.

Sibling-plugin releases (`netbox-pbs`, `netbox-pdm`, `netbox-ceph`,
`netbox-packer`) should adopt the same develop-first + GH-release-triggered
policy when their next release cycle begins. Until they do, the older
"cancel duplicate" step still applies on those repos.

What was done for v0.0.19:

- Fixes database and API compatibility issues between the plugin and proxbox-api:
  `FastAPIEndpoint` token-drift fix (re-register on explicit token change),
  `PBSEndpoint`/`PDMEndpoint` `host` and `timeout_seconds` bridging properties.
- **Historical v0.0.19 Gitea-first bootstrap**: the original workflow handled
  `push: tags:`, `create`, and `workflow_dispatch`, and that release used a
  direct-upload recovery while tag triggers were broken. This history is not a
  current procedure. The current target is tag-push-only, manifest-bound,
  repository-linked, and fail-closed. It verifies pinned uv in fresh per-run
  managed-Python/cache roots and emits only a canonical six-file signed request. The
  separate locked control plane verifies and seals the bytes before its isolated
  publisher performs registry writes; fixes always advance to a new immutable
  version.
- Paired backend: `proxbox-api v0.0.16`.
- **Historical GitHub release**: The draft GitHub release `v0.0.19` was
  published manually as a one-time cleanup. Current private publishing pushes
  only RC tags to GitHub; final promotion and GitHub Release creation happen
  only after the Gitea package and NMS production gates.

### Package-first Production Deployment

The package publisher never deploys directly and never uses SSH. After a final
Gitea package is linked to this repository and its two artifacts/digests are
verified, dispatch the production target through `nms git deployments` with
`latest_package` (default). `main_branch` is an explicit operator-selected
alternative. Promote to GitHub/PyPI only after NMS reports success and the live
NetBox/plugin health checks pass.
- Quoted variable interpolation prevents shell injection

**Deployment flow:**
1. Git fetch/checkout of the released tag in the plugin submodule
2. pip install -e to refresh editable install
3. manage.py migrate to apply any pending migrations
4. manage.py collectstatic to collect new/updated static files
5. systemctl **restart** netbox.service (gunicorn re-exec so refreshed plugin
   code is re-imported). **Never `reload`** here: a graceful gunicorn reload
   (SIGHUP) can keep stale model code resident and silently serve a schema that
   no longer matches the migrated DB (e.g. a dropped column), producing
   `ProgrammingError` 500s on every affected query. The prod WSGI unit is
   `netbox.service` (older hosts used `netbox-production.service`).
6. systemctl restart netbox-rq.service (RQ worker restart for code changes)
7. Verify the deploy across three independent gates — any failure rolls the
   plugin back to the previous ref and restarts NetBox:
   a. **HTTP health** — `curl -sf http://127.0.0.1:18001/api/` returns 200/403.
   b. **Freshness (boot token)** — the WSGI unit's
      `ExecMainStartTimestampMonotonic`, captured before/after the restart, must
      advance. This proves the web process actually restarted and re-imported the
      new code — not merely that *some* backend answers — catching a wrong-unit
      or compose no-op restart that would otherwise ship green on stale code.
   c. **Model DB smoke** — a fresh, read-only `manage.py shell` queries one row of
      every managed, non-proxy model of the deployed plugin; any DB/schema error
      (a missing or unapplied migration) fails the deploy. The bare `/api/` probe
      does not exercise plugin models, so this is the gate that catches a
      stale-code / schema mismatch.

**Monitoring and manual recovery:**
- Watch the target `publish-gitea.yml`, central locked-control, and
  `deploy-production.yml` workflow runs in Gitea Actions.
- Use the approved NMS CLI deployment/status surfaces for production health,
  logs, hotfixes, and rollbacks. Do not access the production host directly or
  bypass NMS with SSH commands.

For detailed production deployment infrastructure and cross-plugin coordination, see `/root/personal-context/nmulticloud-context/CLAUDE.md` "Automatic Plugin Deployment to Production" section.

---

## Software Engineering Life Cycle Requirements

This section establishes project-wide quality standards derived from industry-standard software engineering practices. All changes must conform to these requirements before release.

### Requirements Traceability and Design Documentation

**Architectural Design:** The plugin's architecture is defined across:
- **Plugin models** (`netbox_proxbox/models/`) — subsystem decomposition
- **Service layers** (`netbox_proxbox/services/`) — dependency definitions and evolution rules
- **API contracts** (`netbox_proxbox/api/`, `netbox_proxbox/schemas/`) — interface specifications
- **Integration surface** (backend proxy routes, sync job contracts) — cross-subsystem dependencies

Changes to plugin models, service APIs, or backend contracts MUST include an updated architecture note in the closest CLAUDE.md explaining:
- What subsystem or interface changed
- Why the change is necessary (traceability to an issue or feature)
- What downstream systems are affected
- Any breaking changes or migration steps

**Derived Requirements:** All plugin features must support the derived requirement that NetBox remains the source of truth for sync data. Features that mutate Proxmox directly (intent workflows) must be explicitly gated and safety-locked.

**Verification:** Before opening a PR, confirm that:
1. Models and schemas match their CLAUDE.md documentation
2. All new public methods have docstrings explaining purpose and contracts
3. Integration points (backend proxies, SSE contracts, webhook handlers) are documented in the nearest CLAUDE.md

### Code Coverage and Quality Metrics

**Coverage Target:** Maintain ≥85% coverage for changed production logic in the
harness that can execute it. Coverage is measured by `pytest-cov` and reported
in CI. Endpoint auto-configuration and the bridge-v1 scheduling serializers are
real-Django-only and each has an independent 85% branch-coverage floor in
`.github/workflows/django-tests.yml`; aggregate coverage cannot let one module
mask the other.

**Coverage Reporting:** 
- `rtk pytest -p no:django tests/ --cov=netbox_proxbox --cov-report=term-missing`
  runs the broad mocked suite locally.
- The real-NetBox matrix reports the combined data, then runs separate
  `coverage report --include=... --fail-under=85` gates for endpoint
  auto-configuration and the bridge serializer on every push; do not disable
  pytest-django in that job.
- Uncovered code MUST be documented with a rationale (e.g., "except: pass for legacy API compatibility")

**Exclusions:** The following are exempt from coverage requirements:
- `netbox_proxbox/static/` (JavaScript), `netbox_proxbox/templates/` (Django templates)
- Database migration files (`netbox_proxbox/migrations/`)
- Unreachable exception handlers and platform-specific branches

### Testing and Regression Requirements

**Test Suite:** All changes must include unit and integration tests:
- **Unit tests** (`tests/test_*.py`) — verify individual functions and models in isolation
- **Integration tests** (`tests/integration/`) — verify plugin + NetBox + proxbox-api workflows end-to-end
- **Regression tests** — always include a test that would fail on the pre-fix code

**Regression Testing:** Before release, run:
```bash
rtk pytest -p no:django tests/integration/ -v --timeout=30
rtk pytest -p no:django tests/ -v --cov=netbox_proxbox --cov-report=term-missing
```
This verifies that no previously passing test was broken by the change.

**E2E Validation:** Changes to sync workflows, backend integration, or Proxmox VM models must be validated against the full E2E Docker stack:
```bash
docker compose -f e2e/docker/docker-compose.yml up --build -d
bash e2e/docker/wait-for-stack.sh
bash e2e/docker/smoke.sh
```

### Static Analysis and Quality Gates

**Linting:** All code must pass `ruff` static analysis:
```bash
rtk ruff check .          # Detect errors, style violations, unused imports
rtk ruff format --check . # Enforce code formatting
```

**Type Checking:** All Python files MUST pass `ty` (Pyright strict):
```bash
rtk ty check proxbox_cli
```

**Defect Categories Detected:**
- Undefined variables and imports
- Incorrect method/attribute access
- Unused imports and dead code
- Security issues (SQL injection, unsafe eval, XSS vectors)
- Type mismatches (via Pyright strict mode)

**Pre-commit Enforcement:** The pre-commit checklist at the top of this file MUST pass before committing ANY change:
```bash
python -m compileall netbox_proxbox tests
rtk ruff check .
rtk pytest -p no:django tests/
rtk ty check proxbox_cli
```

### Configuration Control and Change Management

**Configuration Items:** The following are managed under strict change control:
- Plugin version (`netbox_proxbox/__init__.py` `__version__`, `pyproject.toml` version field)
- NetBox compatibility floor (`netbox_proxbox/__init__.py` `min_version` and `max_version`)
- Backend service minimum version (`proxbox_api` version floor in `pyproject.toml` dependencies and CI matrix)
- Plugin models and migrations (all changes require `makemigrations --check --dry-run` validation)
- Backend integration contracts (sync routes, job queue names, SSE payload schemas)

**Change Control Process:**
1. **Before changing a configuration item**, post a comment on the related GitHub issue or PR explaining the change and impact.
2. **After merging**, update the relevant CLAUDE.md file to document the new floor or requirement.
3. **Release notes** MUST include breaking changes to configuration items (e.g., "requires proxbox-api ≥0.0.14").

**Version Management:** Follow PEP 440:
- Use `X.Y.ZrcN` for release candidates (TestPyPI validation only)
- Use `X.Y.Z` for official releases
- Use `X.Y.Z.postN` for bug-fix releases (never `X.Y.Z.devN` or `twine --skip-existing`)

### Pre-Release Verification Checklist

**Before opening a release PR, verify ALL of the following:**

- [ ] All requirements are implemented and verified in code
- [ ] Code passes pre-commit checklist (syntax, lint, tests, type checking)
- [ ] Coverage is ≥85% (`pytest-cov --cov-report=term-missing`)
- [ ] Regression testing passes against E2E Docker stack
- [ ] Changelog (`docs/release-notes/version-X.Y.Z.md`) is complete
- [ ] Architecture documentation (CLAUDE.md files) is updated
- [ ] Backend compatibility (proxbox-api version floor) is documented
- [ ] NetBox compatibility matrix is current (`min_version`, `max_version`)
- [ ] All CI checks are green (GitHub Actions)
- [ ] Integration with latest NetBox official release is confirmed

**After merging to develop**, before creating GitHub release:

- [ ] RC cycle is complete (all TestPyPI validation passed)
- [ ] Merged commit is on `develop` branch
- [ ] Version bumps are finalized (`X.Y.Z`, not `rcN`)
- [ ] Release notes are approved
- [ ] No uncommitted changes remain in the working tree

**During release publishing**:

- [ ] Push RC and final tags to Gitea first; only RC tags are promoted automatically
- [ ] Link and verify the final Gitea package, then deploy it through NMS
- [ ] Only after production validation, promote the final tag and use `gh release create`
- [ ] Monitor CI/CD for successful PyPI and Docker Hub publication
- [ ] Verify dist is live on PyPI before declaring success

---

## How To Navigate

- Start with [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md) for the package-level map.
- Go to `models`, `views`, and `api` first when changing behavior.
- Use `forms`, `filtersets`, and `tables` when changing how plugin objects are edited or listed in NetBox.
- Use `templates` and `static` together when adjusting UI behavior, page structure, or browser-side interactions.
- Check `migrations` before changing any model field or constraint.
- For sync streaming changes, see `views/CLAUDE.md` (SSE proxy), `static/netbox_proxbox/js/CLAUDE.md` (browser SSE parsing), and `templates/netbox_proxbox/CLAUDE.md` (stream URL wiring).

## Index

- [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/api/CLAUDE.md`](./netbox_proxbox/api/CLAUDE.md)
- [`netbox_proxbox/forms/CLAUDE.md`](./netbox_proxbox/forms/CLAUDE.md)
- [`netbox_proxbox/management/CLAUDE.md`](./netbox_proxbox/management/CLAUDE.md)
- [`netbox_proxbox/management/commands/CLAUDE.md`](./netbox_proxbox/management/commands/CLAUDE.md)
- [`netbox_proxbox/migrations/CLAUDE.md`](./netbox_proxbox/migrations/CLAUDE.md)
- [`netbox_proxbox/models/CLAUDE.md`](./netbox_proxbox/models/CLAUDE.md)
- [`netbox_proxbox/schemas/CLAUDE.md`](./netbox_proxbox/schemas/CLAUDE.md)
- [`netbox_proxbox/services/CLAUDE.md`](./netbox_proxbox/services/CLAUDE.md)
- [`netbox_proxbox/static/CLAUDE.md`](./netbox_proxbox/static/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md)
- [`netbox_proxbox/tables/CLAUDE.md`](./netbox_proxbox/tables/CLAUDE.md)
- [`netbox_proxbox/templates/CLAUDE.md`](./netbox_proxbox/templates/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md)
- [`netbox_proxbox/templatetags/CLAUDE.md`](./netbox_proxbox/templatetags/CLAUDE.md)
- [`netbox_proxbox/views/CLAUDE.md`](./netbox_proxbox/views/CLAUDE.md)
- [`netbox_proxbox/views/endpoints/CLAUDE.md`](./netbox_proxbox/views/endpoints/CLAUDE.md)
- [`netbox_proxbox/views/sync_now/CLAUDE.md`](./netbox_proxbox/views/sync_now/CLAUDE.md)
- [`proxbox_cli/CLAUDE.md`](./proxbox_cli/CLAUDE.md)
- [`tests/CLAUDE.md`](./tests/CLAUDE.md)

---

## Branching-Driven Intent

netbox-proxbox supports **two integration directions**:

1. **Proxmox → NetBox (reflection, default).** The historic, read-only
   pipeline. `proxbox-api` discovers Proxmox state and reflects it into
   NetBox via `createOrUpdate`-style helpers. No Proxmox-side mutation.
2. **NetBox → Proxmox (intent, opt-in).** Operators declare desired state
   on a NetBox **branch**; merging the branch triggers `proxbox-api` to
   apply CREATE / UPDATE / DELETE against Proxmox (VMs, LXC, optional
   Cloud-Init). Gated by
   `ProxboxPluginSettings.netbox_to_proxmox_enabled` (default `False`)
   and per-branch custom field `apply_to_proxmox` (default `False`).

### Decision rule for new features

Every new feature must answer: **does it belong on the reflection side
(read-only), the intent side (write-through), or both?** If "both", ship
the read side first and the write side as a separate sub-PR.

### Invariants for the intent side

- Optional companion modules must be imported only when their Django app is
  enabled. A package present in the virtual environment but absent from
  `PLUGINS` is disabled: do not register its signals, models, views, or URLs.
  Conversely, never suppress an import failure for an enabled companion: fail
  startup instead of running a partially configured integration.
- The **single source of truth** for intent is the merged `ChangeDiff`
  list on a branch flagged `apply_to_proxmox=True`.
- The **single trigger** for Proxmox-side mutation is the `post_merge`
  signal from `netbox_branching.signals`. No other code path may mutate
  Proxmox; the operational verbs from #376 (start/stop/snapshot/migrate)
  are the one exception and they are audit-logged identically.
- Direct writes to `main` (no branch) do not trigger applies — they
  remain NetBox-only by construction.
- DELETE requires a **five-lock chain** (see **Safety Model** below):
  master flag + typed confirmation phrase + per-branch
  `apply_destroy_confirmed` + RBAC at request time + a *separate*
  user holding `authorize_deletion_request` who approves the
  resulting `DeletionRequest`. The plugin **never** calls Proxmox
  destroy from the merge handler.
- After every successful apply, the read-side reflection sync must
  produce **zero diffs** (drift-detect verification per #357).

### Safety Model

netbox-proxbox enforces four mandatory safety invariants on the intent
path. Code or configuration that bypasses any of these is a regression.

1. **Default direction is Proxmox → NetBox (read-only).** The intent
   path is opt-in at every level; nothing in this plugin's design
   weakens the read-only default.
2. **Master flag is locked behind a typed confirmation phrase.**
   `netbox_to_proxmox_enabled=True` requires
   `netbox_to_proxmox_typed_confirmation == "allow-edit-and-add-actions"`
   to pass `ProxboxPluginSettingsForm.clean()`. The settings template
   renders a red warning callout listing the risks. Toggling the
   boolean back to `False` clears the typed phrase, forcing a
   re-confirmation on re-enable. Code that bypasses the form-level
   validator is a regression.
3. **Every Proxmox-side DELETE goes through a `DeletionRequest`.**
   Branch merges containing DELETE diffs MUST NOT call Proxmox destroy
   at merge time. Instead, they create a `DeletionRequest` row in
   `pending` state, tag the Proxmox VM `proxbox-pending-deletion`, and
   wait for separate authorization. The metadata snapshot
   (`vmid`, `node`, name, tags, cores, memory, disk, interfaces, IPs,
   CFs) is captured so the executor can act after authorization
   without a NetBox FK. Code that calls Proxmox destroy without first
   creating an *approved* `DeletionRequest` is a regression.
4. **Authorization permission is held separately from
   `intent_delete_*`.** `netbox_proxbox.authorize_deletion_request` is
   declared on `DeletionRequest.Meta.permissions` and is independent
   of `intent_delete_vm` / `intent_delete_lxc` (which control who can
   *request* a delete). Granting both to the same role is allowed,
   but four-eyes self-approval is rejected at the view layer unless
   `intent_apply_authorization_self_approve_allowed=True` (default
   **False**). The Deletion-Requests page lives at
   `/plugins/proxbox/intent/deletion-requests/`.

### Cross-references

- Issue: [`#377`](https://github.com/emersonfelipesp/netbox-proxbox/issues/377)
- Reference doc: [`reference/NETBOX-BRANCHING.md`](./reference/NETBOX-BRANCHING.md)
- Companion roadmap items: #357, #358, #367, #370, #376

## Production deploy requires a signed NMS authorization

`deploy-production.yml`'s production job cannot be started usefully from Gitea.
The deploy host refuses `netbox-proxbox` unless it is invoked as the fixed
`proxbox-package-deploy deploy-main netbox-proxbox <sha> <request-id>
<proof-path> <request-sha256> <run-id>` action, and only `nms-backend` can mint
that authorization.

Dispatch with `POST /git/deployments/{target_id}/dispatch-source`
(target 4 = `emersonfelipesp/netbox-proxbox production`). The backend publishes
a request, injects `nms_request_id` and `nms_request_sha256` as workflow inputs,
and binds the authorization to that exact run. The workflow then claims it via
`POST /git/deployment-proofs/{request_id}/claim` and writes the response through
**unmodified** — the host verifies an Ed25519 signature over exactly those six
keys against a root-owned public-key pin, so reshaping the body invalidates it.
Those proof routes carry no bearer by design: holding the request id and its
digest *is* the authorization, which is why neither is ever echoed.

The source comes from the claimed request, never from the `deploy_source`
input — a canonical-main dispatch sends no `deploy_source`, so the input would
default to `latest_package`. The authorization is single-use and expires in
15 minutes, and `run_attempt` is a constant 1: a re-run needs a fresh dispatch.

`latest_package` fails closed until `publish-gitea.yml` publishes a
`<package>-release-manifest` generic package; no version has one today.
