# netbox-proxbox Repository Guide

Current release-candidate source: netbox-proxbox 0.0.31rc2 requires proxbox-api 0.0.29 or later (the release that adds endpoint-owned cluster bindings). The backend must be released and deployed before the plugin. The netbox-sdk dependency remains proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

> **LLM Agent Safety:** Before any destruction-adjacent operation, read
> `AGENTS.md` § "LLM Agent Safety Guardrails". Automated agents may inspect and
> explain protected workflows, but they may not supply human confirmation or
> approval on an operator's behalf.

> **Release channels:** the Gitea Package Registry must never go ahead of PyPI
> or Docker Hub. Publish a final or `.postN` to Gitea only in the same run that
> publishes it to PyPI; never consume a version number only on Gitea; choose
> the next version from the latest PyPI final. See `AGENTS.md` § "Release
> Channel Sync Guardrail".

This repository contains the public `netbox_proxbox` NetBox plugin and its
standalone `proxbox` command-line client. Keep the project independently
installable and usable with NetBox, Proxmox VE, and the public `proxbox-api`
interfaces documented in this repository.

## Public boundary

- Do not add closed-product identities, dependencies, credential contracts, or
  product-specific runtime coupling. Generic forge, registry, CI, and deployment
  infrastructure may remain when it serves this public repository directly.
- Run `python scripts/check_public_boundary.py` before review. The scanner must
  inspect every tracked text file and fail closed when inspection is incomplete.
- Express reusable integrations through project-owned, vendor-neutral APIs and
  persisted names. Do not add optional imports from unrelated private plugins.
- Generated documentation must be regenerated from sanitized sources. Never fix
  only a generated artifact while leaving its source contaminated.
- The boundary manifest covers reviewed name, domain, URL, command, path,
  package, service, distribution, workspace, retired contract, and private host
  identifier classes. It scans
  tracked text plus explicitly supplied wheel and source archives and fails
  closed when any file or archive member cannot be inspected.
- The persisted `nmulticloud` InfluxDB organization default is public user
  configuration, not a private control-plane identifier. Preserve it until a
  separately scoped compatibility migration provides an additive transition.

## Architecture

`PLUGINS_CONFIG["netbox_proxbox"]["automatic_background_tasks"]` is a strict
boolean, default `True`. Set it to `False` for inventory-only deployments to
suppress startup discovery and stock service-monitor registration. Existing
unowned, unscoped, exact-name one-minute system timers drain without polling or
re-enqueueing; audit records and user/custom jobs remain. A non-secret suppression
marker in existing Job.data is saved with the cleared interval so lifecycle
failure retries cannot resume polling. Require both object IDs and object types
to be absent; malformed suppression metadata fails closed. Restart all application
and worker processes after a configuration change. Keep explicit synchronization,
models, migrations, job APIs, and integrity signal handlers available. The
operator contract is in the Docker installation guide.

- `netbox_proxbox/models/` owns persisted plugin state and validation.
- `netbox_proxbox/api/` owns REST serializers, viewsets, and operational API
  actions. Secret-returning actions require explicit permissions and secure
  transport outside development mode.
- `netbox_proxbox/views/` and `netbox_proxbox/templates/` own the NetBox UI.
- `netbox_proxbox/jobs.py` and `netbox_proxbox/sync/` own asynchronous sync
  orchestration. NetBox remains the local system of record; Proxmox remains the
  source of truth for reflected infrastructure state.
- `ProxboxPluginSettings.sync_job_timeout` is the UI-backed RQ wall-clock limit
  for newly enqueued synchronization jobs. It defaults to 7200 seconds, accepts
  3600–604800 seconds, and never changes an already-running job's captured timeout.
- `proxbox_cli/` is a standalone client and must not import Django or NetBox.
- `docs/` is the source for the MkDocs site; `llms.txt` is committed generated
  documentation and must remain consistent with the source documentation.
