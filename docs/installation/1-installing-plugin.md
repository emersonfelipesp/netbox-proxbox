# Installing the Plugin Using PyPI

## Read This First

The current repository code targets NetBox `4.5.8`, `4.5.9`, and `4.6.x`
(validated against `v4.5.8`, `v4.5.9`, and `v4.6.0` through `v4.6.4`).

If you need the code documented in this repository, use [Installing the Plugin Using Git](./2-installing-plugin-git.md) instead.

Use the PyPI package path only if you intentionally want the currently published package and have verified its compatibility separately.

## Generic Package Install Flow

```bash
source /opt/netbox/venv/bin/activate
pip install netbox-proxbox

cd /opt/netbox/netbox
python3 manage.py migrate netbox_proxbox
python3 manage.py collectstatic --no-input
sudo systemctl restart netbox
```

Enable the plugin in `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = ["netbox_proxbox"]
```

## Recommendation

For NetBox `4.5.8+`, prefer the Git/source installation path documented in this repository.

## Next Step

The plugin still requires the separate backend service. Continue with [Backend Setup](./backend-setup.md).
