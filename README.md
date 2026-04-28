# Proxbox

Proxbox is a NetBox plugin that synchronizes Proxmox infrastructure data into NetBox. It keeps your DCIM up-to-date with real Proxmox clusters, nodes, virtual machines, containers, and backups.

## What It Does

Proxbox discovers and syncs the following from Proxmox into NetBox:

- **Clusters and Nodes** — Proxmox cluster name, mode (cluster/standalone), quorum status, node count, and Proxmox VE version. Each node includes online status, IP address, CPU usage, memory usage, and uptime at sync time. Optionally link to NetBox Cluster and Device objects.
- **Virtual Machines** — VM status, resources, and configuration
- **Containers (LXC)** — Container details and settings
- **VM Snapshots** — Point-in-time snapshots for recovery
- **VM Backups** — Backup jobs and restore points
- **Storage** — Datastores and storage content
- **Network Interfaces and IPs** — Network interfaces and IP addresses assigned to VMs and containers
- **Backup Routines** — Backup job definitions from Proxmox
- **Replications** — Replication job status and configuration

> **Note:** All metrics (CPU, memory, uptime, etc.) are captured as point-in-time snapshots at sync time, not continuous monitoring.

Sync runs on-demand from the NetBox UI or scheduled automatically via NetBox's job system.

## Compatibility Matrix

| NetBox   | netbox-proxbox | proxbox-api | netbox-sdk     | proxmox-sdk    |
|----------|----------------|-------------|----------------|----------------|
| >=4.6.0-beta2  | v0.0.13.post1        | v0.0.9           | v0.0.7.post6   | v0.0.3.post1   |
| >=4.6.0-beta1  | v0.0.12        | v0.0.8.post1      | v0.0.7.post6   | v0.0.3.post1   |
| >=4.5.7  | v0.0.11        | v0.0.7      | v0.0.7.post4   | v0.0.2.post2   |

## Requirements

- NetBox 4.6.x
- Verified with NetBox v4.6.0-beta2
- Python 3.12+
- Proxmox VE 7.x or 8.x
- Proxbox API backend (see below)

## Quick Start

Choose the installation path that matches your NetBox deployment:

- **Standard NetBox install (venv on host):** follow steps below.
- **NetBox Docker install (`netbox-docker`):** use the Docker-specific workflow in [Installing the Plugin in Docker-Based NetBox Deployments](./docs/installation/3-installing-plugin-docker.md).

1. **Install the plugin** into your NetBox virtual environment (host/venv deployment):

   ```bash
   cd /opt/netbox/netbox
   git clone https://github.com/emersonfelipesp/netbox-proxbox.git
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

## NetBox Docker Install Option

If your NetBox runs with `netbox-community/netbox-docker`, install the plugin through the Docker plugin files in your NetBox Docker project:

1. Add plugin requirements to `plugin_requirements.txt` (PyPI or Git):

   ```txt
   netbox-proxbox
   # or
   # netbox-proxbox @ git+https://github.com/emersonfelipesp/netbox-proxbox.git
   ```

2. Enable the plugin in `configuration/plugins.py`:

   ```python
   PLUGINS = ["netbox_proxbox"]
   ```

3. Rebuild and restart NetBox:

   ```bash
   docker compose build
   docker compose up -d
   ```

4. Run migrations in the NetBox container:

   ```bash
   docker compose exec netbox /opt/netbox/netbox/manage.py migrate
   ```

For complete Docker installation instructions, validation checks, and Git/source install examples, see [docs/installation/3-installing-plugin-docker.md](./docs/installation/3-installing-plugin-docker.md).

## Scheduled Sync

Proxbox sync jobs run on NetBox's **`default`** RQ queue. A standard NetBox installation already ships a `netbox-rq` systemd service that runs:

```
manage.py rqworker high default low
```

Check whether it is running before doing anything else:

```bash
sudo systemctl status netbox-rq
```

If it is **active (running)**, you have nothing extra to configure — Proxbox jobs will be picked up automatically.

If the service is **inactive or missing**, enable it:

```bash
sudo systemctl enable --now netbox-rq
```

The unit file is provided by NetBox at `contrib/netbox-rq.service` in the NetBox repository. If you need to create it manually, copy it from there and run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netbox-rq
```

> **Upgrading from an older Proxbox release?** Jobs used to be enqueued on the `netbox_proxbox.sync` queue. The stock `netbox-rq` service does not listen to that queue, so old-style jobs will not run. New jobs always use `default` and are picked up without any changes.

### Schedule a sync

1. In NetBox, go to **Proxbox > Schedule Sync**.
2. Choose one or more sync types (**All**, Devices, VMs, Storage, etc.).
3. Optionally set a **Schedule at** time and a **Recurs every** interval in minutes (e.g. `1440` for daily).
4. Click **Schedule**.

Track job status under **Proxbox > Sync Jobs** or **Operations > Background Jobs**.

### Job timeout

Proxbox sync jobs default to a **7200-second (2-hour) RQ wall-clock limit** (`PROXBOX_SYNC_JOB_TIMEOUT`). NetBox's default `RQ_DEFAULT_TIMEOUT` is only 300 s, which would kill long syncs. No configuration is needed unless your syncs routinely take longer than two hours; if they do, override the constant in `netbox_proxbox/jobs.py`.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Job stays **`pending`** | No RQ worker running, or worker not listening to `default` queue | Start/restart `manage.py rqworker` |
| Job stays **`running`** for a long time | Proxbox API is still syncing or stream is slow | Check the job **Log** tab; wait or inspect the backend |
| Job **`errored: JobTimeoutException`** | RQ wall-clock limit exceeded | Increase `PROXBOX_SYNC_JOB_TIMEOUT` in `netbox_proxbox/jobs.py` |

## Documentation

Full documentation is available at [emersonfelipesp.github.io/netbox-proxbox](https://emersonfelipesp.github.io/netbox-proxbox/).

Key pages:

- [Installation Guide](https://emersonfelipesp.github.io/netbox-proxbox/installation/2-installing-plugin-git/)
- [Backend Setup](https://emersonfelipesp.github.io/netbox-proxbox/installation/backend-setup/)
- [Scheduled Sync](https://emersonfelipesp.github.io/netbox-proxbox/features/scheduled-sync/)

## Community

- GitHub Discussions: https://github.com/orgs/emersonfelipesp/discussions
- Discord: https://discord.gg/X6FudvXW
- Telegram: https://t.me/netboxbr

## Contributing

See [DEVELOP.md](./DEVELOP.md) for development setup and contribution guidelines.

## Support the Project

If Proxbox has been useful for you, consider supporting the project on GitHub Sponsors:

[Sponsor Me!](https://github.com/sponsors/emersonfelipesp)