- `Dockerfile.oci` and `oci/` define the testing-only all-in-one OCI appliance.
  It keeps NetBox and proxbox-api on separate Python runtimes, persists all
  database and secret state under the declared volumes, and must remain usable
  through both the OCI entrypoint and Proxmox LXC `/sbin/init`. Release builds
  use the single plugin/backend pairing declared in `COMPATIBILITY.md` only
  after compatible, non-yanked source distributions or pure-Python universal
  wheels appear in both required PyPI APIs, build the final multi-architecture
  index once, smoke-test its amd64 manifest, and publish that same digest.
- The authoritative semantic bridge contract is
  [`docs/api/semantic-mcp-bridge.md`](docs/api/semantic-mcp-bridge.md).

## Supported versions

The certified stable NetBox range is `4.5.8` through `4.7.99` (the whole 4.7 series is admitted by the numeric gate; CI verifies GA `4.7.0`). The current
plugin version is `0.0.31rc2`.

Current source compatibility: netbox-proxbox 0.0.31rc2 requires proxbox-api 0.0.29 or later (the release that adds endpoint-owned cluster bindings), with proxmox-sdk 0.0.15 and netbox-sdk 0.0.13. This describes the current sibling source revisions, not a historical published-release promise. The netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

The documented released runtime pairing for this release line is
netbox-proxbox 0.0.29.post6 <-> proxbox-api 0.0.27.post4 <-> proxmox-sdk 0.0.15
<-> netbox-sdk 0.0.13. Preserve release-note and compatibility rows as
historical records unless a release workflow changes them.

Current release-candidate runtime requirement: deploy proxbox-api 0.0.29 or later (the release that adds endpoint-owned cluster bindings) before netbox-proxbox 0.0.31rc2. The proxmox-sdk and netbox-sdk versions remain 0.0.15 and 0.0.13 respectively. The netbox-sdk dependency is REST-only and does not provide the semantic MCP bridge.

CI pairing: the E2E Docker, page-coverage, documentation-screenshot, and
release-validation defaults select proxbox-api `0.0.29`. These are intended
source selections, not evidence that the backend package or image is public.
Verify backend publication and qualification before candidate publication or
ordinary E2E execution. E2E uses the exact published image by default; source-head
builds require explicit `dependency_mode: dev`. Repository variables remain
equality-checked against the checked-in current default, and a different
coordinated candidate pairing requires the existing explicit manual input.
TestPyPI plugin candidates consume their paired backend from PyPI, preserving
the selected-index distinction and all current matrices.

## Current source map

