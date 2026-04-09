# `proxbox_cli`

This package contains the standalone Typer-based CLI client for the companion `proxbox-api` backend.

## Files And Ownership

- [`__init__.py`](./__init__.py): Typer app entrypoint, root commands (`init`, `config`, `test`, `version`, `info`, `cache`, `clear-cache`, `full-update`), and sub-app wiring.
- [`__main__.py`](./__main__.py): module runner so `python -m proxbox_cli` executes `main()`.
- [`client.py`](./client.py): async `aiohttp` API client (`ProxboxApiClient`) and `ApiResponse` wrapper.
- [`config.py`](./config.py): CLI config model and persistence (`~/.config/proxbox-cli/config.json` or `$XDG_CONFIG_HOME/proxbox-cli/config.json`) with `PROXBOX_URL` override support.
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

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
