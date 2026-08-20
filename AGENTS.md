# Agent Entry Points

## Installation Docs: Two Traps

**Endpoint addresses depend on which container dials.** The `FastAPIEndpoint`
record is consumed by the NetBox container; the `NetBoxEndpoint` record is
consumed by the backend container. Both are filled in from the NetBox UI, which
makes the browser-visible address the tempting wrong answer for both. In a
single Compose project each needs the peer's **service name** and
**container-internal** port — never `localhost`, never a `127.0.0.1`-published
host port. The `8800` default on `FastAPIEndpoint.port` is correct only for a
standalone published container; keep both cases documented side by side rather
than replacing one with the other.

**The credential encryption key is an install-path prerequisite**, not a
configuration detail. The backend refuses to store a Proxmox credential without
one and says so only when the first endpoint is created. Keep the generate-and-
supply steps in `docs/installation/backend-setup.md` and cross-link the setting
semantics in `docs/configuration/plugin-settings.md`; do not duplicate them.
Answer key-change questions from `services/encryption_recovery.py`, not from
memory — rotation is verified and all-or-nothing, a lost key needs the
permission-gated destructive reset, and a backend still on the old key blocks
plugin rotation through the `/admin/encryption/status` attestation.


## Repository Destination Policy (Hard Rule)

This project is owned and changed only through the Emerson repositories:

- Development, issues, branches, commits, and pull requests:
  `https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox.git`
- Approved public promotion, mirroring, and releases through
  `deploy-workflow` only:
  `https://github.com/emersonfelipesp/netbox-proxbox.git`

The EdgeUno fork and `/root/personal-context/edgeuno/netbox-proxbox/` vendor
submodule are read-only reference sources. Never mutate EdgeUno issues, PRs,
comments, branches, commits, tags, releases, packages, mirrors, deployments,
remotes, upstreams, fallbacks, or PR bases, and never edit the vendor
submodule. Before every external write, inspect the exact owner/repository and
remote URL and abort unless it matches the allowlist above.

A stale cross-repository PR can display new source-branch commits without a
write to its base. Never rewrite or delete an Emerson branch to change an
EdgeUno PR. Do not attempt to close it from Emerson workflows; closure requires
the PR author or an actor authorized on the EdgeUno base repository.

## Pre-commit Checklist

Before committing any change:

1. Run syntax check: `python -m compileall netbox_proxbox tests`
2. Run linter: `rtk ruff check .`
3. Run type checker: `rtk ty check proxbox_cli`
4. Run mocked tests: `rtk pytest -p no:django tests/`

The mocked suite must disable pytest-django per invocation. Real model,
transaction, form, serializer, and signal behavior runs through
`.github/workflows/django-tests.yml` with pytest-django enabled. Endpoint
auto-configuration and the bridge request serializer each have an independent
85% branch-coverage floor there; see
[`docs/developer/endpoint-autoconfiguration.md`](./docs/developer/endpoint-autoconfiguration.md).

## Framework Stack

When implementing or changing behavior, prefer solutions in this order:

1. NetBox plugin idioms - patterns already used in this plugin and in NetBox's plugin framework.
2. NetBox core - `utilities.forms`, `utilities.views`, `netbox.*` bases, and NetBox-aligned DRF usage.
3. Django - standard `django.*` APIs when NetBox does not provide an equivalent.

Do not add new third-party PyPI dependencies to replace what NetBox or Django already provides. Existing runtime dependencies in `pyproject.toml` — `requests`, `websockets`, `pydantic` (used throughout `schemas/`), and the optional CLI extras — are fine.

## Security

Use NetBox view mixins from `utilities.views` (`ConditionalLoginRequiredMixin`, `TokenConditionalLoginRequiredMixin`, `ContentTypePermissionRequiredMixin`) for custom routes. Enforce object visibility with `QuerySet.restrict()`. Permission strings for ProxBox-specific operations are centralized in [`netbox_proxbox/views/proxbox_access.py`](./netbox_proxbox/views/proxbox_access.py); see [`CLAUDE.md`](./CLAUDE.md) for the current permission and workflow notes.

The read-only `/api/plugins/proxbox/mcp/` document is only a versioned producer
descriptor for a future compatible netbox-sdk plugin bridge. No released SDK
identity is currently activated; keep the checked activation artifact blocked
and do not present the descriptors as operational tools until exact immutable
SDK provisioning and paired CI are committed. Semantic tools must reuse existing
DRF endpoints and their permissions; do not add FastMCP, credentials, or a
parallel transport stack to this plugin. Mark sync scheduling destructive:
reconciliation can remove stale NetBox inventory records even though it does
not delete Proxmox guests or infrastructure. An activated SDK exposes generic
`plugin_list_tools` / `plugin_call_tool`; its mutation opt-in enables every MCP
write, not a single descriptor. Bridge v1 uses explicit concrete `sync_stages`,
does not advertise legacy `all` or `netbox_endpoint_ids`, and accepts only a
nonempty verified Proxmox scope, representable strict timezone-bearing RFC 3339
time, and an exactly-one-unit recurrence bounded to the persisted minute field.
Schema version 1 identifies the generic descriptor protocol, not a frozen
plugin payload. Endpoint PKs are bounded to positive signed 64-bit values.
Integer JSON literals retain that full range; integral float/Decimal forms
normalize only through `9007199254740991`, while unsafe larger floats, booleans,
strings, fractions, and non-finite numbers fail. Reject unknown properties,
duplicates, nonpositive/out-of-range IDs, and overlong names. `sync_stages`
selects the 13 SSE stages only: endpoint preflight and scoped cluster/node,
firewall, datacenter, and normally VM-template reconciliation still run. The
exact unique full set canonicalizes to internal `[all]` for recurring hints and
repair debounce without accepting `all` through MCP. Never
auto-retry an ambiguous schedule outcome. Keep the
manifest, DRF serializer, Proxbox-owned contract snapshot, blocked activation
artifact, immutable paired-SDK gate, and both MCP test suites aligned. The gate
must require an exact-commit SDK root whose complete `netbox_sdk/` package
inventory matches, exact released version plus full commit, fixed
relative module origin, isolated locked interpreter/dependency origins, and
package bytes materialized only after bounded commit/tree/blob graph validation
and explicit blob rehashing; never trust ambient `PYTHONPATH`,
dirty source, or a version string alone. Read
[`docs/api/semantic-mcp-bridge.md`](./docs/api/semantic-mcp-bridge.md) before
changing or invoking this surface.

