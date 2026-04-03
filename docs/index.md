# Proxbox

Proxbox is a NetBox plugin that integrates Proxmox with NetBox through a separate FastAPI backend.

## Compatibility

The current repository code declares support for:

- NetBox `4.5.x`
- Plugin version `0.0.10` in source

That support comes directly from the plugin config in this repository:

- `min_version = "4.5.0"`
- `max_version = "4.5.99"`

## Important Packaging Note

The repository is ahead of the latest published PyPI release of `netbox-proxbox`.

- Use the Git/source installation path if you want the code documented here.
- Do not assume older prerelease installation instructions apply to the current branch.

## What The Plugin Contains

The current codebase includes NetBox models for:

- Proxmox endpoints
- NetBox endpoints
- FastAPI endpoints
- Sync processes
- VM backups
- VM snapshots
- Proxmox clusters and hypervisor nodes (with links to NetBox Cluster and Device objects)
- Backup routines (Proxmox vzdump schedules with retention policies)
- Replications (Proxmox storage replication metadata)

The plugin UI exposes sync actions for:

- devices
- virtual machines
- containers
- full update
- VM backups
- VM snapshots
- Backup routines
- Replications

The plugin also provides a Backend Logs page for real-time log viewing from the proxbox-api backend.

## Architecture

Proxbox is split into two services:

1. The NetBox plugin from this repository.
2. A separate FastAPI backend service, `proxbox-api`.

The NetBox plugin stores endpoint configuration and triggers sync requests. The backend talks to Proxmox and NetBox over HTTP and streams real-time progress updates via SSE (Server-Sent Events). Legacy WebSocket streaming is also supported.

## Recommended Install Path

For the current repository state, the recommended path is:

1. Install the plugin from Git/source into the NetBox virtual environment.
2. Run migrations and collect static assets.
3. Install and run `proxbox-api`.
4. Configure `Proxmox API`, `NetBox API`, and `ProxBox API (FastAPI)` objects in the NetBox UI.
5. Run `Full Update` from `Plugins > Proxbox`.

See:

- [Installation Overview](./installation/index.md)
- [Pre-Installation](./installation/pre-installation.md)
- [Installing the Plugin Using Git](./installation/2-installing-plugin-git.md)
- [Installing the Plugin in Docker-Based NetBox Deployments](./installation/3-installing-plugin-docker.md)
- [Backend Setup](./installation/backend-setup.md)
- [Proxbox CLI Overview](./cli/index.md)

## Read-Only Proxmox Behavior

Proxbox currently focuses on synchronization and discovery. The plugin does not directly manage Proxmox resources from NetBox.

## Documentation Notes

- The published docs site is generated with MkDocs and uses site-relative URLs such as `/installation/2-installing-plugin-git/`.
- Generated CLI reference pages are rebuilt from the current `proxbox_cli` command tree.
- Historical pages that describe older workflows are retained only when clearly labeled as legacy.

## Stars History

[![Star History Chart](https://api.star-history.com/svg?repos=emersonfelipesp/netbox-proxbox&type=Timeline)](https://star-history.com/#emersonfelipesp/netbox-proxbox&Timeline)
