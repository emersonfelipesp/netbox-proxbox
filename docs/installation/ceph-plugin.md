# Installing the Ceph Plugin

`netbox-ceph` is a separate wheel shipped from the same repository as
`netbox-proxbox`. It depends on `netbox-proxbox` and must be enabled
**alongside** it, not instead of it.

## Prerequisites

- A working `netbox-proxbox` installation (see
  [Installing the Plugin (pip)](./1-installing-plugin.md) or
  [Installing the Plugin (git, recommended)](./2-installing-plugin-git.md)).
- A `proxbox-api` backend at `>= 0.0.11` reachable from NetBox and exposing
  the `/ceph/status` and `/ceph/sync/*` routes (these ship in the same
  backend release that provides `/intent/*` and `/ha/*`).
- NetBox `4.5.8`–`4.6.99`.

## Install the wheel

The `netbox-ceph` package lives in `netbox_ceph/` inside this repository.
From a Git clone:

```bash
source /opt/netbox/venv/bin/activate
cd /opt/netbox/netbox-proxbox/netbox_ceph
pip install .

cd /opt/netbox/netbox
python3 manage.py migrate netbox_ceph
python3 manage.py collectstatic --no-input
sudo systemctl restart netbox
```

Enable both plugins in `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = [
    "netbox_proxbox",
    "netbox_ceph",
]
```

`netbox_ceph` will refuse to load if `netbox_proxbox` is not enabled — it
declares `required_plugins = ["netbox_proxbox"]` in its `PluginConfig`.

## Verify

Open NetBox and navigate to **Plugins → Proxbox Ceph**. The home page
should list the configured Proxmox endpoints. Cluster, OSD, pool, daemon,
filesystem, CRUSH rule, flag, and health-check lists are read-only and
populated by the `CephSyncJob` background job (see
[Ceph (Proxmox-managed)](../features/ceph.md)).

A first sync can be triggered from the Plugins → Background Jobs page by
enqueuing a `Ceph Sync` job, or programmatically via:

```python
from netbox_ceph.jobs import CephSyncJob
CephSyncJob.enqueue(resources=["full"])
```

## Branching (optional)

If the `netbox-branching` plugin is installed, edit the **Ceph Plugin
Settings** singleton and enable `branching_enabled`. `CephSyncJob` will
then provision a branch (default prefix `ceph-sync`, default on-conflict
`fail`), thread the branch schema id through every `/ceph/sync/*` call, and
merge the branch back to `main` only on a clean run. Failures leave the
branch open for inspection.

## Uninstalling

```bash
source /opt/netbox/venv/bin/activate
pip uninstall netbox-ceph
```

Remove `"netbox_ceph"` from `PLUGINS` and restart NetBox. The migration is
forward-only; if you need to reclaim the schema, drop the `netbox_ceph_*`
tables manually.
