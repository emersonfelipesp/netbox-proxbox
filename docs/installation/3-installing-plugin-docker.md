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
netbox-proxbox @ git+https://github.com/emersonfelipesp/netbox-proxbox.git
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

## Endpoint Addresses in a Compose Deployment

This is the part that most often costs time, because the correct value depends on **which
container is doing the dialling** — and for the two endpoint records, that is not the same
container.

### The rule

| Endpoint record | Consumed by | Address it needs |
|---|---|---|
| **ProxBox API (FastAPI)** | the **NetBox** container | how NetBox reaches the backend |
| **NetBox API** | the **backend** container | how the backend reaches NetBox |

Both are filled in from the NetBox UI, which makes it easy to reach for the address *your
browser* uses. That address is almost never right for either record.

### Standalone container (published on the host)

The `docker run -p 8800:8000` command in
[Proxbox Backend Setup](./backend-setup.md) publishes the backend on a host port, and
`FastAPIEndpoint.port` defaults to `8800` to match:

| Field | Value |
|---|---|
| **Domain** or **IP address** | the host's name or address |
| **HTTP port** | `8800` (the published host port) |

### Same Compose project (the case the default does not fit)

When the backend runs as a service in the **same Compose project** as NetBox, the two
containers talk over the Compose network. A host port published on `127.0.0.1` is **not**
reachable from inside the NetBox container, so `8800` is the wrong value here — use the
service name and the **container-internal** port.

```yaml
# docker-compose.override.yml — alongside netbox-docker's own services
services:
  proxbox-api:
    image: emersonfelipesp/proxbox-api:latest
    environment:
      # Required before the first Proxmox endpoint can be created.
      PROXBOX_ENCRYPTION_KEY: ${PROXBOX_ENCRYPTION_KEY:?set this in your .env}
    # Publishing to the host is optional and only for your own browser or curl.
    # It has no effect on how NetBox reaches the backend.
    ports:
      - "127.0.0.1:8800:8000"
    # The image declares a /data volume and defaults its SQLite database to
    # /data/database.db. Name the volume so `docker compose down` and image
    # upgrades do not orphan the endpoint configuration.
    volumes:
      - proxbox-api-data:/data

volumes:
  proxbox-api-data:
```

!!! warning "A backend-local encryption key is not on that volume by default"
    If you let the backend generate its own key instead of passing
    `PROXBOX_ENCRYPTION_KEY`, the key file lands next to the installed package
    (`/app/data/encryption.key`), **not** on `/data` — so recreating the container
    destroys the key while the database survives, stranding every stored credential.
    Either use `PROXBOX_ENCRYPTION_KEY` as shown above, or set
    `PROXBOX_ENCRYPTION_KEY_FILE=/data/encryption.key`. See
    [Credential Encryption Key](./backend-setup.md).

Then create the two endpoint records with the addresses each **container** sees:

| Record | Field | Value | Why |
|---|---|---|---|
| **ProxBox API (FastAPI)** | Domain | `proxbox-api` | the Compose service name, resolvable from the NetBox container |
| | HTTP port | `8000` | the port the backend listens on **inside** its container, not the published `8800` |
| | Use HTTPS | ✗ | intra-Compose traffic on the non-TLS image |
| **NetBox API** | Domain | `netbox` | netbox-docker's service name, resolvable from the backend container |
| | HTTP port | `8080` | netbox-docker's in-container HTTP port; confirm it against your own compose file |
| | API token | a NetBox token with write access | the backend writes objects with it |

!!! warning "Not `localhost`, and not the published port"
    Inside a container, `localhost` is that container. A **NetBox API** record pointing at
    `localhost` tells the backend to call *itself*, and a **ProxBox API** record pointing
    at `127.0.0.1:8800` tells NetBox to call *itself*. Both fail in ways that look like the
    other service being down.

!!! tip "Check your own service and port names"
    `proxbox-api`, `netbox`, and `8080` above are netbox-docker's conventional names. If
    you renamed a service or changed a listen port, use yours — `docker compose ps` and
    your own compose file are the authority.

    Confirm both directions **before** saving either record. The NetBox image ships
    Python, so this works without assuming `curl` is installed:

    ```bash
    # NetBox container -> backend
    docker compose exec netbox python3 -c \
      "import urllib.request;print(urllib.request.urlopen('http://proxbox-api:8000/').status)"

    # backend container -> NetBox
    docker compose exec proxbox-api python3 -c \
      "import urllib.request;print(urllib.request.urlopen('http://netbox:8080/api/').status)"
    ```

    A `NameResolutionError` means the service name is wrong or the two services are not on
    the same Compose network; a connection refusal means the name resolved but the port is
    wrong.

    The same service-name-plus-internal-port form is used by the scheduler example that
    ships with this repo
    ([`proxbox_scheduler/docker-compose.example.yml`](https://github.com/emersonfelipesp/netbox-proxbox/blob/main/proxbox_scheduler/docker-compose.example.yml)),
    which points at `http://proxbox-api:8000`.

## Scheduled sync deployments

After the long-lived stack is up, you usually want syncs to run on a
schedule without a human clicking **Full Update**. The recommended
one-shot pattern ships next to this page as
[`docker-compose-single-exec.yml`](./docker-compose-single-exec.yml) and
is documented in
[Scheduled sync — one-shot `docker compose` pattern](../operations/single-exec.md),
with worked crontab and systemd-timer examples.

## Next Step

The plugin requires the separate FastAPI backend service. Continue with [Proxbox Backend Setup](./backend-setup.md).