- Models include endpoint configuration, synchronized cluster/node/storage/VM
  data, typed sync-state sidecars, guest interfaces, SDN and firewall
  inventory, Firecracker inventory, service-monitoring collections, metrics,
  intent/apply records, deletion requests, cloud-init records, and companion
  PBS/PDM endpoint records. Endpoint SSH may use an endpoint-owned
  `ProxmoxEndpointService` bound to the endpoint IP and a one-to-one
  `ServiceSSHCredential`; provider assignments target that service for the
  primary `console` purpose without depending on core `ipam.Service`. Service
  material reads require object-level reveal access and the exact enabled
  assignment. Provider writes and supported assignment cleanup run inside one
  settings-first transaction; raw deletes refuse remaining provider state.
  Migration `0107_v0_0_30_release` is the current schema tip. It consolidates
  the three unpublished development migrations for native cluster binding,
  endpoint-owned SSH services, and Cloud Image SSH binding. Installations that
  applied the former development `0107_endpoint_native_cluster_binding` retain
  its ignored orphan migration-recorder row; the new migration safely adopts
  the existing schema and data.

  Optional PDM and RPC integrations require the companion plugin to be enabled
  in NetBox, not merely importable. Installed-but-disabled packages must not
  render companion tables or query unmigrated companion settings models.

  Proxmox node Device names use the effective endpoint/global
  `node_device_name_template`; Proxmox API paths and typed sync identity retain
  the original short node name.
  Device sync-state identity also retains proxbox-api's independent
  `proxmox_endpoint_raw_id`; never substitute a local endpoint primary key.
  Stamped values are endpoint-exclusive, while null values remain unclaimed
  legacy candidates, never ownership proof. A consumer must corroborate actual
  cluster, site, and placement even for a singleton candidate before adoption.
  Device-sidecar claims lock the row; NULL-to-ID and same-ID writes are allowed,
  while changing a committed ID returns `endpoint_ownership_conflict`.
  Remote NetBox connection approval binds the effective token version and its
  non-secret v1 token reference or effective v2 key selected for transmission.
  Token changes require explicit
  reapproval, and token secrets never enter the fingerprint.
  Cloud Image bakes store the Proxmox target node and proxbox-api-host identity
  file path on `ProxmoxEndpoint`. Backend synchronization sends the complete
  six-field SSH binding only for API + SSH endpoints whose effective enabled,
  broad-write, and Packer gates are open, with every value populated and the
  selected inventory node verified at the endpoint SSH host. Verification compares
  the selected source's effective SSH host with node IP addresses. Service
  credentials use the endpoint IP even with a configured domain; other sources
  remain domain-first. Binding and approval use the effective SSH username and normalized actual SSH host. Configured bake bindings require explicit reapproval after this authority correction; endpoints without bake fields retain their approval formula.
  Every row at that address must have the same
  case-insensitive target name; conflicting names fail closed. Identity-file paths
  use POSIX normalization for payload and currency comparison. Value pushes store a
  SHA-256 management receipt in a durable transaction before transmission.
  Receipt failures, missing owners, and outer uncommitted transactions block
  value pushes. API-only explicit service-secret clears are rejected before
  save; use the separate credential settings. Commit-then-timeout remains
  managed. Gate closure or clearing both bake
  fields clears a managed binding; incomplete or failed verification also revokes
  Packer. Stale approval still permits credential-free managed-binding revocation.
  Successful clears erase only the prepared receipt, preserving a newer concurrent
  receipt. An empty receipt preserves an external binding. Form inventory validation
  is skipped when the submitted state closes a gate, allowing revocation while
  preserving draft values. Once a target node or
  identity file is configured, SSH binding authority changes require sensitive
  connection re-approval; endpoints with neither value keep their pre-existing
  approval fingerprint, so an upgrade does not invalidate their approvals. Backend currency compares
  emitted binding keys so a failed rotation remains retryable, while intentional
  omission ignores an existing backend binding. The consolidated release
  migration supplies database defaults during forward application. Its reverse
  removes the Cloud Image fields and SSH-service schema while retaining the
  native-cluster ownership column and values. Re-saving the endpoint triggers
  rollout through the post-save push.
- UI routes include the home/dashboard, data-protection calendar, HA, endpoint
  and inventory views, model-scoped Sync Now actions, repair/recovery flows,
  soft-deleted VM review, and standalone VM console sessions. Cluster and node
  detail routes are mounted through NetBox model URLs so their Sync Now actions
  resolve correctly.
  The core cluster Virtual Machines child tab must expose `BulkDelete`, not the
  misplaced single-object `DeleteObject` declared by NetBox 4.5–4.7. Keep the
  compatibility adapter version-checked and retain the core VM bulk-delete
  permission, confirmation, changelog, transaction, and protected-object path.
  Data Protection scheduled events use the source endpoint's best-effort
  discovered IANA timezone and convert exact wall-clock occurrences to
  NetBox's active timezone before day bucketing. Fail-open cases remain visibly
  approximate, and combined node selection is capped at 50.
  The per-VM HA tab treats the VM sync-state endpoint as authoritative, rejects
  linked typed cluster or node rows from another endpoint, intersects the exact
  enabled endpoint with caller visibility, and queries only that endpoint. An
  unresolved, inconsistent, disabled, or hidden identity fails locally without
  contacting the backend.
- Home dashboard status and card hydration uses one four-worker request pool.
  FastAPI probes have a short settings-hashed cache, successful Proxmox pushes
  have a secret-safe fingerprint cache whose backend ID is verified before use,
  card failures never downgrade successful keepalive badges, and backend capacity
  responses remain visibly throttled. Initial requests and at most three retries
  per card use the same persistent pool.