## Configuration policy

**Prefer DB-backed plugin settings over `.env` variables.**
When adding a new runtime tunable that the plugin or the companion `proxbox-api`
backend needs to read, default to making it a
[`ProxboxPluginSettings`](./netbox_proxbox/models/plugin_settings.py) field —
NetBox-UI-editable and persisted in the NetBox database. On the backend it is read
via `proxbox_api.runtime_settings.get_int / get_float / get_bool / get_str`, which
already resolves **env var (override) → `ProxboxPluginSettings` → built-in default**
with a 5-minute settings cache.

Only fall back to a pure `.env` variable on the backend when the value is needed
**before** the NetBox connection exists or is **operator-only infrastructure** with
no business in the UI: `PROXBOX_BIND_HOST`, `PROXBOX_RATE_LIMIT`,
`PROXBOX_ENCRYPTION_KEY` / `PROXBOX_ENCRYPTION_KEY_FILE`, `PROXBOX_STRICT_STARTUP`,
`PROXBOX_SKIP_NETBOX_BOOTSTRAP`, `PROXBOX_GENERATED_DIR`,
`PROXBOX_CORS_EXTRA_ORIGINS`. Anything that controls sync behavior, batching,
concurrency, caching, or feature toggles belongs in `ProxboxPluginSettings`.

Do **not** invent shadow config layers (parallel JSON/YAML files, ad-hoc dotenv
sections, module-level constants meant as overrides) to dodge the migration cost.
A new field touches all five wiring points — model, migration, form, serializer,
template — and existing fields plus migration
[`0037_v0_0_15_release.py`](./netbox_proxbox/migrations/0037_v0_0_15_release.py)
show the pattern. See [`CLAUDE.md → Plugin settings and configuration`](./CLAUDE.md)
for the full keep-list.

The Ceph control-plane timing contract is persisted by migration `0077` as
`ceph_task_timeout`, `ceph_task_poll_interval`, and
`ceph_run_lease_seconds`. Preserve the model/form/API bounds and proxbox-api's
environment override → plugin value → default precedence. The polling
interval must not exceed the timeout at plugin boundaries, while proxbox-api
also normalizes environment-derived values. A run's independently renewed
lease is an immutable persisted snapshot, not a live mutable setting.

## Sync Mode Controls

Per-resource sync modes control how each Proxmox resource type is reflected into NetBox.
Three modes per type (global and per-endpoint — endpoint takes priority):

- **`always`** — sync on every run (default)
- **`bootstrap_only`** — create once, tag with `bootstrap-only`, never patch/delete again
- **`disabled`** — skip entirely, leave existing objects untouched

Ten resource types: `sync_mode_vm`, `sync_mode_vm_template`, `sync_mode_vm_interface`, `sync_mode_mac`, `sync_mode_cluster`, `sync_mode_node`, `sync_mode_storage`, `sync_mode_ip_address`, `sync_mode_sdn`, `sync_mode_sdn_bgp`.

`sync_mode_sdn` and `sync_mode_sdn_bgp` default to `disabled`. The **All** sync
choice includes the SDN stage after VM interface/IP-address stages, but stage
gating skips it until the effective SDN mode is enabled. SDN sync is read-only
against Proxmox and writes only NetBox L2VPN/L2VPNTermination/RouteTarget/Prefix
objects plus Proxbox plugin SDN metadata. `sync_mode_sdn_bgp` is a child mode
for optional `netbox_bgp` projection inside the SDN stage; it is forced disabled
whenever `sync_mode_sdn` is disabled.

Physical-NIC MAC reflection through SSH hardware discovery has an additional
plugin-only opt-in: `hardware_discovery_sync_nic_macs` defaults to `False` and
is effective only while `hardware_discovery_enabled=True`. Keep both fields on
the Hardware Discovery settings card and in the settings API. Disabling only
the MAC flag stops future native `dcim.MACAddress`/`primary_mac_address`
reconciliation without disabling chassis or NIC-link fact discovery.

VM interface sync now has a separate strategy setting:
`ProxboxPluginSettings.vm_interface_sync_strategy` defaults to
`guest_os_model`. In that mode Proxmox NICs remain core
`virtualization.VMInterface` rows named `net0`/`net1`, guest-agent OS names are
stored in plugin `GuestVMInterface` rows, and `GuestVMInterfaceAddress` links
to the same core `ipam.IPAddress` rows rather than duplicating IPs. The old
`use_guest_agent_interface_name` flag is deprecated and used only under
`legacy_rename`.

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

