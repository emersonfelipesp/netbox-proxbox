# Proxbox CLI

Command-line client for the `proxbox-api` FastAPI backend that powers the Proxbox NetBox plugin.

## Installation

### From the repository

```bash
pip install "netbox-proxbox[cli]"
```

### Verify

```bash
pxb --help
```

## Configuration

### First-time setup

Run the interactive initializer to configure the backend URL:

```bash
pxb init
```

You will be prompted for:

- **proxbox-api base URL** — e.g. `http://localhost:8000` for a local backend or `https://proxbox-api.example.com` for a remote backend
- **Request timeout** — a finite request timeout from more than `0` through `600` seconds (default: `30`)

The CLI stores its configuration in `~/.config/proxbox-cli/config.json` (or
`$XDG_CONFIG_HOME/proxbox-cli/config.json` when set). `pxb init` reads this
file without applying environment overrides and never copies
`PROXBOX_API_KEY` into the file. It preserves a stored API key when the
normalized backend origin remains the same. Changing the origin removes that
key unless the operator explicitly runs `pxb init --keep-api-key`.

Protected `proxbox-api` routes require an API key. Supply it through
`PROXBOX_API_KEY` or the config file's `api_key` field. The CLI deliberately
has no API-key command-line flag, so the secret does not enter command history
or process arguments. `pxb config` reports only whether a key is configured.
When a key is configured, remote backends require `https://`. Cleartext HTTP
remains available for explicit loopback hosts. For an exceptional trusted
network deployment, `PROXBOX_CLI_ALLOW_INSECURE_TRANSPORT=1` permits a remote
HTTP origin and prints a warning to standard error because the key crosses the
network without transport encryption.

```bash
export PROXBOX_API_KEY='<proxbox-api-key>'
pxb version
```

The config file also accepts `timeout` and `max_response_bytes`. Environment
variables take precedence over file values, which take precedence over the
built-in defaults. The backend origin and API key are treated as one credential
bundle: when `PROXBOX_URL` selects a different origin from the file's
`base_url`, the file's `api_key` is not sent. Supply `PROXBOX_API_KEY` for the
selected origin. Equivalent normalized origins, including an explicit default
port, may continue using the file key.

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PROXBOX_URL` | Backend base URL; a different origin does not inherit the config-file key | `http://localhost:8000` |
| `PROXBOX_API_KEY` | API key sent as `X-Proxbox-API-Key` (overrides config file) | unset |
| `PROXBOX_CLI_TIMEOUT` | Finite total HTTP timeout in seconds; must be `> 0` and `<= 600` | `30` |
| `PROXBOX_CLI_MAX_RESPONSE_BYTES` | Maximum decoded response body accepted while streaming; must be positive | `8388608` (8 MiB) |
| `PROXBOX_CLI_ALLOW_INSECURE_TRANSPORT` | Set to exactly `1` to permit a configured API key over non-loopback HTTP; emits a warning to standard error | unset |

### Show current configuration

```bash
pxb config
```

### Test connectivity

```bash
pxb test
```

## Command Reference

### Root-level commands

| Command | Description |
|---------|-------------|
| `pxb init` | Interactively configure the backend URL and timeout; use `--keep-api-key` to retain a stored key across an intentional origin change |
| `pxb config` | Display current configuration |
| `pxb test` | Test connectivity to the backend |
| `pxb version` | Show backend version |
| `pxb info` | Show backend project info |
| `pxb cache` | Show in-memory cache contents |
| `pxb clear-cache` | Clear the backend cache |
| `pxb full-update` | Run a full multi-stage sync (devices, storage, VMs, disks, backups, snapshots) |

### `pxb netbox` — Remote NetBox endpoints

Manage remote NetBox API endpoint records stored in the proxbox-api database.

