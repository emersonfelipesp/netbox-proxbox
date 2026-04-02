# E2E Docker Testing

The `E2E Docker` GitHub Action validates the real integration path between:

- NetBox (with `netbox_proxbox` plugin installed)
- NetBox RQ worker (job execution)
- Proxbox backend (`proxbox-api` container)
- A mocked Proxmox API service (no real Proxmox calls)

## Architecture

```mermaid
flowchart LR
  A[GitHub Actions Runner]

  subgraph D[Docker network: proxbox-e2e]
    NB[NetBox Container\nplugin installed]
    RQ[NetBox rqworker\nmanage.py rqworker]
    PB[Proxbox API Container\nemersonfelipesp/proxbox-api:latest]
    PM[Proxmox Mock Container\nFastAPI mock_proxmox_api.py]
    PG[(PostgreSQL)]
    RD[(Redis)]
  end

  A --> NB
  A --> PB
  A --> PM
  A --> RQ

  NB --> PG
  NB --> RD
  RQ --> PG
  RQ --> RD

  NB -->|plugin sync proxy calls| PB
  PB -->|Proxmox API calls| PM
  PB -->|NetBox REST API| NB
```

## Workflow Sequence

```mermaid
sequenceDiagram
  participant GA as GitHub Action
  participant NB as NetBox + Plugin
  participant RQ as NetBox rqworker
  participant PB as proxbox-api
  participant PM as Proxmox mock

  GA->>NB: Start stack and wait for readiness
  GA->>NB: Create NetBox API token
  GA->>PB: Configure backend endpoints (NetBox, Proxmox)
  GA->>NB: Configure plugin endpoints (NetBox, FastAPI, Proxmox)
  GA->>NB: POST /plugins/proxbox/sync/full-update/
  NB->>RQ: Enqueue Proxbox sync job
  RQ->>PB: Request full-update stream
  PB->>PM: Read mocked Proxmox cluster/resources/config
  PB->>NB: Create or update NetBox objects via REST
  GA->>NB: Poll /api/core/jobs until completed
  GA->>NB: Assert plugin data endpoints contain synced records
  GA->>PM: Change mocked VM status (running -> stopped)
  GA->>NB: Trigger full-update again
  RQ->>PB: Run sync again
  PB->>NB: Update VM status in NetBox (active -> offline)
  GA->>NB: Assert VM status transition in NetBox
```

## What Is Verified

- NetBox plugin UI/API routes are reachable and functioning.
- Keepalive routes for FastAPI, NetBox, and Proxmox endpoint checks succeed.
- Full sync jobs run through real NetBox background jobs (`rqworker`).
- Proxbox backend stream endpoint (`/full-update/stream`) completes successfully.
- Synced storage/backup/snapshot plugin models are populated.
- VM status update behavior is validated by mutating mocked Proxmox VM state and confirming NetBox status changes after re-sync.

## Mocking Strategy

Only the Proxmox side is mocked. The test does not call any real Proxmox cluster.

- Mock API routes are served by `tests/e2e/mock_proxmox_api.py`.
- The mock supports runtime VM status mutation via `POST /__admin/vm/{vmid}/status`.
- NetBox and proxbox-api routes are real containers and are exercised end-to-end.