**VM templates** are stored in `ProxmoxVMTemplate` (not `VirtualMachine`). The model has optional FKs to `VirtualMachine` (`source_vm` and M2M `cloned_vms`), `ProxmoxCluster`, and `ProxmoxNode`.

Key files: `choices.py` (SyncModeChoices and VMInterfaceSyncStrategyChoices), `constants.py` (SYNC_MODE_FIELDS), `models/plugin_settings.py` (global fields), `models/guest_vm_interface.py` (guest OS interface inventory), `models/proxmox_endpoint.py` (per-endpoint fields + `effective_sync_mode()`), `models/vm_template.py` (ProxmoxVMTemplate), `models/sdn_inventory.py` (SDN metadata), `sync_stages.py` (gating helpers and backend query forwarding), `netbox_bootstrap.py` (bootstrap-only tag creation), `services/sync_vm_template.py` (template sync service), `docs/configuration/sync-modes.md` (user docs).

## Custom-field to model migration (complete)

The legacy Proxbox custom-field surface has been moved into plugin-owned
sidecar models under `netbox_proxbox/models/sync_state.py`. Every sidecar
inherits `ProxboxSyncStateBase`, which owns the shared `last_updated`
(`proxmox_last_updated`) and `last_run_id` (`proxbox_last_run_id`) columns.
VM and device sidecars reuse existing `ProxmoxEndpoint`, `ProxmoxNode`, and
`ProxmoxCluster` rows as nullable FKs, with text/raw fallback columns retained
for unresolved custom-field values. Virtual-disk and VM-interface sidecars keep
numeric unresolved storage/bridge IDs in `*_raw_id` and preserve non-numeric or
malformed legacy JSON payloads in `*_raw_value` text fallbacks before the legacy
JSON columns are removed. `virtualization.Cluster` uses a sidecar
(`ProxboxClusterSyncState`) instead of extending `ProxmoxCluster`, because
`ProxmoxCluster` is endpoint-scoped and links to NetBox clusters through a
nullable FK rather than a one-to-one relationship.

The VM sidecar also stores `proxmox_last_synced_role_id`, a nullable scalar
DeviceRole ID representing the role last written by sync. It deliberately is
not a foreign key, so deleting a DeviceRole does not erase the ownership
evidence used to preserve operator edits. Migration 0078 copies valid legacy
custom-field values without deleting them; the backend writes the typed
snapshot only after successful VM reconciliation.

These sidecars are now the standard source of truth: the proxbox-api
writer/reader switch has landed (commit `51866764`), so a normal sync writes
and reads the sidecars, rebuilt from live Proxmox data. The legacy reflection
custom fields are deprecated and gated behind
`ProxboxPluginSettings.custom_fields_enabled` (default `False`); by default
proxbox-api does not write, read, or reconcile custom fields. Setting the flag
`True` restores legacy custom-field behavior for a transition window and emits
deprecation warnings. Full custom-field removal is a later cleanup; no data is
deleted while the flag exists.

## Release Procedure (summary)

Official releases are cut **from `develop`** and triggered **only** by
GitHub release creation after the Gitea package and NMS production gates. The
public publish workflow listens to:

- `push: tags: v*rc*` → TestPyPI (release-candidate gate)
- `release: published` → PyPI (official releases)

Plain non-rc tag pushes (`vX.Y.Z`, `vX.Y.Z.postN`) do **not** trigger
publish. Use `gh release create vX.Y.Z --target develop --verify-tag
--title vX.Y.Z --notes-file docs/release-notes/version-X.Y.Z.md` to fire
the `release: published` event after the version bump commits are merged
into `develop`. Never `twine --skip-existing` — fix forward with the next
`.postN` or `rcN` per PEP 440. Full step-by-step in
[`CLAUDE.md → Release Procedure`](./CLAUDE.md).

## CI/CD Workflows

### Authenticated Django matrix bootstrap (not enabled)

Issue #300 adds the reviewed target-branch waiter at
`scripts/wait_for_github_django_matrix.py` and pins
`.github/workflows/django-tests.yml` by Git blob identity. The public matrix is
still **non-security evidence** because candidate code owns the installed
package and tests. Do not add or enable a Gitea consumer as part of this
bootstrap and do not describe its result as trusted evidence.

A future **base-pinned external supervisor** must execute the waiter from an
immutable reviewed base checkout, bind the trusted candidate branch to its full
SHA, and provide both the expected GitHub run ID and expected run-attempt
number. A UTC not-before creation time is only an optional additional bound,
never a standalone selector. The waiter requires GitHub's bare workflow path
`.github/workflows/django-tests.yml`, validates branch provenance separately
through `head_branch` and the exact run-name ref, and polls only
`/repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt}` from the
outset. A 404 is a bounded not-yet-visible state under the shared deadline and
request cap. Workflow-run list ordering or flooding cannot displace the pinned
pair, and a stale run or rerun attempt cannot satisfy the gate.
When `django-tests.yml` changes, keep the waiter on the previously reviewed
blob. Land and review the workflow first; update the base-owned pin only in a
second, separately reviewed change. A candidate workflow must never authorize
its own blob.
Only after that supervisor and its isolation are reviewed may a separate change
enable a consumer. Prefer `GH_MATRIX_READ_TOKEN_FILE`, naming a private token
file readable only by the waiter, so the token value never enters the process
environment. `GH_MATRIX_READ_TOKEN` remains a fallback, but popping it cannot
erase the original environment block: same-runner processes with proc access
can still read it from `/proc/<pid>/environ`, and Python startup hooks run before
the waiter can remove it. File ingress avoids those environment exposures.
Process and namespace isolation remain supervisor obligations that the waiter
cannot enforce. In either mode, the base-owned token must remain outside every
candidate checkout, environment, process, hook, and log. The waiter accepts
only a base-owner GitHub App user access token (`ghu_…`) that exposes exactly
one accessible app installation; that installation must belong to the base
owner and select only the exact Emerson repository with `Actions: read` and
`Contents: read`. Never weaken its fixed GitHub API allowlist,
ambient-proxy and redirect refusal, shared deadline, response cap, or request
budget. See
`docs/developer/ci-e2e-workflows.md` for the bootstrap order and full trust
boundary.

