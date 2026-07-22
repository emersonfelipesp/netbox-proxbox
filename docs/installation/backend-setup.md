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

If you want NetBox to connect over HTTPS, use the TLS (`*-nginx`) image instead:

```bash
docker pull emersonfelipesp/proxbox-api:latest-nginx
docker run -d --name proxbox-api-tls \
  -p 8800:8000 \
  -e MKCERT_EXTRA_NAMES='proxbox.backend.local' \
  emersonfelipesp/proxbox-api:latest-nginx
```

When configuring the NetBox `FastAPIEndpoint` for an `*-nginx` (TLS-only) image,
set:

| Field | Value | Why |
|---|---|---|
| **Use HTTPS** | ✓ enabled | The image only listens on TLS; plain HTTP returns `400`. |
| **Verify SSL** | ✗ disabled (when using the bundled mkcert cert) | The cert is self-signed; verification will fail unless the mkcert root CA is trusted on the NetBox host. Tick **only** if you have installed the mkcert CA into NetBox's trust store. |
| **Port** | host port mapped to container `8000` | Typically `8800`. |

`Use HTTPS` and `Verify SSL` are independent toggles since v0.0.15 (issue #352).
Earlier releases coupled them, which made the `*-nginx` + self-signed-cert combo
unreachable from the UI.

### Custom certificates

If you supply your own CA-signed, Let's Encrypt, or corporate certificates,
the `*-nginx` and `*-granian` images detect them automatically and skip
mkcert generation. Mount the certificate directory read-only:

```bash
docker run -d --name proxbox-api-tls \
  -p 8800:8000 \
  -v /path/to/certs:/certs:ro \
  emersonfelipesp/proxbox-api:latest-nginx
```

The `/certs` directory must contain `cert.pem` and `key.pem`. If either file is
absent, mkcert auto-generation runs as normal.

When using a publicly trusted or internally-trusted certificate (not self-signed),
you can enable certificate verification on the FastAPIEndpoint:

| Field | Value |
|---|---|
| **Use HTTPS** | ✓ enabled |
| **Verify SSL** | ✓ enabled |
| **Port** | host port mapped to container `8000` |

For the granian image, see the full certificate handling notes in the
[proxbox-api installation docs](https://emersonfelipesp.github.io/proxbox-api/getting-started/installation/#mounting-custom-certificates).

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

### Fail-closed token setup

When an enabled `FastAPIEndpoint` is created, activated, moved to a different
backend URL/TLS target, or given a replacement token, the backend must be
reachable and the operator must explicitly submit a non-empty candidate. The
plugin never generates one implicitly. It then performs one of two mutually
exclusive flows:

1. **Uninitialized backend** (`needs_bootstrap=true`) — use the explicitly
   retained candidate and require one successful `POST /auth/register-key`
   (`201`).
2. **Initialized backend** — never call the bootstrap route. Authenticate the
   candidate with one read-only `GET /auth/keys` request and persist it only on
   `200`.

Authentication rejection, conflict, throttling, timeout, TLS failure, or a
connection error leaves the previous encrypted token unchanged. A disabled
endpoint never makes a connection and a new disabled row remains keyless. To
activate a disabled row, enable it and explicitly resubmit the key in the same
save. The bootstrap-status, key-list, and registration checks do not follow
redirects, so credentials cannot be forwarded to another origin.

After adoption, the plugin stores a credential-free SHA-256 target fingerprint
covering the canonical primary HTTP authority, fallback IP, port, HTTP/TLS
flags, and WebSocket authority flags. Runtime callers recompute it before using
the stored key and fail closed on target drift. The WebSocket client also
disables ambient proxies, refuses a server-selected redirect before sending the
key, rechecks trust after its handshake and periodically while connected, and
is cancelled when the endpoint changes.

Keep the first candidate until the NetBox save commits. If proxbox-api accepts
the bootstrap but the local database transaction later rolls back, retry with
that same candidate. The backend is now initialized, so the retry proves the
candidate with `GET /auth/keys` and can safely commit it locally.

### Manual Token Management

The diagnostic command never prints token fragments. Disabled endpoints are
always skipped, including under `--fix`. Without `--fix` the command is
read-only and does not contact an unadopted legacy target. After the operator
reviews the target, `--fix` authenticates the durably stored key and records its
target fingerprint; it performs a one-time bootstrap only when the backend
confirms that no key exists:

```bash
# Check token status
python manage.py proxbox_fix_tokens

# Fix unregistered tokens
python manage.py proxbox_fix_tokens --fix
```

### Safe key rotation

Keep the current key active until the replacement has been adopted and verified:

```bash
# 1. Authenticate with the current key and create a replacement.
curl -X POST http://localhost:8800/auth/keys \
  -H "X-Proxbox-API-Key: current-key"
```

The response exposes `raw_key` exactly once. Copy it directly into the existing
NetBox `FastAPIEndpoint` token field. Saving performs a protected read with the
candidate before changing the encrypted database value. Verify another
protected backend request from the plugin, then deactivate or delete the old
key. If any step fails, keep the old key active and retry only after resolving
the reported condition; the plugin never substitutes or bootstraps a different
credential automatically.

The unauthenticated `POST /auth/register-key` route is only for a backend whose
bootstrap status explicitly reports that it has no keys. It is never a rotation
mechanism, and HTTP `409` is a failure rather than proof that a candidate works.

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