```bash
# List all NetBox endpoint records
pxb netbox endpoint list

# Show a specific endpoint
pxb netbox endpoint get <id>

# Create an endpoint
pxb netbox endpoint create --body-json '{"url": "https://netbox.example.com", "token": "..."}'

# Update an endpoint
pxb netbox endpoint update <id> --body-json '{"token": "new-token"}'

# Delete an endpoint
pxb netbox endpoint delete <id> --confirm

# Check NetBox API status
pxb netbox status

# Fetch NetBox OpenAPI schema
pxb netbox openapi
```

### `pxb proxmox` — Proxmox integration

Inspect Proxmox sessions and manage local Proxmox endpoint records.

```bash
# Overview of all Proxmox sessions
pxb proxmox overview

# Active session details
pxb proxmox sessions

# Proxmox server version
pxb proxmox version

# Storage inventory across all sessions
pxb proxmox storage

# Storage content for a specific node and storage
pxb proxmox storage-content <node> <storage-id>
pxb proxmox storage-content pve01 local --vmid 100

# Query a raw Proxmox API path
pxb proxmox top-level access
pxb proxmox top-level cluster

# VM configuration
pxb proxmox vm-config <node> <type> <vmid>
pxb proxmox vm-config pve01 qemu 100

# Cluster status and resources
pxb proxmox cluster status
pxb proxmox cluster resources
pxb proxmox cluster resources --type vm

# Node information
pxb proxmox nodes list
pxb proxmox nodes network <node>
pxb proxmox nodes qemu <node>
pxb proxmox nodes lxc <node>

# Proxmox endpoint CRUD (local database)
pxb proxmox endpoints list
pxb proxmox endpoints get <id>
pxb proxmox endpoints create --body-json '{"host": "pve01.example.com", ...}'
pxb proxmox endpoints update <id> --body-json '{"host": "pve02.example.com"}'
pxb proxmox endpoints delete <id> --confirm

# Proxmox API viewer (OpenAPI/Pydantic codegen)
pxb proxmox viewer generate --body-json '{"parallel_workers": 4}'
pxb proxmox viewer openapi
pxb proxmox viewer openapi-embedded
pxb proxmox viewer contracts
pxb proxmox viewer pydantic
```

### `pxb dcim` — Device and interface sync

Sync Proxmox nodes into NetBox as DCIM devices and create their interfaces.

```bash
# List proxbox-tagged devices in NetBox
pxb dcim devices

# Sync all Proxmox nodes to NetBox devices
pxb dcim devices-create

# Create interfaces for a specific node device
pxb dcim interfaces-create <node>

# Create interfaces for all node devices
pxb dcim interfaces-create-all
```

### `pxb virtualization` — VM, storage, and backup sync

Sync virtual machines, storage, snapshots, and backups from Proxmox into NetBox.

```bash
# Cluster setup
pxb virtualization cluster-types-create   # stub (501) — use NetBox UI
pxb virtualization clusters-create        # stub (501) — use NetBox UI

# Storage sync
pxb virtualization storage-create

# Virtual machine operations
pxb virtualization vms list
pxb virtualization vms get <vm-id>
pxb virtualization vms create           # sync all VMs
pxb virtualization vms interfaces-create
pxb virtualization vms ip-address-create
pxb virtualization vms disks-create
pxb virtualization vms summary-example

# VM backups
pxb virtualization vms backups-create --node pve01 --storage local
pxb virtualization vms backups-sync-all
pxb virtualization vms backups-sync-all --delete-stale

# VM snapshots
pxb virtualization vms snapshots-create
pxb virtualization vms snapshots-create --vmid 100 --node pve01
pxb virtualization vms snapshots-sync-all
```

### `pxb extras` — NetBox custom fields

```bash
# Create predefined Proxbox custom fields in NetBox
pxb extras custom-fields-create
```

### `pxb proxbox` — Plugin configuration and backend info

Read plugin configuration from the NetBox side and backend info.

```bash
# Show resolved plugin configuration from NetBox
pxb proxbox settings

# Show full PLUGINS_CONFIG (all plugins)
pxb proxbox plugins-config --all

# Show Proxbox default settings
pxb proxbox default-settings
```

### `pxb docs` — Documentation generation

```bash
# Generate CLI docs artifacts (run from repository root)
pxb docs generate-capture
```

