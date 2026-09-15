# `proxbox_cli`

> **Repository destination guardrail:** This guide inherits the hard rule in
> the repository-root `CLAUDE.md`. EdgeUno and the local EdgeUno vendor
> submodule are read-only reference sources, never change destinations. All
> development writes must target exactly
> `https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox.git`; approved
> public promotion may target only
> `https://github.com/emersonfelipesp/netbox-proxbox.git`. Never mutate EdgeUno
> issues, PRs, branches, commits, tags, releases, packages, mirrors, or
> deployments, and never configure EdgeUno as a writable remote, upstream,
> fallback, or PR base.

This package contains the standalone Typer-based CLI client for the companion `proxbox-api` backend.

## Files And Ownership

- [`__init__.py`](./__init__.py): Typer app entrypoint, root commands (`init`, `config`, `test`, `version`, `info`, `cache`, `clear-cache`, `full-update`), and sub-app wiring.
- [`__main__.py`](./__main__.py): module runner so `python -m proxbox_cli` executes `main()`.
- [`client.py`](./client.py): async `aiohttp` API client (`ProxboxApiClient`) and `ApiResponse` wrapper, including authenticated headers, bounded response streaming, and redirect refusal.
- [`config.py`](./config.py): validated CLI config model and persistence (`~/.config/proxbox-cli/config.json` or `$XDG_CONFIG_HOME/proxbox-cli/config.json`) with environment-over-file precedence.
- [`errors.py`](./errors.py): typed configuration and transport-policy failures with stable exit statuses.
- [`runtime.py`](./runtime.py): cached config loader and client factory helpers.
- [`support/`](./support/): package providing async bridge, output formatting (human/JSON/YAML), table rendering, and CLI error helpers. Key modules:
  - `async_bridge.py`: event-loop bridge for running async code from sync Typer callbacks
  - `console.py`: Rich console instance and shared print helpers
  - `output.py`: human/JSON/YAML output formatting
  - `tables.py`: Rich table rendering for list responses
- [`commands/`](./commands): grouped command modules for backend resources:
  - `netbox.py` (`pxb netbox ...`)
  - `proxmox.py` (`pxb proxmox ...`)
  - `proxmox_cluster.py` (`pxb proxmox cluster ...`)
  - `proxmox_endpoints.py` (`pxb proxmox endpoints ...`)
  - `proxmox_nodes.py` (`pxb proxmox nodes ...`)
  - `proxbox.py` (`pxb proxbox ...`)
  - `dcim.py` (`pxb dcim ...`)
  - `virtualization.py` (`pxb virtualization ...`)
  - `extras.py` (`pxb extras ...`)
- [`docgen/`](./docgen): command-capture engine and command catalog builders for MkDocs artifacts.
- [`docgen_capture.py`](./docgen_capture.py): façade utilities to generate CLI capture snapshots and raw JSON artifacts (`pxb docs generate-capture`).
- [`README.md`](./README.md): user-facing install, configuration, and command reference documentation.

## Dependencies

- Inbound: installed as the `pxb` console script (`pyproject.toml` → `project.scripts`).
- Outbound: `aiohttp`, `typer`, `click`, `rich`, `PyYAML`, `pydantic`, and the external `proxbox-api` service.

## Notes

- The CLI is optional (`netbox-proxbox[cli]`) and can run independently from the NetBox plugin runtime.
- Root command `pxb docs generate-capture` updates generated docs artifacts under `docs/generated/proxbox-cli/`.
- Global output flags `--json` and `--yaml` are mutually exclusive and enforced by shared helpers in `support/output.py`.
- Backend authentication comes only from `PROXBOX_API_KEY` or config field `api_key`; do not add an API-key CLI flag or print the secret. Treat the backend origin and API key as one credential bundle: a `PROXBOX_URL` origin change must not reuse the file key without `PROXBOX_API_KEY`. `pxb init` reads the file separately and never persists the environment key; it preserves the stored key for the same normalized origin and requires explicit `--keep-api-key` to retain it across an origin change.
- A configured API key requires HTTPS for non-loopback hosts. `PROXBOX_CLI_ALLOW_INSECURE_TRANSPORT=1` is the explicit cleartext opt-in and must print a warning to standard error. Every response body and HTTP exception must redact exact occurrences of the configured key before any human, JSON, or YAML rendering.
- `PROXBOX_CLI_TIMEOUT`/`timeout` must be finite, greater than zero, and no more than 600 seconds. `PROXBOX_CLI_MAX_RESPONSE_BYTES`/`max_response_bytes` defaults to 8 MiB and is enforced while streaming.
- Every request sends `Accept: application/json`, adds `X-Proxbox-API-Key` when configured, and sets `allow_redirects=False`. Redirect errors identify only the configured host.
- Backend HTTP commands exit `0` on success, `1` after rendering a `4xx`/`5xx` response or transport-policy failure, `2` for invalid configuration or a missing required key, and `130` for keyboard interruption. `pxb sync run` retains its documented subprocess-status contract.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
