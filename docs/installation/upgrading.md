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

- Proxbox `0.0.14` is the current release for NetBox `4.5.8`, `4.5.9`, and `4.6.x` (certified simultaneously against `v4.5.8`, `v4.5.9`, and official `v4.6.0`; declared compatibility range `4.5.8` through `4.6.99`). It is certified with the separate `proxbox-api` backend release `0.0.10.post2`, a contract-stable certification bump over backend `0.0.9.post2` (no plugin code changes; REST/SSE/WebSocket/auth/overwrite-flag contracts remain compatible). `proxbox-api` is not installed as a plugin dependency. The previous `0.0.13.post4` release pairs with backend `0.0.9.post2`.
- Recent releases moved sync execution to NetBox Jobs and the default RQ queue, so keep a standard NetBox RQ worker running after upgrade.
- Review the release notes before jumping from older `0.0.7` or early `0.0.9` installs; the `0.0.14` line continues the NetBox `4.5.8` / `4.5.9` / `4.6` compatibility path established in `0.0.13.post4`.
- If you run `proxbox-api >= 0.0.10` behind a reverse proxy and want per-client rate-limiting and brute-force lockout to track real client IPs, set `PROXBOX_TRUSTED_PROXIES` (CIDR list) on the backend container. Without it, `X-Forwarded-For` is ignored and limits apply to the proxy's IP. This is a backend-side configuration; the plugin itself does not care.
- Upgrading from a pre-`0.0.13` install introduces 16 new per-endpoint `overwrite_*` columns on `ProxmoxEndpoint`. The migration shipped in `0.0.13`; no new migrations are introduced in `0.0.14`.

## Backend Upgrade

Upgrade the separate `proxbox-api` service independently of the plugin:

```bash
source /opt/proxbox-api/venv/bin/activate
pip install -U proxbox-api
sudo systemctl restart proxbox
```

If you run the backend in Docker, pull the new image tag and recreate the container.