- REST routes expose typed endpoint and inventory viewsets, sync-state
  sidecars, SDN/firewall/Firecracker resources, service monitoring, jobs,
  settings, semantic MCP manifest discovery, browser-console session creation,
  and operational actions. The API is not a generic backend proxy.
  `GET /ha/vm/{vmid}/` requires `virtual_machine_id={netbox_vm_pk}`, restricts
  that VM and its authoritative sync-state endpoint by the caller's object
  permissions, verifies linked typed cluster and node consistency plus the
  synchronized VM ID match with `{vmid}`, and sends only that endpoint to the
  backend. Invalid or unresolved identity returns HTTP 400 without backend I/O.
  Proxmox operational actions use the grantable `run_proxmox_action` custom
  action on each `ProxmoxEndpoint`, with exact endpoint ObjectPermission
  scoping. The literal `core.run_proxmox_action` is a deprecated additive
  compatibility path. Unsafe requests authenticated by an API token require
  `write_enabled=True`; session authentication remains unchanged.
  Every operational dispatch binds the exact authorized, enabled NetBox endpoint
  to proxbox-api's separate endpoint ID through the shared operational-target
  resolver. Firewall previews carry a single translated endpoint scope and reject
  mismatched response identity. VM firewall ownership comes only from consistent
  typed sync state; explicit VM, node, and security-group relations must agree
  with their authoritative endpoint. Template builds retain the resolved backend
  context through dispatch. Disabled or conflicting endpoints produce no backend
  context or HTTP work.
- `ProxmoxServiceMonitoringJob` is a one-minute system job;
  `ProxboxSyncJob` owns the staged SSE synchronization pipeline. The standalone
  `pxb` CLI covers local configuration, backend inspection, NetBox/Proxmox
  resources, headless sync, and deterministic CLI documentation capture.
  Staged runs isolate required-stage, firewall, and datacenter failures per
  Proxmox endpoint, continue later endpoints, persist each failed scope, and
  fail after all selected endpoints have been attempted. Backend-key and stage
  throttling retries share bounded delta-seconds and HTTP-date `Retry-After`
  parsing. Staged work uses one monotonic RQ-timeout deadline with a 120-second
  persistence reserve; deadline exhaustion records the current and remaining
  endpoint failures before finalization.
- The server-side WebSocket bridge binds positive `ws_run_id: 1` capability
  state to one authenticated connection, invalidates it on connection changes,
  and rechecks it when dispatching every correlated command. A rejection wins
  over an earlier in-flight probe. Capability doubt sends the legacy bare
  command. An attributable invalid-envelope response downgrades the same run,
  retries its command once as legacy, and tells its poller through a run-matched
  control record; foreign, malformed, and late rejections never replay a
  command. An expired or replaced pending envelope is retired without replay so
  its successor can dispatch. Reload and require the original endpoint trust
  identity after capability discovery and before any retry; trust loss closes
  the connection and surfaces a failed `sync-run` record without sending or
  downgrading the command. During mixed-version rolling deployment, one rejected
  envelope may be retried once as legacy and all later commands on that
  connection remain legacy. Correlated runs accept only exact, well-formed run
  identifiers and documented aggregate statuses. Legacy runs accept only
  untagged frames; full updates retain virtual-machine-terminal completion and
  the 600-second idle latch.
- Gitea workflows own CI, package publication, final-tag promotion, artifact
  compatibility, and the approved GitHub mirror. GitHub workflows own public
  CI, the real-Django matrix, documentation, screenshots, E2E contracts,
  nightly contracts, page coverage, notifications, and TestPyPI publication.

## GitHub matrix observation

`scripts/wait_for_github_django_matrix.py` is a base-pinned external supervisor
for `.github/workflows/django-tests.yml`. It is non-security evidence and cannot enforce
merge authorization or protect secrets. Prefer `GH_MATRIX_READ_TOKEN_FILE`
with a mode-`0600` or stricter file; `GH_MATRIX_READ_TOKEN` is a weaker fallback.
Removing an inherited environment value cannot erase the original process
environment from `/proc/<pid>/environ`. The bootstrap must remain non-consuming
and must not be treated as a security gate.

