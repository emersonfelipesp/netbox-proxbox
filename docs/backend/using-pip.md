# Installing The Backend With pip

This is the simplest non-Docker path for the `proxbox-api` backend.

## Install

```bash
mkdir -p /opt/proxbox-api
cd /opt/proxbox-api
python3 -m venv venv
source venv/bin/activate
pip install --upgrade proxbox-api
```

## Start Manually

```bash
/opt/proxbox-api/venv/bin/uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800 --app-dir /opt/proxbox-api
```

Once started, the backend should answer on `http://<host>:8800`.

If you want to stay on repository head instead of the latest published package, use [Installing The Backend From Source](./using-git.md).

## Run With systemd

This repository includes a sample unit file at `contrib/proxbox.service`.

```bash
sudo cp -v /opt/netbox/netbox/netbox-proxbox/contrib/proxbox.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now proxbox
sudo systemctl status proxbox
```

## Next Step

After the backend is running, create the `ProxBox API (FastAPI)` endpoint object in NetBox and test a sync from the Proxbox home page.