### End-to-end release pipeline (Gitea-first)

The official release pipeline runs in this order:

1. **Activation gate** — do not merge the target cutover until the private control repository has a positive policy-pinned ID and its protected workflows, host boundaries, sockets, and repository-scoped runners pass readiness. Leave the existing publisher active until then.
2. **Gitea tag push** — push an annotated RC or final tag to Gitea.
3. **Data-only request** — `.gitea/workflows/publish-gitea.yml` gives both release jobs `actions: read` plus `contents: read` only for checksum-pinned runner/CI evidence gates. Both jobs use repository-unique `ci-release-netbox-proxbox`, and before candidate processing their trusted gate requires the live runner ID, name, and sole label to equal `.gitea/release-runner-acceptance.json` plus a fresh signed external-supervisor attestation bound to repository/run/job/source, complete registered labels, runtime image, and network/runtime policy. Zero/empty identity and all-zero key/image/policy digests keep tag releases disabled until exact live acceptance is reviewed; missing, stale, invalidly signed, or mismatched job evidence fails before candidate execution. The build fetches validated public source without checkout credentials and never passes its step-scoped Gitea token across the candidate boundary. Gitea's public-repository floor can still make public Actions data readable, and the outer job receives an artifact runtime token. All candidate-controlled dependency installation/build/check/manifest work therefore runs behind a separate numeric UID, minimal token-free environment, no-new-privileges, a fail-closed x86-64 Landlock ABI 3+ write allowlist limited to the per-run build root, a fail-closed x86-64 seccomp deny for every socket syscall, all `io_uring` entry points, and every x32-tagged syscall, exact immutable wheelhouse revalidation, hard cgroup-v2 one-CPU/2-GiB/zero-swap/64-PID ceilings, a hard one-GiB/50,000-inode `/nmc-build` tmpfs, parent-enforced 900-second-wall/live-plus-reaped-CPU/RSS/PID/logical-size/filesystem-block/file-count/output checks, root-parent `/proc` denial, and surviving-process cleanup. Linux CPU records are parsed after the process-name delimiter so whitespace in candidate names cannot evade aggregate accounting. The filesystem boundary prevents candidate writes to runner workflow-command files and shared temporary storage. The activation canary must prove that the exact accepted runner/container denies management and production network access, bind that result and runtime digest to the same runner ID, and re-attest the live state for every job; a label or historical canary is insufficient evidence. Candidate output is captured rather than passed to the runner command parser; live legacy command probes must not affect the next step. Reviewed outer code copies an exact bounded regular-file inventory with no-follow descriptors and re-hashes each copy. After candidate process cleanup, the root-only external supervisor signs a canonical completion statement binding the initial attestation, live job/runner policy, request digest, and every final artifact byte; candidate code cannot access the signer socket. The controller independently verifies that signature before sealing. Candidate code receives no job, runtime, package, mirror, or write credential and cannot publish or push tags.
   The workflow is globally serialized per repository. Validation and build have independent pinned repository-registration scope digests, and the completion statement binds the supervisor-derived build digest; the target client and controller require each role's evidence to equal its pinned acceptance value. Every RC, final, or post request consumes its ephemeral validation/build pair, so the next request requires freshly registered and reviewed identities.
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

4. **Locked validation and publication** — dispatch `validate.yml` first, then the separate irreversible `publish.yml`, each with exactly the repository name, first-attempt target run ID, and request SHA-256. The isolated builder verifies and seals the bytes; the isolated publisher uploads the exact package and promotes only RC tags to GitHub.
5. **Production gate** — link and verify the final Gitea package, then deploy through NMS with `latest_package` by default (or explicitly selected `main_branch`).
6. **Public promotion** — after production health validation, promote the final tag and create the GitHub Release; `release: published` authorizes PyPI.

### RC (release-candidate) pipeline

1. Push a `vX.Y.ZrcN` tag to Gitea and wait for its `release-control-request` artifact.
2. Hash `release-request.json`; dispatch `validate.yml`, then `publish.yml`, with exactly `repository=netbox-proxbox`, the target run ID, and that SHA-256. The control publisher publishes the Gitea bytes and promotes only that RC tag to GitHub.
3. `.github/workflows/publish-testpypi.yml` fires on `push: tags: v*rc*` → publishes the exact Gitea bytes to TestPyPI.

### Immutable-version guarantee

Uploads never use `--skip-existing`. A version consumed in Gitea, TestPyPI, or
PyPI must never be replaced with different bytes; advance to the next `rcN` or
`postN` and record it in the release ledger.

### Gitea Package Registry