The Django compatibility matrix has eight independent jobs: five base NetBox
versions, the PDM registry override, the NetBox 4.7 all-companion configuration,
and the NetBox 4.7 OpenBao configuration. Keep the original `profile: [base]`
axis and distinct `all-companions` and `openbao` profile values. Matching
`include` entries merge into original GitHub matrix combinations; removing
this discriminator collapses the companion contracts and selects the wrong
hash lock. Keep each profile paired with its reviewed dependency lock.

The Django workflow includes one immutable NetBox 4.7 cell that installs and
registers netbox-proxbox together with netbox-ceph, netbox-pbs, netbox-pdm, and
netbox-packer. Keep every companion checkout pinned by commit, verified by HEAD
and pyproject digest, resolved from the reviewed hash-locked input, and covered
by the post-migration registry and system-check assertions. This GitHub evidence
does not replace a required Gitea pre-merge gate.

The private PBS companion checkout requires the GitHub repository secret
`COMPANION_READ_SSH_KEY`. Register its public key as a read-only deploy key
for `emersonfelipesp/netbox-pbs` only and store its private key securely in
the encrypted Actions secret. Supply it only to the
conditional PBS credential diagnostic and checkout. Keep
`persist-credentials: false`; never expose this credential to test processes,
other checkouts, command text, logs, or artifacts. A missing credential must
fail clearly without removing the pinned companion or its matrix coverage.

The workflow also includes an immutable NetBox 4.7 OpenBao cell. Keep its
netbox-openbao and netbox-rpc source commits, pyproject digests, composed input,
and hash lock aligned. Endpoint OpenBao writes must use the exact configured
policy slug and the provider-owned material transaction; credential UUIDs,
assignments, audit witnesses, and metadata projection must not be persisted as
independent best-effort steps. Selected node SSH password/keypair material uses
the same boundary, assigns the primary `login` purpose to the linked
`dcim.Device`, and reconciles link, relink, and unlink changes automatically.
FastAPI, PBS, and PDM API tokens use `api-token` credentials assigned to their
owner for the `api` purpose; Firecracker agent tokens use the same credential
type with the `agent` purpose. Their public readiness and assignment lookup
metadata is provider-neutral and never reveals material or UUID references.

