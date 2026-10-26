# Companion Plugins

The Proxbox ecosystem is built around a central FastAPI backend (`proxbox-api`) and the core NetBox plugin (`netbox-proxbox`). Four standalone companion plugins extend that foundation with inventory for adjacent Proxmox-family infrastructure: Proxmox Backup Server, Proxmox Datacenter Manager, Ceph storage clusters, and HashiCorp Packer image factories.

Each companion plugin is a fully independent NetBox plugin package. You install only the plugins that match your infrastructure.

For the planned integration of secrets, procedure variables and mandatory audited
writes, see [Audited Proxmox writes with RPC and OpenBao](./audited-proxmox-writes.md).
It distinguishes existing behavior from the implementation required for cutover.

## Plugin Overview

| Plugin | PyPI package | What it inventories |
|---|---|---|
| [netbox-pbs](./netbox-pbs.md) | `netbox-pbs` | Proxmox Backup Server — direct PBS inventory, managed configuration, deployments, and backup correlation |
| [netbox-pdm](./netbox-pdm.md) | `netbox-pdm` | Proxmox Datacenter Manager — PDM endpoints and their remotes (PVE + PBS) |
| [netbox-ceph](./netbox-ceph.md) | `netbox-ceph` | Ceph clusters — nodes, OSDs, pools, filesystems, CRUSH rules, flags, health checks |
| [netbox-packer](./netbox-packer.md) | `netbox-packer` | HashiCorp Packer — image definitions and build execution records |
| [netbox-openbao](./netbox-openbao.md) | `netbox-openbao` | OpenBao-backed SSH credentials for synced VMs and containers (separate plugin; not proxbox-api sync) |
| [netbox-rpc](./netbox-rpc.md) | `netbox-rpc` | Audited Proxmox host procedures and service monitoring through the RPC catalog |

## Ecosystem Architecture

```mermaid
graph TB
    subgraph proxmox["Proxmox Infrastructure"]
        PVE["Proxmox VE\ncluster / nodes"]
        PBS["Proxmox Backup Server"]
        PDM["Proxmox Datacenter Manager"]
        CEPH["Ceph Cluster"]
    end

    subgraph packer_infra["Image Factory"]
        PACKER_SRC["HashiCorp Packer\nbuild pipeline"]
    end

    subgraph backend["proxbox-api (FastAPI backend)"]
        PROXBOX_API["Proxmox operations and other companion backends"]
    end

    subgraph netbox["NetBox"]
        NB_PROXBOX["netbox-proxbox\n(core plugin)"]
        NB_PBS["netbox-pbs"]
        NB_PDM["netbox-pdm"]
        NB_CEPH["netbox-ceph"]
        NB_PACKER["netbox-packer"]
    end

    PVE -- "Proxmox API" --> PROXBOX_API
    PBS -- "PBS REST API: inventory and configuration" --> NB_PBS
    PDM -- "PDM API" --> PROXBOX_API
    CEPH -- "Ceph REST / MGR" --> PROXBOX_API
    PACKER_SRC -- "webhooks / polling" --> PROXBOX_API

    PROXBOX_API -- "SSE stream" --> NB_PROXBOX
    NB_PBS -- "typed Proxmox deployment, storage, and backup operations" --> PROXBOX_API
    PROXBOX_API -- "REST sync" --> NB_PDM
    PROXBOX_API -- "REST sync" --> NB_CEPH
    PROXBOX_API -- "REST" --> NB_PACKER

    NB_PDM -- "links Proxmox endpoints" --> NB_PROXBOX
    NB_PDM -- "links PBS servers" --> NB_PBS

    style NB_PROXBOX fill:#1565c0,color:#fff
    style PROXBOX_API fill:#e65100,color:#fff
```

## How Sync Works

Companion plugins use different transports. The PBS sync worker reads PBS
directly, as shown below. Its Proxmox deployment and backup operations use
proxbox-api. The other companions retain their documented transport paths.
OpenBao credential management and RPC execution use separate workflows:

```mermaid
sequenceDiagram
    participant U as Operator / Scheduler
    participant NB as NetBox (netbox-pbs)
    participant RQ as RQ Worker
    participant PBS as Proxmox Backup Server

    U->>NB: Trigger sync (UI or scheduler)
    NB->>RQ: Enqueue SyncJob (default queue)
    RQ->>PBS: Read PBS REST API by sync stage
    PBS-->>RQ: Configuration, backup, and task data
    RQ->>NB: Reconcile inventory and desired-state observations
    NB-->>U: Job completed / errored
```

Operational guidance for companion jobs:

- PBS sync jobs run on NetBox's **`default`** RQ queue. A stock `manage.py rqworker` (no extra arguments) picks them up.
- Check each companion's job timeout and scheduler settings in its own guide. Netbox Proxbox exposes its bounded sync timeout under **Proxbox > Settings**.
- **Branch-aware sync** (optional, requires `netbox-branching`) creates an isolated NetBox branch and runs the sync against it. Conflict handling is plugin-specific; see each plugin's settings and guide.

## Plugin Dependency Map

```mermaid
graph LR
    NB_PROXBOX["netbox-proxbox\n(required base)"]
    NB_PBS["netbox-pbs"]
    NB_PDM["netbox-pdm"]
    NB_CEPH["netbox-ceph"]
    NB_PACKER["netbox-packer"]
    BRANCHING["netbox-branching\n(optional)"]

    NB_PROXBOX --> NB_PBS
    NB_PROXBOX --> NB_PDM
    NB_PROXBOX --> NB_CEPH
    NB_PROXBOX --> NB_PACKER
    NB_PBS --> NB_PDM
    BRANCHING -.-> NB_PBS
    BRANCHING -.-> NB_PDM
    BRANCHING -.-> NB_CEPH
```

`netbox-proxbox` must be installed before any companion plugin. `netbox-pdm` further cross-references `netbox-pbs` models, so install and migrate `netbox-pbs` before `netbox-pdm`.

## Installing All Companion Plugins

Install the packages you need alongside `netbox-proxbox`:

```bash
source /opt/netbox/venv/bin/activate
pip install netbox-proxbox netbox-pbs netbox-pdm netbox-ceph netbox-packer
```

Enable them in `configuration.py`. The order matters: `netbox_proxbox` must appear first, and `netbox_pbs` before `netbox_pdm`:

```python
PLUGINS = [
    "netbox_proxbox",
    "netbox_pbs",
    "netbox_pdm",
    "netbox_ceph",
    "netbox_packer",
]
```

Run migrations for each plugin:

```bash
cd /opt/netbox/netbox
python3 manage.py migrate netbox_proxbox
python3 manage.py migrate netbox_pbs
python3 manage.py migrate netbox_pdm
python3 manage.py migrate netbox_ceph
python3 manage.py migrate netbox_packer
python3 manage.py collectstatic --no-input
sudo systemctl restart netbox netbox-rq
```

!!! note "Partial installs"
    You do not need to install all four companion plugins. Each is independent; for example, `netbox-ceph` works without `netbox-pbs`. The only required dependency for all four is `netbox-proxbox`.

!!! warning "Migration order"
    Always migrate `netbox_proxbox` before any companion plugin. Migrate `netbox_pbs` before `netbox_pdm` because `PDMEndpoint` has an M2M relation to `PBSServer`.
