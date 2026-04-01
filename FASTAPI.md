# Proxbox Backend Notes

Proxbox no longer ships an in-repo experimental FastAPI app under the NetBox plugin package. The current backend is the separate [`proxbox-api`](https://github.com/emersonfelipesp/proxbox-api) service consumed by this plugin.

Use one of these current paths instead:

- Published package or source checkout of `proxbox-api`
- Docker image `emersonfelipesp/proxbox-api:latest`
- TLS Docker image `emersonfelipesp/proxbox-api:latest-mkcert`

Typical local run commands are:

```bash
uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800
```

or, from a source checkout of the backend repository:

```bash
uv run fastapi run proxbox_api.main:app --host 0.0.0.0 --port 8000
```

For current installation and deployment guidance, use:

- `docs/installation/backend-setup.md`
- `docs/backend/using-pip.md`
- `docs/backend/using-git.md`
- `docs/backend/using-docker.md`

This file is kept only as a compatibility note for older references to `FASTAPI.md`.