Keep OpenBao-dependent real-Django suites isolated to that exact companion
cell. The ordinary NetBox compatibility cells prove the plugin without the
optional package and must not inherit provider rows or references from tests
that require netbox-openbao. Tag-triggered screenshot validation must check out
the immutable tag and must never push generated screenshots; only an explicit
manual screenshot refresh may write its selected branch.
VM cloud-init password and private-key inputs use `password` and `ssh-keypair`
credentials assigned to the parent `virtualization.VirtualMachine` for the
`login` purpose. `ssh_pwauth` selects the primary assignment; public
`sshkeys`/`sshkeys_enc` never enter provider payloads, and the legacy
`credential_reference_id` remains an opaque external reference only in
explicit legacy mode.
Unlinked nodes defer assignment. OpenBao resolution fails closed without a
Fernet or an unrelated credential-provider fallback; explicitly selected legacy
storage continues to use Fernet. UI and REST credential/link mutations must
enter the provider material transaction before NetBox's atomic wrapper and
carry the request actor through that boundary. Raw/bulk ORM bypasses, parent
cascades, and OpenBao-to-legacy changes must refuse while owned references or
assignments remain and require explicit cleanup. Readiness and generic
assignment selectors may be exposed as secret-free metadata, but live node
material remains confined to the authenticated hardware credential endpoint.
Global storage changes through `save()`, queryset `update()`, and
`bulk_update()` lock the settings singleton before final guard checks and keep
it locked through persistence. Both default and base manager querysets are
guarded; validated literal bulk updates use only a context-local permit for
Django's internal expression update. Provider outer material transactions are
entered in autocommit. Inside their provider-owned durable transaction, the
settings singleton is the first row lock, before every owner, assignment, or
credential row; downstream row order remains transaction-specific.
Every material writer must then revalidate its effective backend from the
locked settings and owner graph before provider or assignment writes. Settings
querysets must resolve the write-router alias before locking, bind every final
state read to that alias, and reject conflict upserts that update
`credential_storage_backend`. A blank endpoint override inherits the effective
global selection from the locked settings row on that same write database.
Supported endpoint deletion removes assignments before `pre_delete`; any
assignment-only state remaining at that signal proves an unsupported delete and
must be refused. An explicitly legacy endpoint with assignment-only state uses
plain ORM cleanup in the current application transaction and never enters a
provider material transaction. It must freshly resolve the request actor and
authorize every exact assignment deletion before deleting any row; referenced
OpenBao endpoints retain their provider-owned cleanup path.
Verified Fernet rotation and selective reset may cross the single-secret
queryset guard only through the private exact model, database alias, field, and
ciphertext permit. Ordinary or mismatched writes and reference mutations remain
refused.
`netbox_proxbox/api/device_openbao_ssh_resolver.py` resolves the by-node SSH
secrets fallback (used only when no local `NodeSSHCredential` exists) against
a netbox-openbao `ServiceEndpoint` + `Credential` pair on the node's linked
`dcim.Device`, through the same audited `reveal_credential_material` path,
with the same SSH-access gate as the local-credential path. The credential
lookup is additionally scoped through
`Credential.objects.restrict(request.user, "reveal")` — the same object
permission netbox-openbao's own reveal API requires — so a caller authorized
only for the local `NodeSSHCredential` path (e.g. `view_nodesshcredential`)
cannot reveal an arbitrary device's OpenBao-stored material through this
fallback; an unauthenticated caller or one lacking `reveal_credential` gets a
403. More than one
credentialed SSH `ServiceEndpoint` for a device is a denial — callers may
narrow with an explicit port — never a partial answer. netbox-openbao is
optional and imported lazily through `apps.is_installed()`/`apps.get_model()`;
with it absent, with no matching endpoint, or predating the
`ServiceEndpoint`/`Credential` models this module expects, resolution returns
nothing and the caller sees the same 404 as before this fallback existed
(`_get_openbao_model()` catches `apps.get_model()`'s `LookupError` for the
last case — see docs/companion-plugins/netbox-openbao.md for the pinned CI
revision this currently affects and when the pin can move). There is no
reintroduced coupling to any other non-public, environment-specific plugin —
the public-boundary scanner (`scripts/check_public_boundary.py`) is the
enforced reason: it fails closed on private identifiers, which ruled out
restoring the exact legacy design the originating issue described. Both
`_credential_for_node_identifier()` and `_proxmox_node_for_identifier()` in
`ssh_credentials.py` resolve both interpretations of `node_id` (own PK and
linked-device PK) and refuse a genuine collision between two distinct rows,
never silently preferring one.
`proxbox_openbao_setup --check` and the settings readiness card share one typed,
secret-free structural readiness service. Writable setup may create only an
explicitly configured default engine and the configured policy; it never creates
users or material. Assignment backfill adds only missing relations and refuses
unresolved references or another owner's primary assignment. This does not
certify the broader RPC/backend protected-write rollout.
Backfill accepts an exact existing relation only when it is enabled, its primary
state matches the declared slot, and the provider credential type is exact.
Mismatches are reported without UUIDs and are never rewritten implicitly.
Interactive storage validation consumes only the provider, default-engine, and
exact-policy subset; it must not require RPC or an automation username when the
authenticated request actor supplies the write identity. Writable setup raises
inside its atomic block so failed final composed readiness rolls back every row.

## Real-NetBox migration test compatibility

When a test rewinds only the plugin migration graph, create shared NetBox rows
through the current model before rewinding and reacquire them through the
historical app registry. A historical model may omit newer non-null physical
columns. Never reverse an additive repair by dropping a field or column owned
by an earlier migration, and never rewrite a published migration to accommodate
a newer app-registry class identity; narrow the compatibility fixture while
retaining isolated coverage of the published behavior. Version-specific
query-count baselines are allowed only for a demonstrated NetBox core query-plan
difference and must be verified in the affected and adjacent matrix lanes.
Native table tests must exercise shared supported NetBox table behavior across
4.5.8 through 4.7.99: keep the token column visible before calling no-argument
`_apply_prefetching()`, which every supported release accepts.

