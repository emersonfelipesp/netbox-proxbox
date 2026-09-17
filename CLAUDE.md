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
- The authoritative semantic bridge contract is
  [`docs/api/semantic-mcp-bridge.md`](docs/api/semantic-mcp-bridge.md).

## Supported versions

The certified stable NetBox range is `4.5.8` through `4.7.0` GA. The current
plugin version is `0.0.27rc4`.

Current backend-runtime pairing: netbox-proxbox 0.0.27rc4 <-> proxbox-api 0.0.22.post1 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

## GitHub matrix observation

`scripts/wait_for_github_django_matrix.py` is a base-pinned external supervisor
for `.github/workflows/django-tests.yml`. It is non-security evidence and cannot enforce
merge authorization or protect secrets. Prefer `GH_MATRIX_READ_TOKEN_FILE`
with a mode-`0600` or stricter file; `GH_MATRIX_READ_TOKEN` is a weaker fallback.
Removing an inherited environment value cannot erase the original process
environment from `/proc/<pid>/environ`. The bootstrap must remain non-consuming
and must not be treated as a security gate.

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
