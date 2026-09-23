# netbox-proxbox Repository Guide

> **LLM Agent Safety:** Before any destruction-adjacent operation, read
> `AGENTS.md` § "LLM Agent Safety Guardrails". Automated agents may inspect and
> explain protected workflows, but they may not supply human confirmation or
> approval on an operator's behalf.

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

The certified stable NetBox range is `4.5.8` through `4.7.0` GA. The current
plugin version is `0.0.27rc13`.

Current source pairing: netbox-proxbox 0.0.27rc13 <-> proxbox-api 0.0.23.post1 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This describes the current sibling source revisions, not a historical published-release promise. The netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

The last documented released runtime pairing for this release line remains
netbox-proxbox 0.0.27rc4 <-> proxbox-api 0.0.22.post1 <-> proxmox-sdk 0.0.13
<-> netbox-sdk 0.0.13. Preserve release-note and compatibility rows as
historical records unless a release workflow changes them.

Current backend-runtime pairing: netbox-proxbox 0.0.27rc13 <-> proxbox-api 0.0.23.post1 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

CI pairing: the E2E Docker, page-coverage, documentation-screenshot, and
release-validation workflow defaults consume proxbox-api `0.0.23.post1`. E2E uses the
exact published image by default; GitHub source-head builds require explicit
`dependency_mode: dev`. Repository variables are equality-checked configuration:
release preparation fails closed when an implicit value does not equal the
checked-in current default, and a coordinated candidate requires an explicit
workflow input. TestPyPI plugin candidates use stable proxbox-api `0.0.23.post1` from
PyPI because that backend version is not published on TestPyPI. The E2E harness
uses typed sync-state sidecars and must not call the removed proxbox-api custom-
field creation route.

## Current source map

- Models include endpoint configuration, synchronized cluster/node/storage/VM
  data, typed sync-state sidecars, guest interfaces, SDN and firewall
  inventory, Firecracker inventory, service-monitoring collections, metrics,
  intent/apply records, deletion requests, cloud-init records, and companion
  PBS/PDM endpoint records. Migration
  `0102_vm_cloudinit_openbao_references`
  is the current schema tip.
- UI routes include the home/dashboard, data-protection calendar, HA, endpoint
  and inventory views, model-scoped Sync Now actions, repair/recovery flows,
  soft-deleted VM review, and standalone VM console sessions. Cluster and node
  detail routes are mounted through NetBox model URLs so their Sync Now actions
  resolve correctly.
  Data Protection scheduled events use the source endpoint's best-effort
  discovered IANA timezone and convert exact wall-clock occurrences to
  NetBox's active timezone before day bucketing. Fail-open cases remain visibly
  approximate, and combined node selection is capped at 50.
- REST routes expose typed endpoint and inventory viewsets, sync-state
  sidecars, SDN/firewall/Firecracker resources, service monitoring, jobs,
  settings, semantic MCP manifest discovery, browser-console session creation,
  and operational actions. The API is not a generic backend proxy.
- `ProxmoxServiceMonitoringJob` is a one-minute system job;
  `ProxboxSyncJob` owns the staged SSE synchronization pipeline. The standalone
  `pxb` CLI covers local configuration, backend inspection, NetBox/Proxmox
  resources, headless sync, and deterministic CLI documentation capture.
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

The Django workflow includes one immutable NetBox 4.7 cell that installs and
registers netbox-proxbox together with netbox-ceph, netbox-pbs, netbox-pdm, and
netbox-packer. Keep every companion checkout pinned by commit, verified by HEAD
and pyproject digest, resolved from the reviewed hash-locked input, and covered
by the post-migration registry and system-check assertions. This GitHub evidence
does not replace a required Gitea pre-merge gate.

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

## Safety invariants

- Never log, serialize, export, or render plaintext passwords, private keys,
  API keys, tokens, or encryption keys.
- Credentialed HTTP requests must reject redirects, validate their destination,
  use bounded timeouts, and verify TLS by default.
- Destructive Proxmox operations require explicit permission and the repository's
  approval or intent workflow. Do not weaken four-eyes or confirmation gates.
- Keep optional companion-plugin imports lazy and fail safely when unavailable.
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
