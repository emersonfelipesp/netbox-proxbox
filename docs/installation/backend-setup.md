# Proxbox Backend Setup

The NetBox plugin requires a separate `proxbox-api` FastAPI service. The plugin stores configuration in NetBox, but sync requests are sent to this backend.

## Backend Role

The current plugin code expects a configured `FastAPIEndpoint` object and uses it for:

- device sync
- virtual machine sync
- full update
- VM backup sync

## Option 1: Install The Backend With pip

```bash
mkdir -p /opt/proxbox-api
cd /opt/proxbox-api
python3 -m venv venv
source venv/bin/activate
pip install --upgrade proxbox-api
```

Start it manually:

```bash
/opt/proxbox-api/venv/bin/uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800 --app-dir /opt/proxbox-api
```

## Option 2: Run The Backend In Docker

```bash
docker pull emersonfelipesp/proxbox-api:latest
docker run -d --name proxbox-api -p 8800:8000 emersonfelipesp/proxbox-api:latest
```

The image serves on container port `8000` (nginx), so keep `8800:8000` if you want the backend reachable as `http://<host>:8800`.

If you want NetBox to connect over HTTPS, use the TLS image instead:

```bash
docker pull emersonfelipesp/proxbox-api:latest-mkcert
docker run -d --name proxbox-api-tls \
  -p 8800:8000 \
  -e MKCERT_EXTRA_NAMES='proxbox.backend.local' \
  emersonfelipesp/proxbox-api:latest-mkcert
```

Then set the NetBox `FastAPIEndpoint` URL to `https://<host>:8800` and leave `verify_ssl` enabled. If NetBox or your workstation does not trust the mkcert root CA yet, install that root CA first so HTTPS verification succeeds.

## Option 3: Run It As A systemd Service

This repository includes sample service files:

- `contrib/proxbox.service`
- `contrib/proxbox-https.service`

Install one of them:

```bash
sudo cp -v /opt/netbox/netbox/netbox-proxbox/contrib/proxbox.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now proxbox
sudo systemctl status proxbox
```

The sample unit expects the backend virtual environment under `/opt/proxbox-api/venv` and starts:

```bash
/opt/proxbox-api/venv/bin/uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800 --app-dir /opt/proxbox-api
```

Adjust the service file if your backend lives somewhere else.

## Option 4: Run The Backend From Source

Use the source workflow when you want the latest backend code or need to patch the backend itself:

```bash
cd /opt
git clone https://github.com/emersonfelipesp/proxbox-api.git
cd /opt/proxbox-api

python3 -m venv venv
source venv/bin/activate
pip install -e .

/opt/proxbox-api/venv/bin/uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800 --app-dir /opt/proxbox-api
```

## TLS Notes

If you terminate TLS in front of `uvicorn` with nginx, keep the proxy streaming-friendly:

- `proxy_pass` to the local `uvicorn` process on `127.0.0.1:8000`
- set `proxy_http_version 1.1`
- forward `Host`, `X-Real-IP`, `X-Forwarded-For`, and `X-Forwarded-Proto`
- disable buffering with `proxy_buffering off`
- keep long read/send timeouts so SSE `/stream` responses are not cut off early

For a complete nginx example, see the backend repository README and the bundled nginx templates under `docker/nginx/`.

If you use the HTTPS sample unit and point it at NetBox-managed certificates, the backend process may need permission to read them:

```bash
sudo chmod +rx -R /etc/ssl/private/
sudo chmod +rx -R /etc/ssl/certs/
```

That is convenient, but you should review the security impact for your environment before using it.

## Authentication

The NetBox plugin and `proxbox-api` backend use database-backed API key authentication:

1. When you create a `FastAPIEndpoint` in NetBox, the plugin auto-generates a 64-character secure token
2. The plugin calls `/auth/bootstrap-status` to check if the backend needs initial setup
3. If bootstrap is needed, the plugin registers the token via `/auth/register-key`
4. All subsequent requests use the `X-Proxbox-API-Key` header with that token

### Manual Key Registration

If the plugin cannot register the key automatically (e.g., backend not running during setup), you can register keys manually:

```bash
# Check if bootstrap is needed
curl http://localhost:8800/auth/bootstrap-status

# Register a key (only works when no keys exist)
curl -X POST http://localhost:8800/auth/register-key \
  -H "Content-Type: application/json" \
  -d '{"api_key": "your-secure-api-key-at-least-32-characters", "label": "netbox-plugin"}'
```

Then set the `token` field on your `FastAPIEndpoint` in NetBox to match.

### Key Management

After the first key is registered, manage keys via the authenticated API:

```bash
# List keys (requires auth)
curl http://localhost:8800/auth/keys \
  -H "X-Proxbox-API-Key: your-key"

# Create a new key
curl -X POST http://localhost:8800/auth/keys \
  -H "X-Proxbox-API-Key: your-key"

# Delete a key
curl -X DELETE http://localhost:8800/auth/keys/1 \
  -H "X-Proxbox-API-Key: your-key"
```

## Next Step In NetBox

After the backend is reachable, create these objects in the Proxbox UI:

1. `Proxmox API`
2. `NetBox API`
3. `ProxBox API (FastAPI)`

Then return to `Plugins > Proxbox` and run `Full Update`.