SSH secret APIs require the same fresh sensitive-data grant in addition to
API-token authentication, HTTPS, object visibility, and provider permissions.
New ObjectChange snapshots redact settings keys, credential material,
ciphertext, and provider references through a shared registry. Historical
snapshots are unchanged. Proxmox and NetBox endpoint target edits invalidate
`approved_connection_target_fingerprint`; credential payloads require exact
approval before resolution and again before transmission. Review the target
with GET and approve its fingerprint with PUT on the endpoint's
`connection-authority` API action. Approval requires sensitive-data access and
independent view/change access. Migration `0104_security_hardening`
leaves existing approvals blank. FastAPI target changes additionally require
sensitive authority before its existing authentication/adoption flow; disabled
backend target edits remain drafts.

## Safety invariants

- Never log credentials or include them in ordinary serialization, templates,
  history, errors, or exports. Explicit protected endpoint exports and runtime
  key disclosure require an active authenticated superuser or the default-off
  per-user sensitive-data flag, plus existing object and provider permissions.
  Only active superusers may administer grants; cached user relations and
  ordinary view/change/token permissions must never confer sensitive access.
- Credentialed HTTP requests must reject redirects, validate their destination,
  use bounded timeouts, and verify TLS by default.
- Destructive Proxmox operations require explicit permission and the repository's
  approval or intent workflow. Do not weaken four-eyes or confirmation gates.
- Keep optional companion-plugin imports lazy and fail safely when unavailable.
- netbox-openbao is optional. Automatic credential storage selects OpenBao only
  when the companion is enabled and otherwise selects local Fernet storage;
  explicit selections never fall back.
- Keep Proxmox endpoint API readiness response-local: derive serialized service
  monitoring eligibility from non-secret endpoint metadata plus response-local
  SSH and RPC readiness, preserve the guarded netbox-rpc model import before
  endpoint overrides, read each required global setting at most once per
  serializer, and derive OpenBao SSH readiness from one list-wide, actor-
  authorized credential metadata query without resolving credential material.
- Historical migrations are immutable compatibility records. Add a new migration
  for schema changes instead of rewriting an already released migration, except
  when sanitizing non-functional prose without changing migration behavior.
- New executable functions require explicit return types and focused tests.
- EdgeUno repositories and vendor checkouts are read-only reference sources.
  Implementation belongs only in `emersonfelipesp/netbox-proxbox`.
- Disabled endpoints are a hard no-network gate for API, SSH, console, sync, and
  monitoring actions.
- Browser console authentication, tickets, upstream URLs, credentials, and TLS
  decisions remain server-side. Never serialize console secrets to templates or
  browser-readable configuration.
- Semantic bridge scope is limited to the public manifest and typed operations
  documented in `docs/api/semantic-mcp-bridge.md`; it is not a raw API proxy.
- Configuration ownership stays local: Proxbox settings own plugin behavior,
  NetBox owns permissions and inventory, and companion plugins own their own
  backend selection and credentials.
- Keep cluster-tab selected-row deletion routed to
  `virtualization:virtualmachine_bulk_delete`. The cluster page's top-level
  Delete action targets the parent cluster and must never be presented as a VM
  bulk action. Preserve this distinction with the real-Django regression.

## Change workflow

1. Add or update tests that state the behavior and failure modes.
2. Keep documentation, API references, migrations, and generated artifacts in
   the same change as the behavior they describe.
3. Run focused tests while developing, then the configured lint, format, type,
   documentation, package, migration, and test gates appropriate to the diff.
4. Run a per-function cyclomatic-complexity audit for changed executable code.
   Scores 11–15 require review, 16–25 require strong branch coverage or
   refactoring, and scores above 25 block the change without an approved waiver.
5. Run `python scripts/check_public_boundary.py` on the proposed tracked tree.

## Common verification

```bash
ruff check .
ruff format --check .
python -m compileall -q netbox_proxbox proxbox_cli tests
pytest -p no:django -q tests
mkdocs build --strict
python scripts/check_public_boundary.py
```

