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
- Keep historical migrations immutable and add a migration for schema changes.
- Keep `Dockerfile.oci` testing-only, preserve its separate NetBox and
  proxbox-api Python runtimes, and keep its OCI entrypoint equivalent to the
  Proxmox LXC `/sbin/init` path.
- Convert exact Data Protection schedules through the source endpoint's
  discovered IANA timezone; keep unresolved timing visibly approximate and cap
  combined calendar node selection at 50.
- Update MkDocs sources, this wrapper, `CLAUDE.md`, and generated `llms.txt`
  together when architecture or operator behavior changes.
- Run focused tests, `mkdocs build --strict`, the public-boundary scanner, and
  a per-function complexity audit when executable source changes.

@CLAUDE.md

## LLM Agent Safety Guardrails

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

The certified stable NetBox range is `4.5.8` through `4.7.0` GA. The current
plugin version is `0.0.27rc11`.

Current source pairing: netbox-proxbox 0.0.27rc11 <-> proxbox-api 0.0.23.post1 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This describes the current sibling source revisions, not a historical published-release promise. The netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

The last documented released runtime pairing for this release line remains
netbox-proxbox 0.0.27rc4 <-> proxbox-api 0.0.22.post1 <-> proxmox-sdk 0.0.13
<-> netbox-sdk 0.0.13. Do not rewrite historical release notes when the source
pairing advances.

Current backend-runtime pairing: netbox-proxbox 0.0.27rc11 <-> proxbox-api 0.0.23.post1 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

## Current implementation surfaces

The current schema tip is migration
`0102_vm_cloudinit_openbao_references`.
The plugin provides endpoint and synchronized inventory models, typed sync
state, guest interfaces, SDN/firewall/Firecracker inventory, service
monitoring, metrics, browser consoles, intent/apply audit records, deletion
requests, and PBS/PDM companion endpoint records. `ProxboxSyncJob` owns staged
SSE synchronization; `ProxmoxServiceMonitoringJob` is the one-minute system
job. The `pxb` CLI provides configuration, backend and inventory inspection,
headless synchronization, and deterministic CLI documentation capture.

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
