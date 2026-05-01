# Upgrading Proxbox

## Plugin Upgrade Checklist

Use this flow when upgrading an existing Proxbox installation in NetBox:

```bash
cd /opt/netbox/netbox
source /opt/netbox/venv/bin/activate
pip install -U netbox-proxbox
python3 manage.py migrate netbox_proxbox
python3 manage.py collectstatic --no-input
sudo systemctl restart netbox
```

If you install from a Git checkout instead of PyPI, replace the install step with:

```bash
pip install -e /opt/netbox/netbox/netbox-proxbox
```

## Important Notes

- Proxbox `0.0.13.post4` is the current release for NetBox `4.6.x` (certified against `v4.6.0-beta2`). It pairs with `proxbox-api==0.0.9.post2`, which fixes a `create_storages()` `TypeError` that affected `0.0.9.post1`. If you are still on NetBox `4.5.x`, stay on `0.0.11`.
- Recent releases moved sync execution to NetBox Jobs and the default RQ queue, so keep a standard NetBox RQ worker running after upgrade.
- Review the release notes before jumping from older `0.0.7` or early `0.0.9` installs; the `0.0.11` line continues the NetBox `4.5.x` compatibility range while `0.0.12` and later require NetBox `4.6.0` or later.
- Upgrading to `0.0.13` introduces 16 new per-endpoint `overwrite_*` columns on `ProxmoxEndpoint`. The migration ships in this release; no manual schema work is required, but plan for the migration to run during the upgrade window.

## Backend Upgrade

Upgrade the separate `proxbox-api` service independently of the plugin:

```bash
source /opt/proxbox-api/venv/bin/activate
pip install -U proxbox-api
sudo systemctl restart proxbox
```

If you run the backend in Docker, pull the new image tag and recreate the container.
