# netbox-proxbox Repository Guide

Current backend-runtime pairing: netbox-proxbox 0.0.29.post2 <-> proxbox-api 0.0.23.post3 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

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
  through both the OCI entrypoint and Proxmox LXC `/sbin/init`.
- The authoritative semantic bridge contract is
  [`docs/api/semantic-mcp-bridge.md`](docs/api/semantic-mcp-bridge.md).

## Supported versions

The certified stable NetBox range is `4.5.8` through `4.7.99` (the whole 4.7 series is admitted by the numeric gate; CI verifies GA `4.7.0`). The current
plugin version is `0.0.29.post2`.

Current source pairing: netbox-proxbox 0.0.29.post2 <-> proxbox-api 0.0.23.post3 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This describes the current sibling source revisions, not a historical published-release promise. The netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

The last documented released runtime pairing for this release line remains
netbox-proxbox 0.0.27 <-> proxbox-api 0.0.23.post2 <-> proxmox-sdk 0.0.15
<-> netbox-sdk 0.0.13. Preserve release-note and compatibility rows as
historical records unless a release workflow changes them.

Current backend-runtime pairing: netbox-proxbox 0.0.29.post2 <-> proxbox-api 0.0.23.post3 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

CI pairing: the E2E Docker, page-coverage, documentation-screenshot, and
release-validation workflow defaults consume proxbox-api `0.0.23.post3`. E2E uses the
exact published image by default; GitHub source-head builds require explicit
`dependency_mode: dev`. Repository variables are equality-checked configuration:
release preparation fails closed when an implicit value does not equal the
checked-in current default, and a coordinated candidate requires an explicit
workflow input. TestPyPI plugin candidates use stable proxbox-api `0.0.23.post3` from
PyPI because that backend version is not published on TestPyPI. The E2E harness
uses typed sync-state sidecars and must not call the removed proxbox-api custom-
field creation route.

## Current source map

- Models include endpoint configuration, synchronized cluster/node/storage/VM
  data, typed sync-state sidecars, guest interfaces, SDN and firewall
  inventory, Firecracker inventory, service-monitoring collections, metrics,
  intent/apply records, deletion requests, cloud-init records, and companion
  PBS/PDM endpoint records. Migration
  `0105_reset_implicit_openbao_storage_default`
  is the current schema tip.

  Optional PDM and RPC integrations require the companion plugin to be enabled
  in NetBox, not merely importable. Installed-but-disabled packages must not
  render companion tables or query unmigrated companion settings models.

  Proxmox node Device names use the effective endpoint/global
  `node_device_name_template`; Proxmox API paths and typed sync identity retain
  the original short node name.
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
