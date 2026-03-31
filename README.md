# Proxbox

Proxbox is a NetBox plugin that synchronizes Proxmox infrastructure data into NetBox. It keeps your DCIM up-to-date with real Proxmox clusters, nodes, virtual machines, containers, and backups.

## What It Does

Proxbox discovers and syncs the following from Proxmox into NetBox:

- **Clusters and Nodes** — Proxmox cluster and node information
- **Virtual Machines** — VM status, resources, and configuration
- **Containers (LXC)** — Container details and settings
- **VM Snapshots** — Point-in-time snapshots for recovery
- **VM Backups** — Backup jobs and restore points
- **Storage** — Datastores and storage content
- **Networking** — VLANs, bridges, and IP assignments

Sync runs on-demand from the NetBox UI or scheduled automatically via NetBox's job system.

## Requirements

- NetBox 4.5.x
- Python 3.12+
- Proxmox VE 7.x or 8.x
- Proxbox API backend (see below)

## Quick Start

1. **Install the plugin** into your NetBox virtual environment:

   ```bash
   cd /opt/netbox/netbox
   git clone https://github.com/netdevopsbr/netbox-proxbox.git
   source /opt/netbox/venv/bin/activate
   pip install -e ./netbox-proxbox
   ```

2. **Enable the plugin** in `netbox/netbox/configuration.py`:

   ```python
   PLUGINS = ["netbox_proxbox"]
   ```

3. **Run migrations and collect static files:**

   ```bash
   python3 manage.py migrate netbox_proxbox
   python3 manage.py collectstatic --no-input
   sudo systemctl restart netbox
   ```

4. **Install the Proxbox API backend:**

   ```bash
   mkdir -p /opt/proxbox-api
   cd /opt/proxbox-api
   python3 -m venv venv
   source venv/bin/activate
   pip install proxbox-api
   uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800
   ```

   Or use Docker (the published image runs **nginx** on port **8000** inside the container, in front of **uvicorn**):

   ```bash
   docker run -d --name proxbox-api -p 8800:8000 emersonfelipesp/proxbox-api:latest
   ```

   **HTTPS with mkcert (optional):** the backend also publishes **`emersonfelipesp/proxbox-api:latest-mkcert`** (and `:<version>-mkcert`). **nginx** terminates **TLS** there (mkcert certs) on **`PORT`** (default **8000**); add more certificate names or IPs with **`MKCERT_EXTRA_NAMES`** (comma- or space-separated). Example:

   ```bash
   docker run -d --name proxbox-api-tls \
     -p 8800:8000 \
     -e MKCERT_EXTRA_NAMES='proxbox.backend.local' \
     emersonfelipesp/proxbox-api:latest-mkcert
   ```

   Point your NetBox **ProxBox API** endpoint at `https://<host>:8800` (or your mapped port). Trust the mkcert root on clients if needed; see the [proxbox-api README](https://github.com/emersonfelipesp/proxbox-api/blob/main/README.md) for build flags, `CAROOT`, and details.

5. **Configure endpoints in NetBox:**

   - Go to **Plugins > Proxbox**
   - Create a **Proxmox API** endpoint (your Proxmox host URL and token)
   - Create a **NetBox API** endpoint (your NetBox URL and token)
   - Create a **ProxBox API** endpoint (the backend from step 4)

6. **Run your first sync:**

   Click **Full Update** on the Proxbox home page. Progress appears in real-time.

## Scheduled Sync

To run sync automatically on a schedule:

1. Start the NetBox RQ worker with the Proxbox queue:

   ```bash
   cd /opt/netbox/netbox
   source /opt/netbox/venv/bin/activate
   python3 manage.py rqworker
   ```

2. In NetBox, go to **Proxbox > Schedule Sync** and configure your schedule.

## Documentation

Full documentation is available at [proxbox.readthedocs.io](https://proxbox.readthedocs.io/).

Key pages:

- [Installation Guide](https://proxbox.readthedocs.io/en/latest/installation/2-installing-plugin-git.html)
- [Backend Setup](https://proxbox.readthedocs.io/en/latest/installation/backend-setup.html)
- [Scheduled Sync](https://proxbox.readthedocs.io/en/latest/features/scheduled-sync.html)

## Community

- GitHub Discussions: https://github.com/orgs/netdevopsbr/discussions
- Discord: https://discord.gg/X6FudvXW
- Telegram: https://t.me/netboxbr

## Contributing

See [DEVELOP.md](./DEVELOP.md) for development setup and contribution guidelines.

## Support the Project

If Proxbox has been useful for you, consider supporting the project on GitHub Sponsors:

[Sponsor Me!](https://github.com/sponsors/emersonfelipesp)
