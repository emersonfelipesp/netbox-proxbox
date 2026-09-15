# Proxbox CLI

`proxbox_cli` is the command-line client for the `proxbox-api` backend that powers the Proxbox NetBox plugin workflows.

It is a Typer application with top-level operational commands plus grouped command trees for:

- `sync` — operator-friendly trigger for a full Proxmox→NetBox sync job via the `proxbox_sync` Django management command
- `netbox` — remote NetBox endpoint management
- `proxmox` — Proxmox session inspection, cluster/node queries, and Proxmox endpoint CRUD
- `proxbox` — plugin configuration and backend info
- `dcim` — device and interface sync from Proxmox nodes to NetBox
- `virtualization` — VM, storage, snapshot, and backup sync operations
- `extras` — custom fields initialization in NetBox
- `docs` — documentation generation utilities

## Installation

Install the CLI dependencies from this repository checkout:

```bash
pip install "netbox-proxbox[cli]"
```

After installation, the console entrypoint is:

```bash
pxb --help
```

## Configuration

Initialize the CLI once so it knows where `proxbox-api` is running:

```bash
pxb init
pxb config
pxb test
```

The CLI stores its config under `~/.config/proxbox-cli/config.json` unless
`XDG_CONFIG_HOME` overrides that path. `pxb init` reads only the on-disk file
and never persists a key supplied through `PROXBOX_API_KEY`. It preserves a
stored key when the normalized backend origin remains the same. Changing the
origin removes the stored key unless the operator explicitly runs
`pxb init --keep-api-key`.

Protected backend routes require an API key. Set `PROXBOX_API_KEY`, or put an
`api_key` field in the config file and restrict that file to the operator. The
CLI has no API-key command-line flag and `pxb config` never prints the key.
Any keyed remote backend must use `https://`. Explicit loopback hosts may use
HTTP. `PROXBOX_CLI_ALLOW_INSECURE_TRANSPORT=1` is an exceptional opt-in for a
keyed remote HTTP origin and prints a cleartext-credential warning to standard
error.

```bash
export PROXBOX_URL=https://proxbox-api.example.com
export PROXBOX_API_KEY='<proxbox-api-key>'
pxb version
```

Configuration resolves in this order: environment variable, config file, then
built-in default. The backend origin and API key are one credential bundle. If
`PROXBOX_URL` selects a different origin from the config file,
the stored `api_key` is not sent to that origin; supply `PROXBOX_API_KEY` for
the selected origin instead. Equivalent normalized origins, including an
explicit default port, may continue using the stored key.

| Environment variable | Config field | Default | Validation |
|----------------------|--------------|---------|------------|
| `PROXBOX_URL` | `base_url` | `http://localhost:8000` | An `http://` or `https://` origin without credentials, a path, query, or fragment. A different origin does not inherit the file key. |
| `PROXBOX_API_KEY` | `api_key` | unset | A nonempty value when the selected backend route requires authentication. |
| `PROXBOX_CLI_TIMEOUT` | `timeout` | `30` seconds | Finite, greater than `0`, and no more than `600`. |
| `PROXBOX_CLI_MAX_RESPONSE_BYTES` | `max_response_bytes` | `8388608` bytes (8 MiB) | A positive byte count. |
| `PROXBOX_CLI_ALLOW_INSECURE_TRANSPORT` | n/a | unset | Set to exactly `1` to permit a configured API key over non-loopback HTTP; emits a warning to standard error. |

The response limit is enforced incrementally while reading the decoded body.
The client also disables redirects for every method. A redirect error includes
only the configured backend host and does not expose or follow `Location`.
Every exact occurrence of the configured API key is replaced with
`[REDACTED]` before a response body or HTTP exception is rendered to standard
output or standard error, including JSON, YAML, and human-readable output.

## Quick Reference

### Sync commands

The `pxb sync` group wraps the `proxbox_sync` Django management command as a subprocess. See [Sync Command](sync.md) for full documentation.

| Command | Description |
|---------|-------------|
| `pxb sync run` | Enqueue a full Proxmox→NetBox sync job and exit |
| `pxb sync run --wait` | Block until the job reaches a terminal state |
| `pxb sync run --wait --timeout 600` | Wait up to 600 s for completion |
| `pxb sync run --json` | Emit a single JSON document at exit (CI-friendly) |
| `pxb sync run --netbox-path PATH` | Override the `manage.py` resolution chain |

### Root-level commands

| Command | Description |
|---------|-------------|
| `pxb init` | Interactively configure the backend URL and timeout; use `--keep-api-key` to retain a stored key across an intentional origin change |
| `pxb config` | Show the current CLI configuration |
| `pxb test` | Test connectivity to the backend |
| `pxb version` | Show the backend version |
| `pxb info` | Show backend project info |
| `pxb cache` | Show in-memory cache contents |
| `pxb clear-cache` | Clear the backend cache |
| `pxb full-update` | Run a full multi-stage sync |

### Endpoint management

```bash
# NetBox remote endpoints
pxb netbox endpoint list|get|create|update|delete

# Proxmox endpoint records (local DB)
pxb proxmox endpoints list|get|create|update|delete

# Backend plugin settings
pxb proxbox settings
pxb proxbox plugins-config
pxb proxbox default-settings
```

### Sync operations

```bash
# Device and interface sync
pxb dcim devices
pxb dcim devices-create
pxb dcim interfaces-create <node>
pxb dcim interfaces-create-all

# Virtual machine sync
pxb virtualization vms list
pxb virtualization vms create
pxb virtualization vms interfaces-create
pxb virtualization vms disks-create
pxb virtualization vms backups-sync-all
pxb virtualization vms snapshots-sync-all

# Storage sync
pxb virtualization storage-create

# Cluster and node inspection
pxb proxmox cluster status
pxb proxmox cluster resources
pxb proxmox nodes list
pxb proxmox nodes network <node>
pxb proxmox nodes qemu <node>
pxb proxmox nodes lxc <node>
```

## Output Formats

All commands that fetch data support `--json` and `--yaml` output flags:

```bash
pxb virtualization vms list --json
pxb proxmox cluster status --yaml
```

For backend HTTP commands, success exits `0`. A backend `4xx` or `5xx` response
is rendered and exits `1`; JSON output retains the response body. A missing API
key detected from a protected backend, an invalid URL, or an invalid HTTP limit
exits `2`. Keyboard interruption exits `130`. Click command-line usage errors
also use `2`.

`pxb sync run` is a local management-command wrapper rather than an HTTP
command and returns the wrapped process status described on the
[Sync Command](sync.md) page.

## Generated Reference

The MkDocs site includes two machine-generated CLI sections:

- [Command Reference](../reference/proxbox-cli/command-catalog/index.md) lists every discovered command and an autogenerated example invocation.
- [Command Examples](../reference/proxbox-cli/command-examples/index.md) captures representative help output for major command groups and leaf commands.

## Regeneration

To refresh the generated CLI docs from the current checkout:

```bash
python docs/generate_proxbox_cli_docs.py
```

The CLI exposes the same generator directly:

```bash
pxb docs generate-capture
```
