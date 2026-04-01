# Installing the Plugin Using Git

This is the recommended installation path for the current repository state.

## Why This Is Recommended

The code in this repository is `0.0.9.post4` and targets NetBox `4.5.x`. That is the version line reflected by the docs in this repository.

## Install

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

## Enable The Plugin

Add the plugin to `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = ["netbox_proxbox"]
```

## Notes

- The plugin declares `min_version = "4.5.0"` and `max_version = "4.5.99"`.
- The project requires Python `>=3.12`.
- `pip install -e` is useful while the repository is moving faster than packaged releases.

## Next Step

After the plugin is installed in NetBox, continue with [Backend Setup](./backend-setup.md).
