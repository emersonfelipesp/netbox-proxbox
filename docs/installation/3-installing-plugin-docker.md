# Installing the Plugin in Docker-Based NetBox Deployments

This is the recommended path when NetBox is deployed with Docker (for example `netbox-community/netbox-docker`).

## NetBox Docker Plugin Files

In the NetBox Docker project root, you usually manage plugin installs with:

- `plugin_requirements.txt`
- `configuration/plugins.py`

This keeps plugin dependencies baked into the NetBox image and reproducible across restarts.

## Option 1: Install from PyPI

Add this to `plugin_requirements.txt`:

```txt
netbox-proxbox
```

Enable the plugin in `configuration/plugins.py`:

```python
PLUGINS = ["netbox_proxbox"]
```

Rebuild and start:

```bash
docker compose build
docker compose up -d
```

Run migrations:

```bash
docker compose exec netbox /opt/netbox/netbox/manage.py migrate
```

## Option 2: Install from Git/Source

If you need the repository head instead of the latest published package, add this to `plugin_requirements.txt`:

```txt
netbox-proxbox @ git+https://github.com/netdevopsbr/netbox-proxbox.git
```

Then use the same `configuration/plugins.py`, build, startup, and migration steps from Option 1.

## Verify the Plugin Is Loaded

After startup and migrations:

- Open NetBox and confirm `Plugins > Proxbox` appears in navigation.
- Run:

```bash
docker compose exec netbox /opt/netbox/netbox/manage.py showmigrations netbox_proxbox
```

All plugin migrations should be marked as applied.

## Next Step

The plugin requires the separate FastAPI backend service. Continue with [Proxbox Backend Setup](./backend-setup.md).
