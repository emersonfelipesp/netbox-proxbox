# Local Proxmox Mock

You can run the Proxmox mock API locally (without Docker) to test Proxbox routes and sync behavior.

The mock service is implemented at `tests/e2e/mock_proxmox_api.py`.

## 1) Install local dependencies

From the repository root:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[e2e]"
```

## 2) Start the mock API service

```bash
python tests/e2e/mock_proxmox_api.py --host 127.0.0.1 --port 8006
```

Alternative (same app, direct uvicorn module path):

```bash
uvicorn tests.e2e.mock_proxmox_api:app --host 127.0.0.1 --port 8006
```

## 3) Validate mock routes

```bash
curl -s http://127.0.0.1:8006/api2/json/version
curl -s http://127.0.0.1:8006/api2/json/cluster/status
curl -s http://127.0.0.1:8006/api2/json/cluster/resources
```

## 4) Change mock VM status (update-path testing)

You can mutate VM state to validate update sync behavior.

Set VM `101` to `stopped`:

```bash
curl -s -X POST http://127.0.0.1:8006/__admin/vm/101/status \
  -H 'Content-Type: application/json' \
  -d '{"status":"stopped"}'
```

Set it back to `running`:

```bash
curl -s -X POST http://127.0.0.1:8006/__admin/vm/101/status \
  -H 'Content-Type: application/json' \
  -d '{"status":"running"}'
```

## 5) Point Proxbox endpoint to local mock

When creating or editing the Proxmox endpoint in Proxbox/NetBox plugin, use:

- Host/domain: `127.0.0.1`
- Port: `8006`
- Username: `root@pam`
- Token name: `e2e`
- Token value: `e2e-secret`
- Verify SSL: disabled

If your backend runs in Docker and the mock runs on your host machine, use a host-reachable address (for example `host.docker.internal` where supported) instead of `127.0.0.1`.