The target workflow uses the runner image's exact Python 3.12.14 and uv 0.12.5
after verifying the baked interpreter/tool versions, the policy-pinned
`uv.lock` digest, and the build-lock checksum manifest for its read-only
wheelhouse. Dependency resolution is offline (`--no-index`, no Python
downloads). The trusted outer steps use image-baked Gitea checkout and artifact
clients, so their only network authority is same-origin Gitea access. Two
job-bound ephemeral
`ci-release-netbox-proxbox` registrations provide distinct validation and build
runner identities; each advertises only that release label and terminates after
its one assigned job.
The job produces exactly the package wheel, package sdist,
`release-manifest.json`, `release-request.json`,
`runner-completion-attestation.json`, and
`runner-completion-attestation.sig`. The request
binds the repository ID, source/tag/version, first-attempt run identity,
workflow digest, manifest digest, and artifact inventory. The target repository
holds no package or mirror credential. The separately administered control
plane verifies the policy-pinned target workflow and every byte on an isolated
builder, seals the handoff, and lets only an isolated publisher read credentials
or invoke fixed digest-locked publication tooling. Public no-authority downloads
must match the manifest before the durable ledger advances. The registry URL is
`https://git.nmulti.cloud/api/packages/emersonfelipesp/pypi`.
The publish workflow deliberately accepts tag `push` events, not Gitea's
overlapping `create` event. Gitea emits both for a tag; subscribing to both
starts duplicate immutable uploads of one version. A consumed or failed version
is never retried; fix forward with the next immutable version.

### Security

- `publish-gitea.yml` accepts only a canonical version tag that equals current
  Gitea `develop`; writer-controlled commit statuses are ignored, and the
  newest authenticated `ci.yml` Actions run plus its required jobs must prove
  a successful first push attempt for that exact SHA,
  trusted actor, expected job, and untrusted runner class.
- The target workflow cannot publish. The control builder and publisher use
  separate identities, state, runtime directories, and locked executables; the
  registry package is linked to this repository and byte-compared with its
  canonical manifest.

## Gitea-to-GitHub Mirror

The Gitea workflow at `.gitea/workflows/mirror-github.yml` mirrors only
approved source branches to the matching GitHub repository. For this repo the
allow-list is `develop` and `main`; `develop` is the staging branch and `main`
is the production branch. The workflow uses
the Gitea Actions secrets `GH_MIRROR_TOKEN` for GitHub and
`SOURCE_MIRROR_TOKEN` for authenticated Gitea source fetches, runs on the
dedicated `mirror-host` runner label, authenticates with `gh`, configures
GitHub git credentials through `gh auth setup-git`, and pushes only
`HEAD:refs/heads/${{ gitea.ref_name }}`. Do not replace it with `git push
--all`, `git push --mirror`, or tag synchronization.

## Branch-tier Deployment

The deployment workflow at `.gitea/workflows/deploy-production.yml` deploys a
reviewed `develop` push to staging. Production is manual and dispatched by the
NMS package-backed target from canonical `main`: `latest_package` requires the
exact Gitea version and is the default, while `main_branch` is an explicit
override. A successful package deployment publishes immutable, repository-
linked completion evidence for the public-promotion gate, but those bytes are
issued only by the root-owned fixed helper after exact import and health proof;
workflow code cannot create them.

## Navigation

Read [`CLAUDE.md`](./CLAUDE.md) first for the plugin architecture and documentation map. Use the lower-level `CLAUDE.md` files when working in a specific directory or when changing only one layer of the plugin.

Key architectural invariants to keep in mind:

- **`NetBoxEndpoint` and `FastAPIEndpoint` are singleton-shaped.** The backend proxy (`services/backend_proxy.py`) and dashboard views resolve the first enabled backend row. Import views enforce the singleton constraint — if a record exists, the user is prompted to confirm the override before the existing record is deleted and replaced.
- **Primary endpoint secrets are encrypted at rest.** `ProxmoxEndpoint.password`, `ProxmoxEndpoint.token_value`, `FastAPIEndpoint.token`, `PBSEndpoint.token_secret`, and `PDMEndpoint.token_secret` are public Python properties backed by Fernet-encrypted `*_enc` model fields. Runtime setters use `ProxboxPluginSettings.encryption_key` and create one when storing a primary secret if it is blank; do not reintroduce plaintext model fields for those secrets.
- **Plugin encryption recovery is registry-driven and atomic.**
  `services/encryption_recovery.py::ENCRYPTED_FIELD_FAMILIES` must contain every
  plugin model `*_enc` field plus the optional netbox-pbs
  `PBSPluginSettings.proxbox_api_key_enc` field and the trust fingerprints
  invalidated by a destructive reset. An optional app is omitted only when both
  its Django registration and known table are absent; dormant ciphertext and
  installed owners with unresolved models/tables fail closed.
  Ordinary key mutation is blocked while ciphertext exists, and both the
  default and base-manager queryset/bulk APIs reject direct
  `ProxboxPluginSettings.encryption_key` writes. Verified rotation owns the one
  exact settings-locked key-update permit. Registered model
  saves (including optional netbox-pbs) lock the settings row, validate their
  ciphertext under that key, and persist within that transaction; direct
  queryset/bulk encrypted-field writes are rejected before SQL through both
  reachable manager classes. Conflict upserts may not name reset-protected
  trust or operational fields unless a private settings-locked internal permit
  authorizes that exact call. Only the private
  one-call rotation/reset/adoption update may write raw ciphertext, and it must
  hold the settings-row lock and validate every outgoing non-empty value against
  the key currently stored there; bulk create/update has no bypass. Rotation uses the same
  settings-row order followed by deterministic PostgreSQL table locks before
  verifying all ciphertext and performing one transactional rewrite. Complete
  ciphertext verification may recover a drifted stored setting; when no
  ciphertext exists, the supplied old key must match the stored value. Rotation
  also requires every configured proxbox-api target to authenticate and return
  the versioned attestation that its active cached key is independent
  (`env`/`local`) and decrypts every backend ciphertext. Legacy source-only,
  unavailable, or invalid attestations block rotation. The credentialed request
  dials the same immutable target capture whose trust fingerprint was checked.
  Lost-key reset is separately permissioned, explicitly confirmed, selective,
  disables
  affected endpoints (or marks Firecracker hosts offline), and uses
  non-signaling queryset updates. Recovery POST values, settings serializer
  mutations, and the key-bearing settings-model save frame are
  exception-reporter sensitive, and each attempt emits a secret-free NetBox
  changelog event. Keep
  the plugin-at-rest key separate from
  proxbox-api database encryption and FastAPI request authentication. Ordinary
  settings serializers withhold it; the backend-only runtime route retains its
  existing permission-gated compatibility response until a paired proxbox-api
  migration removes that fallback.