## Output formats

All data-fetching commands support `--json` and `--yaml` to override the default human-readable table output:

```bash
pxb virtualization vms list --json
pxb proxmox cluster status --yaml
pxb cache --json
```

These flags are mutually exclusive — using both produces an error.

## Exit codes and HTTP limits

Backend HTTP commands use these stable process exit codes:

| Exit code | Meaning |
|-----------|---------|
| `0` | The command completed successfully. |
| `1` | The backend returned a `4xx`/`5xx` response, or an HTTP transport-policy failure occurred. The backend detail is rendered first; `--json` retains the JSON body. |
| `2` | CLI configuration is invalid or a protected backend requires the missing `PROXBOX_API_KEY`. Click also uses `2` for command-line usage errors. |
| `130` | The command was interrupted from the keyboard. |

The client never follows backend redirects. A `3xx` response fails with exit
code `1`, and the error names only the configured backend host, not the
untrusted redirect target. Response bodies are streamed into the configured
`max_response_bytes` limit and rejected as soon as they exceed it.
Before rendering any response body or HTTP exception in human, JSON, or YAML
form, the CLI replaces every exact occurrence of the configured API key with
`[REDACTED]`. This applies to standard output and standard error.

`pxb sync run` is the separate local management-command wrapper. It continues
to return the wrapped `proxbox_sync` process status as documented by
`pxb sync run --help`.

## Environment

The CLI requires network access to the configured `proxbox-api` host and port. It also needs the remote NetBox instance to be reachable from the `proxbox-api` service (the backend proxies to NetBox during sync operations).

Default backend URL is `http://localhost:8000`. Set `PROXBOX_URL` to override:

```bash
export PROXBOX_URL=https://proxbox-api.example.com
export PROXBOX_API_KEY='<proxbox-api-key>'
pxb test
```

## Troubleshooting

### Connection refused

```
Connection failed (HTTP 503)
```

- Verify `proxbox-api` is running: `pxb test`
- Check the configured URL: `pxb config`
- Re-run init if needed: `pxb init`

### HTTP 401 / 403 on sync commands

If the CLI reports that `proxbox-api` requires authentication, set
`PROXBOX_API_KEY` or add `api_key` to the protected config file. An invalid key
remains an ordinary backend `401` and exits `1` after rendering the backend
detail.

Sync commands also require valid NetBox and Proxmox endpoint records in the backend database. Ensure endpoints are created:

```bash
pxb netbox endpoint list
pxb proxmox endpoints list
```

### 501 Not Implemented on cluster-types-create / clusters-create

These are stubs in the backend. Use the NetBox UI or REST API to manage cluster types and clusters directly.

### Long-running sync commands

`full-update`, `backups-sync-all`, and `snapshots-sync-all` are long-running operations that pull data from Proxmox and write to NetBox. Increase the CLI timeout if needed:

```bash
pxb init
# set timeout to 120 or higher, up to 600
```

The backend also has its own streaming endpoints (`/full-update/stream`, etc.) which the CLI calls as regular `GET` requests. For very large environments, consider running sync through the NetBox plugin UI instead, which uses background jobs with longer timeouts.

### Empty results on list commands

List commands return data from the backend database, not directly from Proxmox. Ensure endpoints are configured and sync has run at least once before listing.

## Regenerating documentation

The CLI reference pages are machine-generated. After changing commands, regenerate:

```bash
# From the repository root
python docs/generate_proxbox_cli_docs.py
```

Or through the CLI itself:

```bash
pxb docs generate-capture
```

Then rebuild the MkDocs site to publish updated reference pages.

## Architecture note

The CLI talks directly to the `proxbox-api` FastAPI backend over HTTP. It does **not** communicate with the NetBox plugin directly. Sync operations triggered by the CLI create objects in NetBox through the backend, exactly as the NetBox plugin UI does.

The CLI does not replace the NetBox plugin — it provides a terminal interface for the same backend operations. For scheduled or background sync, use the NetBox plugin UI and job system.
