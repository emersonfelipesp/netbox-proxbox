# Proxbox

Proxbox is a NetBox plugin that integrates Proxmox with NetBox through a separate FastAPI backend.

The current repository code is `v0.0.7` and declares support for NetBox `4.5.x`:

- `min_version = "4.5.0"`
- `max_version = "4.5.99"`

The latest upstream NetBox release I verified for this docs refresh is `v4.5.5`, published on `2026-03-17`.

## Current Status

This repository is ahead of the latest published PyPI release of `netbox-proxbox`.

- If you want the code documented in this repository, install from source.
- If you install the older PyPI prerelease, its compatibility notes from the old docs do not apply to the current `main` branch anymore.

Proxbox remains read-oriented toward Proxmox. The plugin triggers synchronization through the backend and does not directly manage Proxmox resources from NetBox.

## Architecture

Proxbox has two parts:

1. The NetBox plugin in this repository.
2. A separate FastAPI backend service (`proxbox-api`) that talks to Proxmox and NetBox.

Inside NetBox, the plugin currently manages:

- `ProxmoxEndpoint`
- `NetBoxEndpoint`
- `FastAPIEndpoint`
- `SyncProcess`
- `VMBackup`

The UI exposes sync actions for:

- devices
- virtual machines
- full update
- VM backups

## Supported Workflow

For the current codebase, the recommended install path is:

1. Install the plugin from this repository into the NetBox virtual environment.
2. Run migrations and collect static files.
3. Install and start the `proxbox-api` backend separately.
4. In NetBox, create at least one endpoint object for:
   - Proxmox API
   - NetBox API
   - ProxBox API (FastAPI)
5. Run `Full Update` from the Proxbox home page.

## Install From Source

```bash
cd /opt/netbox/netbox
git clone https://github.com/netdevopsbr/netbox-proxbox.git

source /opt/netbox/venv/bin/activate
pip install -e /opt/netbox/netbox/netbox-proxbox

cd /opt/netbox/netbox
python3 manage.py migrate netbox_proxbox
python3 manage.py collectstatic --no-input
sudo systemctl restart netbox
```

Enable the plugin in `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = ["netbox_proxbox"]
```

## Backend Setup

The plugin requires a running `proxbox-api` service. The simplest backend install is a separate virtual environment:

```bash
mkdir -p /opt/proxbox-api
cd /opt/proxbox-api
python3 -m venv venv
source venv/bin/activate
pip install proxbox-api==0.0.2.post3

/opt/proxbox-api/venv/bin/uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800 --app-dir /opt/proxbox-api
```

Docker is also supported for the backend itself:

```bash
docker pull emersonfelipesp/proxbox-api:latest
docker run -d --name proxbox-api -p 8800:8800 emersonfelipesp/proxbox-api:latest
```

The repository also ships sample systemd units in [`contrib/proxbox.service`](./contrib/proxbox.service) and [`contrib/proxbox-https.service`](./contrib/proxbox-https.service).

## Initial Configuration

After both services are running, configure the plugin through the NetBox UI:

1. Open `Plugins > Proxbox`.
2. Create a `Proxmox API` endpoint.
3. Create a `NetBox API` endpoint.
4. Create a `ProxBox API (FastAPI)` endpoint.
5. Return to the Proxbox home page and run a sync.

If you enable WebSocket support on the FastAPI endpoint, the sync pages can display real-time messages from the backend.

## Notes

- The current code requires Python `>=3.12` for the plugin itself.
- HTMX navigation in NetBox can still affect the Proxbox UI; see the pre-installation note in the docs.
- Containerized NetBox/plugin installation is not documented as a supported workflow yet.

## Documentation

The MkDocs site lives under [`docs/`](./docs). The main entry points are:

- [`docs/index.md`](./docs/index.md)
- [`docs/installation/2-installing-plugin-git.md`](./docs/installation/2-installing-plugin-git.md)
- [`docs/installation/backend-setup.md`](./docs/installation/backend-setup.md)

## Community

- GitHub Discussions: <https://github.com/orgs/netdevopsbr/discussions>
- Discord: <https://discord.gg/X6FudvXW>
- Telegram: <https://t.me/netboxbr>