- **Backend API-key adoption is fail-closed.** `FastAPIEndpoint.save()` and
  every UI/import/API persistence path share
  `services.backend_key_adoption.adopt_rotated_backend_key()`. Keys are never
  exposed or recovered from the backend. A new disabled row stays keyless and
  performs no discovery. An enabled save without an explicit candidate commits
  a pending row with a blank fingerprint and encrypted candidate, then invokes
  `services.endpoint_autoconfiguration` through `transaction.on_commit`. The
  service treats the exact UI-persisted URL/IP, port, and TLS policy as its complete
  allowlist, probes identity/readiness without credentials, and authenticates
  the existing encrypted key. It generates and retains a key only for a
  confirmed empty backend's one-time bootstrap. With no row, startup discovery
  is bounded to plugin configuration and same-site names derived from NetBox's
  trusted origin; it never scans or follows redirects. An initialized backend
  with no locally held key stays pending. Explicit token submission remains the
  manual rotation/recovery path. A credential-free
  `backend_key_target_fingerprint` durably binds the ciphertext to the
  canonical primary HTTP target, fallback IP, TLS flags, and WebSocket target
  flags; runtime lookups recompute it using a fresh IP FK and fail closed on
  drift. HTTP and WebSocket adoption rejects redirects, the WebSocket client
  disables ambient proxies and rechecks trust throughout its lifetime, and
  endpoint saves cancel stale clients. Never treat HTTP 409 as success, expose
  token previews, or include response or transport text in key errors. Keep the
  state machine and automated evidence aligned with
  [`docs/developer/endpoint-autoconfiguration.md`](./docs/developer/endpoint-autoconfiguration.md).