Use the real-NetBox matrix for ORM, migration, permission, template-rendering,
and database behavior. The mocked suite is not evidence for those behaviors.

## Scoped guidance

Read the nearest scoped `CLAUDE.md` before changing files under
`netbox_proxbox/api/`, `netbox_proxbox/models/`,
`netbox_proxbox/templates/netbox_proxbox/`, or
`netbox_proxbox/views/endpoints/`.

## Connection approval recovery

The Proxmox and remote NetBox endpoint detail pages provide a secret-free
connection target review panel. An authorized human must review the current
destination before explicitly approving it through the protected
`connection-authority` API action. The panel never approves on GET, page load,
ordinary save, or upgrade. Failed or stale approval responses require another
review. Backend health does not substitute for endpoint approval. Keep the
existing sensitive-data, object permission, disabled-state, and exact-target
checks authoritative on the server.

Native OpenBao profile fixtures must state their intended storage explicitly.
Local-encryption suites persist `legacy_encrypted` and a test key before creating
owners. Target changes carry the authenticated actor through `current_request`
and restore that context in `finally`. Successful hardware SSH fixtures persist
`enabled=True` and `api_ssh` at endpoint creation; API-only and disabled-endpoint
refusal coverage remains separate.
Migration rewind tests use historical models. Migration `0103` intentionally
retains physical columns on reversal, so disposable test databases may provide
those columns with temporary defaults during historical INSERTs and remove the
defaults immediately afterward. Never apply this fixture DDL to managed databases
or modify published migrations to accommodate tests.

## Native local mock telemetry

The E2E mock uses the public native FastAPI factory described in
`docs/developer/proxmox-mock-local.md`. Preserve opt-in export with no implicit
collector or service identity, SDK-disabled application signals, selected
caller provider ownership, scoped privacy, and excluded nested-context
normal/error regressions. Install the E2E extra for the mocked suite and retain
all eight exact real-Django dependency profiles. Local observer provider
shutdown is not the application's shipping lifespan ownership contract.

## Native cluster ownership

`ProxmoxEndpoint.netbox_cluster` is the nullable one-to-one authority for native
cluster identity. `services/cluster_binding.py` implements the endpoint-locked,
local-only `sync-cluster` action. It uses an existing authoritative relation or
unambiguous exact tracking links, never a matching name, and persists native
cluster, endpoint, tracking, and typed sidecar changes in one transaction.
Tracking model saves enforce ownership and ordinary CRUD cannot silently move a
tracking record to another endpoint or native cluster. Preflight cluster
metadata synchronization reuses the linked tracking identity across renames.
Claims are exclusive to the protected action; ordinary tracking saves can clear
obsolete evidence but cannot populate endpoint authority. Sidecar ownership is
server-owned and metadata writes serialize on the native parent. Keep endpoint,
native cluster, tracking, then sidecar lock order. The action explicitly derives
tracking/sidecar maintenance authority from endpoint/core grants and reports
substantive native updates through its additive `changed` response flag.
UI and API relation disclosure require visibility of the related object.
See [the operator contract](docs/features/proxmox-cluster-binding.md) and
`tests/test_endpoint_cluster_binding_django.py` for the real-Django regressions.


## Post-candidate validation boundary

Release 0.0.31rc1 adds only `0108_v0_0_31_schema_validation` after the applied,
immutable `0107_v0_0_30_release`. Keep every numbered migration through 0107
byte- and mode-identical. The unchanged private `_release_0107_schema.py`
checks objects introduced by 0107; its marker identifies that invariant while
the actual migration executing it is 0108. It must remain 0108's last operation.
The source-bound full function audit and native qualification belong to this new
migration boundary, not a relabeling of the earlier pre-candidate experiment.

The 0107 and 0108 transactions commit separately. A failure in 0108 preserves
an already committed 0107 and leaves 0108 unrecorded. Do not claim joint rollback,
rewrite deployed history, or silently repair an unexpected schema. Reverse of
0108 is a no-op for schema/data; reapply validates again. Preserve actual recorder
and data evidence for explicit reviewed recovery. The original 0107 reverse
controls remain historical and do not prove that 0108 removes those objects.
