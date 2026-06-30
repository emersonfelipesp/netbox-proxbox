# Installing the Plugin Using Git

This is the recommended installation path for the current repository state.

## Why This Is Recommended

The code in this repository is `0.0.22` and targets NetBox `4.5.8`,
`4.5.9`, and `4.6.x` (validated against `v4.5.8`, `v4.5.9`, `v4.6.0`, and
`v4.6.0` through `v4.6.4`). That is the version line reflected by the docs in this
repository.

Current pairing: `netbox-proxbox 0.0.22 ↔ proxbox-api 0.0.19 ↔ proxmox-sdk 0.0.12 ↔ netbox-sdk 0.0.10`.
SDN sync requires `proxbox-api >= 0.0.19`.

## Install

```bash
cd /opt/netbox/netbox
git clone https://github.com/emersonfelipesp/netbox-proxbox.git

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

- The plugin declares `min_version = "4.5.8"` and `max_version = "4.6.99"`.
- Proxbox uses NetBox's JobRunner queue APIs and runs on the default RQ queue (`RQ_QUEUE_DEFAULT`).
- The project requires Python `>=3.12`.
- `pip install -e` is useful while the repository is moving faster than packaged releases.

## Next Step

After the plugin is installed in NetBox, continue with [Backend Setup](./backend-setup.md).