- **`enabled=False` is a hard no-connection gate for endpoint-like rows.** Disabled `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `PBSEndpoint`, `PDMEndpoint`, and companion endpoint rows remain visible inventory records, but operational paths must return before pushing to proxbox-api, registering keys, fetching OpenAPI/status, resolving backend ids, hydrating dashboard/status cards, scheduling jobs, or calling live HA/storage/firewall/SDN/datacenter routes.
- **Disabled Proxmox status badges stay static.** List, detail, and dashboard Proxmox status elements must show a gray `Disabled` badge without `data-service-status-url` when `enabled=False`; the direct keepalive endpoint may return `status="disabled"` only as a defensive fallback.
- **Proxmox connection tuning is model-resolved.** Nullable endpoint timeout/retry/back-off values inherit `ProxboxPluginSettings` through `ProxmoxEndpoint.effective_connection_tuning()`; explicit values win when they are not `None`, including zero retries/back-off. Push only the resulting concrete values to proxbox-api — never JSON `null` inheritance markers. Treat a backend row whose public timeout/retry/back-off differs or is missing as stale and push-required even after the soft preflight budget expires.
- **Task history has one stage owner.** Virtual-machine stage requests must include `sync_task_history=false`; the dedicated task-history stage performs that supplementary work and owns its failure handling. This is a paired backend fix: deploy the wire-compatible proxbox-api bounded task-history implementation first, then the plugin. Plugin-first does not break the API, but it does not complete the timeout remediation while the dedicated stage still runs on an old backend.
- **Proxmox endpoint bulk enablement is local-only.** The `/plugins/proxbox/endpoints/proxmox/` list shows `Enabled` by default and exposes **Enable Selected** / **Disable Selected** actions. Keep those actions as direct `ProxmoxEndpoint.enabled` queryset updates; do not save each object or trigger the ProxmoxEndpoint `post_save` backend-registration/sync signal from bulk toggles.
- **Firecracker inventory is separate from QEMU/LXC.** Use `FirecrackerHostPool`, `FirecrackerHost`, `FirecrackerImageTemplate`, and `FirecrackerMicroVM` for NMS Cloud micro-VMs. A Firecracker row exposes `kind="firecracker"` and `instance_ref="firecracker:<id>"`; do not model it as a NetBox core `VirtualMachine`.
- **Guest OS interfaces are separate from core VM interfaces.** Do not rename a core `VMInterface` from `net0` to `ens18` under the default `guest_os_model` strategy. Store guest-agent interface names in `GuestVMInterface`, link by MAC to the core `VMInterface` when possible, and reuse existing `ipam.IPAddress` rows via `GuestVMInterfaceAddress`.
- **Firecracker tenant grants are API-visible Cloud policy.** `FirecrackerHostPoolSerializer` and `FirecrackerImageTemplateSerializer` treat an omitted `allowed_tenants` field as no-op, while an explicit list (including `[]`) replaces the M2M grants through `allowed_tenants.set(...)`. Keep those serializer helpers typed and covered by source-contract tests when changing NMS Cloud visibility behavior.
- **`ProxmoxEndpoint.allowed_tenants` is a real Cloud contract, not UI-only metadata.** Empty means default/global visibility. Explicit tenant grants pin an endpoint to those tenants, and the paired backend must hide the default/global endpoint pool for a tenant as soon as any explicit endpoint grant matches.
- **Proxmox endpoint service monitoring is netbox-rpc mediated.** netbox-proxbox only creates asynchronous `RPCExecution` rows for `os.linux.proxmox.show_systemctl_services`; it does not perform SSH itself and must not import `netbox_rpc` at module import time. The opt-in gate is `allow_writes=True` + `access_methods="api_ssh"` + complete endpoint SSH credentials, and the RPC backend uses the endpoint's own SSH credential. Projection is two-phase: pending `ProxmoxServiceCollection` at enqueue time, then `project_completed_collections()` reconciles finished `execution.result` payloads into samples, latest statuses, and heartbeat fields.
- **Cloud-customer networking is settings-backed.** `ProxboxPluginSettings` stores the operator-designated cloud customer Prefix ID, bridge, VLAN tag, gateway, and lock flag. Populate those fields with the idempotent `python manage.py ensure_cloud_customer_network --prefix ... --vlan ... --gateway ... [--enable-lock]` command; do not hardcode estate-specific cloud network values in plugin, proxbox-api, or nms-backend code.
- **Endpoint export views require token proof for sensitive fields.** `_validate_sensitive_export_token()` supports v1 (dropdown or manual) and v2 (key + secret) modes. Never bypass this check or expose credential fields without it.
- **Export JS is inlined, not a separate static file.** All three endpoint list templates contain the export-modal IIFE directly in `{% block javascript %}`. Do not move it to a `.js` file — it would then require `collectstatic` to be served.
- **Import forms auto-create IPAddress objects.** All three import forms call `IPAddress.objects.get_or_create` in `clean_ip_address()`. Do not replace this with `CSVModelChoiceField` for `ip_address` — that would break cross-instance imports.

## Code Quality Standards

All changes to netbox-proxbox MUST conform to these quality gates before PR review:

### Code Coverage
- Measure mocked-suite coverage: `rtk pytest -p no:django tests/ --cov=netbox_proxbox --cov-report=term-missing`
- Enforce coverage in the harness that executes the changed production logic;
  endpoint auto-configuration has an 85% real-Django branch floor.
- Document uncovered code with a rationale comment (e.g., "except: pass for legacy compat")

### Regression Testing
- Add a test that fails on pre-fix code before implementing any fix
- Run the full mocked suite: `rtk pytest -p no:django tests/ --timeout=30 -v`
- Run mocked integration tests: `rtk pytest -p no:django tests/integration/ -v --timeout=30`
- Validate against E2E Docker stack before release

### Static Analysis

**Ruff (linting):**
```bash
rtk ruff check .          # Errors, style, unused imports
rtk ruff format --check . # Code formatting
```
Fixes errors before pushing. All violations block CI.

**Type Checking (Pyright strict):**
```bash
rtk ty check proxbox_cli
```
Type mismatches block merge. Use `# type: ignore` only with justification.

**Defect Categories Detected:**
- Undefined variables, imports, method/attribute access
- Unused imports and dead code
- Security: SQL injection, unsafe eval, XSS vectors
- Type mismatches (via Pyright strict)

### Requirements Validation

Before writing code, confirm:
1. The feature is traceable to a GitHub issue (link it in the PR description)
2. The design is documented (update nearest CLAUDE.md with architecture notes)
3. You understand how it affects the backend integration (proxbox-api contracts)
4. You've identified all derived requirements (e.g., "sync behavior must be gated")

### Configuration Control

Changes to these configuration items require explicit PR description and CLAUDE.md update:
- Plugin version (`netbox_proxbox/__init__.py` `__version__`)
- NetBox compatibility floor/ceiling (`min_version`, `max_version`)
- Backend service minimum version (`proxbox_api` floor in `pyproject.toml`)
- Database schema (any model/migration change)
- Backend integration contracts (sync routes, SSE payloads, job queue names)

### Safety Model (Intent Workflows)

If your change touches the Proxmox-side mutation path:
1. Verify the default direction remains Proxmox → NetBox (read-only)
2. Confirm that master flag `netbox_to_proxmox_enabled` requires typed confirmation
3. Check that DELETE goes through `DeletionRequest` (no direct destroy calls)
4. Verify authorization permission is separate from the request permission

Violating any of these four invariants is a regression.

## CLAUDE.md Index

Read the nearest scoped guide for the code you are changing.

