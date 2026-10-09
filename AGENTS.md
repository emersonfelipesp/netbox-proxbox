# netbox-proxbox Agent Guide

`CLAUDE.md` is the source repository guide. Read and follow it before making
changes in this repository.

The EdgeUno repository and vendor checkout are read-only reference sources;
never edit or target them. Disabled endpoints are a hard no-network gate.
Console authentication, tickets, upstream URLs, secrets, and TLS decisions stay
server-side. The semantic bridge exposes only its documented typed manifest,
not a raw proxy. Proxbox, NetBox, and public companion plugins each own their
respective configuration and credential state.

`CLAUDE.md` is canonical. This wrapper repeats the safety and current-state
facts that an agent must have even when `@CLAUDE.md` expansion is unavailable:

- Keep changes inside the canonical Emerson repository. Never target EdgeUno.
- Preserve the public boundary and run `python scripts/check_public_boundary.py`.
- The private PBS matrix checkout uses `COMPANION_READ_SSH_KEY`, an encrypted
  Actions secret containing a read-only deploy key for
  `emersonfelipesp/netbox-pbs` only. Keep credential persistence disabled and
  keep the private key out of tests, logs, and artifacts.
- Scan built wheel and source archives with `--artifact`; the reviewed manifest
  covers name, domain, URL, command, path, package, service, distribution,
  workspace, retired contract, and private host identifiers; inspection
  failures are fatal.
- Keep the persisted `nmulticloud` InfluxDB organization default unchanged; it
  is public configuration and changing it requires a separately scoped
  additive compatibility migration.
- Treat disabled endpoints as a hard no-network gate.
- Keep credentials, console tickets, upstream URLs, and TLS decisions
  server-side and out of browser-readable output.
- Keep companion-plugin imports optional and lazy; enabled-but-broken
  companions fail at startup rather than degrading silently.
- netbox-openbao is optional. Automatic credential storage selects OpenBao only
  when the companion is enabled and otherwise selects local Fernet storage;
  explicit selections never fall back.
- Keep Proxmox endpoint API readiness response-local: derive serialized service
  monitoring eligibility from non-secret endpoint metadata plus response-local
  SSH and RPC readiness, preserve the guarded netbox-rpc model import before
  endpoint overrides, read each required global setting at most once per
  serializer, and derive OpenBao SSH readiness from one list-wide, actor-
  authorized credential metadata query without resolving credential material.
- Keep historical migrations immutable and add a migration for schema changes.
- Keep `ProxboxPluginSettings.sync_job_timeout` UI-backed and bounded to
  3600–604800 seconds. Resolve it when enqueueing a sync job, preserve explicit
  per-enqueue overrides, and never mutate the timeout of an already-running job.
- Keep `Dockerfile.oci` testing-only, preserve its separate NetBox and
  proxbox-api Python runtimes, and keep its OCI entrypoint equivalent to the
  Proxmox LXC `/sbin/init` path.
- Convert exact Data Protection schedules through the source endpoint's
  discovered IANA timezone; keep unresolved timing visibly approximate and cap
  combined calendar node selection at 50.
- Keep home dashboard badge and card hydration on one bounded four-worker pool;
  route initial requests and at most three coalesced retries per card through that
  pool, keep successful badge state independent from card errors, and render
  backend capacity responses as throttled rather than failed. Treat the Proxmox
  push cache as a hint and verify the cached backend endpoint identity before use.
- Keep the cluster Virtual Machines tab's selected-row Delete action routed to
  NetBox's core `VirtualMachine` bulk-delete endpoint. Never route selected VM
  IDs to the parent cluster delete action; preserve the version-checked action
  adapter and its real-Django regression.
- Update MkDocs sources, this wrapper, `CLAUDE.md`, and generated `llms.txt`
  together when architecture or operator behavior changes.
- Run focused tests, `mkdocs build --strict`, the public-boundary scanner, and
  a per-function complexity audit when executable source changes.

@CLAUDE.md

## Release Channel Sync Guardrail

The Gitea Package Registry must never go ahead of PyPI or Docker Hub. Agents
and operators must:

- publish a final or `.postN` version to the Gitea registry only in the same
  run that also publishes it to PyPI and, when applicable, Docker Hub. If the
  final-tag promotion, the GitHub Release, or any public publish step is
  blocked, stop before the Gitea final;
- never consume a version number only on Gitea: every release candidate goes
  to the Gitea registry and TestPyPI together, and private Gitea-only
  candidates are not allowed;
- choose the next version from the latest PyPI final, and refuse to start a
  release while the latest Gitea final differs from the latest PyPI final.

