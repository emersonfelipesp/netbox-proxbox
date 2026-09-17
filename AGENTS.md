# netbox-proxbox Agent Guide

`CLAUDE.md` is the source repository guide. Read and follow it before making
changes in this repository.

The EdgeUno repository and vendor checkout are read-only reference sources;
never edit or target them. Disabled endpoints are a hard no-network gate.
Console authentication, tickets, upstream URLs, secrets, and TLS decisions stay
server-side. The semantic bridge exposes only its documented typed manifest,
not a raw proxy. Proxbox, NetBox, and public companion plugins each own their
respective configuration and credential state.

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