- [CLAUDE.md](CLAUDE.md)
- [netbox_proxbox/CLAUDE.md](netbox_proxbox/CLAUDE.md)
- [netbox_proxbox/api/CLAUDE.md](netbox_proxbox/api/CLAUDE.md)
- [netbox_proxbox/forms/CLAUDE.md](netbox_proxbox/forms/CLAUDE.md)
- [netbox_proxbox/management/CLAUDE.md](netbox_proxbox/management/CLAUDE.md)
- [netbox_proxbox/management/commands/CLAUDE.md](netbox_proxbox/management/commands/CLAUDE.md)
- [netbox_proxbox/migrations/CLAUDE.md](netbox_proxbox/migrations/CLAUDE.md)
- [netbox_proxbox/models/CLAUDE.md](netbox_proxbox/models/CLAUDE.md)
- [netbox_proxbox/schemas/CLAUDE.md](netbox_proxbox/schemas/CLAUDE.md)
- [netbox_proxbox/services/CLAUDE.md](netbox_proxbox/services/CLAUDE.md)
- [netbox_proxbox/static/CLAUDE.md](netbox_proxbox/static/CLAUDE.md)
- [netbox_proxbox/static/netbox_proxbox/CLAUDE.md](netbox_proxbox/static/netbox_proxbox/CLAUDE.md)
- [netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md](netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md)
- [netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md](netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md)
- [netbox_proxbox/tables/CLAUDE.md](netbox_proxbox/tables/CLAUDE.md)
- [netbox_proxbox/templates/CLAUDE.md](netbox_proxbox/templates/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md)
- [netbox_proxbox/templatetags/CLAUDE.md](netbox_proxbox/templatetags/CLAUDE.md)
- [netbox_proxbox/views/CLAUDE.md](netbox_proxbox/views/CLAUDE.md)
- [netbox_proxbox/views/endpoints/CLAUDE.md](netbox_proxbox/views/endpoints/CLAUDE.md)
- [netbox_proxbox/views/sync_now/CLAUDE.md](netbox_proxbox/views/sync_now/CLAUDE.md)
- [proxbox_cli/CLAUDE.md](proxbox_cli/CLAUDE.md)
- [tests/CLAUDE.md](tests/CLAUDE.md)

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

## LLM Agent Safety Guardrails

**STOP — read this section before any intent-driven destroy or deletion.**

netbox-proxbox implements a multi-lock safety chain that prevents unintended VM
destruction. LLM agents interacting with this plugin MUST respect all locks and
MUST NOT attempt to autonomously satisfy them.

### Five-Lock Destroy Chain — All Locks Require Human Action

| Lock | What it is | Who sets it |
|---|---|---|
| 1. `netbox_to_proxmox_enabled` | Master feature flag | Human operator |
| 2. Confirmation phrase | User must type `"allow-edit-and-add-actions"` | Human operator |
| 3. `apply_destroy_confirmed` | Per-intent-branch destroy confirmation | Human approver |
| 4. RBAC at request time | User must have delete permission | NetBox admin |
| 5. `self_approve_allowed=False` | Approver must not be the requester | System invariant |

An LLM agent MUST NOT:
- Set `apply_destroy_confirmed=True` on any intent branch autonomously.
- Submit the confirmation phrase on behalf of a user.
- Approve a `DeletionRequest` as the same user who created it.
- Attempt to bypass or work around any of the five locks.

### Transport Access Method — `ProxmoxEndpoint.access_methods`

Each `ProxmoxEndpoint` declares a transport access method, orthogonal to the
destroy chain and to write permissions: `api` (Read+Write over the Proxmox API
only, the default) or `api_ssh` (API + SSH). **SSH only complements API; there
is no SSH-only option.** This is the load-bearing gate for the browser SSH
terminal — `netbox_proxbox/api/ssh_credentials.py` refuses to release SSH
secrets (403) for an API-only endpoint, which blocks the terminal at the
credential source for both endpoint-target and node-target sessions.

An LLM agent MUST NOT set `access_methods="api_ssh"` autonomously to unlock SSH;
it is a human operator assertion. The value is pushed to proxbox-api so the
backend can gate its own SSH paths (cloud-image / Azure VHD import).

### `DeletionRequest` REST API — Read-Only

The `DeletionRequest` REST endpoint at `/api/plugins/proxbox/deletion-requests/`
is **read-only** (`GET`, `HEAD`, `OPTIONS` only — `http_method_names` enforced
in the viewset). LLM agents can read deletion requests for informational
purposes but cannot create, update, or delete them via the REST API.

### Destructive Intent Operations — Explicit Human Confirmation Required

| Operation | Effect | Reversible? |
|---|---|---|
| Intent apply with `apply_destroy_confirmed=True` | Permanently deletes Proxmox VM/LXC | **No** |
| Intent branch merge after destroy confirmation | Applies all planned deletes | **No** |

### Required Human Confirmation Protocol

Before any destruction-adjacent intent operation, an LLM agent MUST:

1. **Name the specific resource** — VM name, VMID, cluster, and node.
2. **List the five-lock chain state** — which locks are currently satisfied
   and which are still pending.
3. **Wait for explicit human approval** — a message from the user that
   unambiguously confirms the operation on the named resource.
4. **Never act as both requester and approver** — the four-eyes invariant is
   enforced at the code level (`self_approve_allowed=False`) and must not be
   circumvented.

**Enforcement locations:**
- `netbox_proxbox/api/views.py::DeletionRequestViewSet.http_method_names` — read-only `["get", "head", "options"]` enforces the four-eyes approval gap at the REST layer
- `netbox_proxbox/api/views.py::ProxmoxApplyJobViewSet.http_method_names` — read-only enforcement on apply-job state (jobs are created only through intent branch-merge workflow)
- `tests/test_static_guardrails.py` — static contract tests that pin `http_method_names`, `self_approve_allowed=False`, the five-lock chain, and the confirmation phrase presence in AGENTS.md