A Gitea-only `0.0.27.post1` and a private `0.0.28rc1` forced the public line to
jump from 0.0.27 to 0.0.29. See
[`docs/developer/release-publishing.md`](docs/developer/release-publishing.md#channel-sync-rule).

## LLM Agent Safety Guardrails

Automated agents must follow `AGENTS.md` § LLM Agent Safety Guardrails before any
destruction-adjacent workflow; inspection and explanation are allowed, confirmation
and approval are not.

Proxbox protects destruction behind a five-lock chain:

1. The `allow_delete` plugin setting must be enabled.
2. A human supplies the exact phrase `allow-edit-and-add-actions`.
3. The request explicitly sets `apply_destroy_confirmed=True`.
4. The requester holds the required delete permission.
5. A different authorized user approves the request because
   `self_approve_allowed=False`.

LLM agents **MUST NOT** submit the confirmation phrase, set
`apply_destroy_confirmed=True`, approve a request, or perform an equivalent
destruction-confirming action autonomously. `DeletionRequest` and
`ProxmoxApplyJob` REST endpoints are read-only; the protected UI and intent
workflow remain the only supported mutation paths.

The complete semantic bridge contract is
[`docs/api/semantic-mcp-bridge.md`](docs/api/semantic-mcp-bridge.md).

## Supported versions

The certified stable NetBox range is `4.5.8` through `4.7.99` (the whole 4.7 series is admitted by the numeric gate; CI verifies GA `4.7.0`). The current
plugin version is `0.0.29.post3`.

Current source pairing: netbox-proxbox 0.0.29.post3 <-> proxbox-api 0.0.23.post3 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This describes the current sibling source revisions, not a historical published-release promise. The netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

The last documented released runtime pairing for this release line remains
netbox-proxbox 0.0.27 <-> proxbox-api 0.0.23.post2 <-> proxmox-sdk 0.0.15
<-> netbox-sdk 0.0.13. Do not rewrite historical release notes when the source
pairing advances.

Current backend-runtime pairing: netbox-proxbox 0.0.29.post3 <-> proxbox-api 0.0.23.post3 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

## Current implementation surfaces

The current schema tip is migration `0105_reset_implicit_openbao_storage_default`.
Sensitive endpoint exports and runtime-key disclosure require an active,
authenticated superuser or the default-off per-user sensitive-data flag.
Only active superusers may administer grants. Keep object and provider checks
independent, resolve material with the request actor, and never cache grants.
Proxmox node Device names use the effective endpoint/global
`node_device_name_template`; keep the original short node name in Proxmox API
paths and typed sync-state identity.
The plugin provides endpoint and synchronized inventory models, typed sync
state, guest interfaces, SDN/firewall/Firecracker inventory, service
monitoring, metrics, browser consoles, intent/apply audit records, deletion
requests, and PBS/PDM companion endpoint records. `ProxboxSyncJob` owns staged
SSE synchronization; `ProxmoxServiceMonitoringJob` is the one-minute system
job. The `pxb` CLI provides configuration, backend and inventory inspection,
headless synchronization, and deterministic CLI documentation capture.
Optional PDM and RPC integrations require the companion plugin to be enabled in
NetBox, not merely importable. A package that is installed but disabled must not
render its tables or query its unmigrated settings model.
Staged runs isolate required-stage, firewall, and datacenter failures per
Proxmox endpoint, continue later endpoints, persist each failed scope, and fail
after all selected endpoints have been attempted. Backend-key and stage
throttling retries share bounded delta-seconds and HTTP-date `Retry-After`
parsing. Staged work uses one monotonic RQ-timeout deadline with a 120-second
persistence reserve; deadline exhaustion records the current and remaining
endpoint failures before finalization.

OpenBao endpoint writes select the exact configured policy slug and use
netbox-openbao's provider-owned transaction for UUID references, assignments,
material versions, audit witnesses, and post-commit metadata. Keep the pinned
NetBox 4.7 OpenBao CI cell aligned with its exact netbox-openbao and netbox-rpc
source commits and composed hash lock. Selected OpenBao-backed node SSH
passwords and keypairs create the primary `login` assignment on the linked
`dcim.Device`; unlinked nodes defer assignment, and link, relink, or unlink
changes reconcile it automatically. Required OpenBao reads fail closed without
a Fernet or unrelated credential-provider fallback. FastAPI, PBS, and PDM
tokens use `api-token` credentials assigned to their owner for the `api`
purpose, while Firecracker agent tokens use `api-token` with the `agent`
purpose. Their readiness and generic assignment selectors are secret-free and
provider-neutral. Explicit legacy storage continues to use Fernet.
VM cloud-init password and private-key inputs create `password` and
`ssh-keypair` credentials on the parent VM's `login` purpose, with
`ssh_pwauth` controlling the primary assignment. Public SSH keys never enter
OpenBao, and `credential_reference_id` remains external legacy metadata.
UI and REST credential/link mutations must enter the
provider material transaction before NetBox's atomic wrapper and carry the
request actor through that boundary. Raw/bulk ORM bypasses, parent cascades,
and OpenBao-to-legacy changes must refuse while owned references or assignments
remain and require explicit cleanup. Readiness and generic assignment selectors
may be exposed as secret-free metadata, but live node material remains confined
to the authenticated hardware credential endpoint.
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

Keep OpenBao-dependent real-Django suites isolated to the exact NetBox 4.7
OpenBao companion cell. Ordinary compatibility cells must prove the optional
package is absent without collecting provider-dependent tests. Tag-triggered
screenshots validate the immutable tag and never push generated assets; only a
manual screenshot refresh may write its selected branch.
`proxbox_openbao_setup --check` and the settings card consume the same typed,
secret-free readiness snapshot. Setup creates no users or credential material;
assignment backfill creates only missing relations and preserves shared-owner
primaries. It does not certify the broader RPC/backend protected-write rollout.
Exact existing relations must be enabled, match the declared primary state, and
reference the exact credential type; backfill reports drift without mutation or
UUID disclosure.
Interactive storage validation uses only provider, default-engine, and exact-
policy readiness. RPC and the automation service user remain composed-command
and panel checks. A failed final command check must roll back all setup writes.

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

## Connection approval recovery

Proxmox and remote NetBox endpoint detail pages expose explicit target review
and approval through the existing protected API. Do not automatically approve
existing targets on upgrade or save. Failed requests and stale reviews must
leave approval disabled until another review. Successful backend health does
not establish approval for a Proxmox destination. Preserve sensitive-data and
object permissions, CSRF protection, and server-side exact-target validation.

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

Native automatic telemetry setup requires `FASTAPI_OTEL_AUTO_CONFIGURE=true` (case-insensitive)
unless the explicit `auto_configure` dictionary value overrides it. Do not add
collector, service identity, or automatic setup environment defaults. SDK-disabled
regressions construct enabled caller providers first and require positive caller
exports after the actual application lifespan while SDK disablement stays set.
