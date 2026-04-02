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

- Proxbox `0.0.10` targets NetBox `4.5.x`.
- Recent releases moved sync execution to NetBox Jobs and the default RQ queue, so keep a standard NetBox RQ worker running after upgrade.
- Review the release notes before jumping from older `0.0.7` or early `0.0.9` installs; the `0.0.10` line continues the same NetBox `4.5.x` compatibility range.

## Backend Upgrade

Upgrade the separate `proxbox-api` service independently of the plugin:

```bash
source /opt/proxbox-api/venv/bin/activate
pip install -U proxbox-api
sudo systemctl restart proxbox
```

If you run the backend in Docker, pull the new image tag and recreate the container.
