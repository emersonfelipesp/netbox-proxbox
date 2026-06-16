# Data Model

This page documents all persisted models in the Proxbox ecosystem — the Django plugin models stored in NetBox's PostgreSQL database, and the SQLite models used by `proxbox-api`.

---

## Plugin Models (NetBox PostgreSQL)

The netbox-proxbox plugin defines Django models for endpoint configuration, Proxmox inventory, Cloud image templates, Firecracker micro-VM inventory, operational records, and plugin settings. They inherit from `NetBoxModel` (which provides `tags`, `custom_fields`, timestamps, and `ObjectChange` tracking) or from `NetBoxModel` through `EndpointBase`.

### Entity Relationship Diagram

```mermaid
erDiagram
    ProxmoxEndpoint {
        int     id
        string  name
        string  domain
        int     port
        string  mode
        string  username
        string  token_name
        string  token_value
        string  version
        fk      ip_address
        m2m     allowed_tenants
    }
    NetBoxEndpoint {
        int     id
        string  name
        string  domain
        int     port
        string  token_version
        string  token_name
        string  token_secret
        string  token_key
    }
    FastAPIEndpoint {
        int     id
        string  name
        string  domain
        int     port
        string  backend_token
        bool    verify_ssl
        string  websocket_url
    }
    ProxmoxCluster {
        int     id
        string  name
        fk      proxmox_endpoint
        fk      netbox_cluster
    }
    ProxmoxNode {
        int     id
        string  name
        fk      proxmox_endpoint
        fk      netbox_device
        fk      proxmox_cluster
    }
    ProxmoxStorage {
        int     id
        string  name
        string  storage_type
        string  path
        fk      proxmox_endpoint
    }
    ProxmoxStorageVirtualDisk {
        int     id
        fk      proxmox_storage
        fk      virtual_disk
    }
    BackupRoutine {
        int     id
        string  name
        string  vmid
        fk      proxmox_endpoint
    }
    Replication {
        int     id
        string  name
        string  vmid
        fk      proxmox_endpoint
    }
    VMBackup {
        int     id
        string  volid
        string  format
        string  size
        fk      virtual_machine
    }
    VMSnapshot {
        int     id
        string  name
        string  description
        fk      virtual_machine
    }
    VMTaskHistory {
        int     id
        string  upid
        string  status
        string  type
        fk      virtual_machine
    }
    FirecrackerHostPool {
        int     id
        string  name
        string  slug
        string  default_network_mode
        bool    is_active
    }
    FirecrackerHost {
        int     id
        string  name
        url     agent_base_url
        string  status
        bool    kvm_available
        int     capacity_vcpus
        int     capacity_memory_mib
        fk      pool
        fk      host_vm
        fk      proxmox_node
    }
    FirecrackerImageTemplate {
        int     id
        string  name
        string  slug
        string  architecture
        string  os_family
        string  kernel_image_url
        string  rootfs_image_url
        bool    is_active
    }
    FirecrackerMicroVM {
        int     id
        uuid    microvm_id
        string  name
        string  status
        string  network_mode
        int     vcpus
        int     memory_mib
        int     disk_mib
        string  guest_ip
        fk      tenant
        fk      host
        fk      image
    }
    ProxboxPluginSettings {
        int     id
        bool    sync_enabled
        string  sync_interval
    }

    ProxmoxEndpoint ||--o{ ProxmoxCluster : "has"
    ProxmoxEndpoint ||--o{ ProxmoxNode : "has"
    ProxmoxEndpoint ||--o{ ProxmoxStorage : "has"
    ProxmoxEndpoint ||--o{ BackupRoutine : "has"
    ProxmoxEndpoint ||--o{ Replication : "has"
    ProxmoxCluster ||--o{ ProxmoxNode : "contains"
    ProxmoxStorage ||--o{ ProxmoxStorageVirtualDisk : "links"
    FirecrackerHostPool ||--o{ FirecrackerHost : "contains"
    FirecrackerHost ||--o{ FirecrackerMicroVM : "runs"
    FirecrackerImageTemplate ||--o{ FirecrackerMicroVM : "boots"
    ProxmoxNode ||--o{ FirecrackerHost : "hosts agent VM"
```

> **NetBox core relationships** — Plugin models link to standard NetBox objects via foreign keys:
>
> - `ProxmoxCluster.netbox_cluster` → `virtualization.Cluster`
> - `ProxmoxNode.netbox_device` → `dcim.Device`
> - `VMBackup.virtual_machine` → `virtualization.VirtualMachine`
> - `VMSnapshot.virtual_machine` → `virtualization.VirtualMachine`
> - `VMTaskHistory.virtual_machine` → `virtualization.VirtualMachine`
> - `ProxmoxEndpoint.ip_address` → `ipam.IPAddress`
> - `FirecrackerHost.host_vm` → `virtualization.VirtualMachine` for the Proxmox VM running the host agent
> - `FirecrackerHost.proxmox_node` → `netbox_proxbox.ProxmoxNode`
> - `FirecrackerMicroVM.tenant` → `tenancy.Tenant`

### VM-Centric Models

```mermaid
erDiagram
    VirtualMachine["virtualization.VirtualMachine\n(NetBox core)"] {
        int    id
        string name
        fk     cluster
    }
    VMBackup {
        int    id
        string volid
        string format
        string size
        string notes
    }
    VMSnapshot {
        int    id
        string name
        string description
        string parent
    }
    VMTaskHistory {
        int    id
        string upid
        string status
        string type
        string exitstatus
    }

    VirtualMachine ||--o{ VMBackup : "has backups"
    VirtualMachine ||--o{ VMSnapshot : "has snapshots"
    VirtualMachine ||--o{ VMTaskHistory : "has task history"
```

---

## Model Summary Tables

### Endpoint Models

| Model | Key Fields | Purpose |
|---|---|---|
| `ProxmoxEndpoint` | domain, port (8006), username, token_name, token_value, mode, version | Credentials and address for one Proxmox VE instance or cluster |
| `NetBoxEndpoint` | domain, port (8000), token_version (v1/v2), token_name, token_secret, token_key | Address and credentials for a remote NetBox instance |
| `FastAPIEndpoint` | domain, port (8000), backend_token, verify_ssl, websocket_url | Address and auth token for the `proxbox-api` backend |
| `PBSEndpoint` | domain, port, token, verify_ssl | Proxmox Backup Server connection record |
| `PDMEndpoint` | domain, port, token, verify_ssl | Proxmox Datacenter Manager connection record |
| `PDMRemote` | name, pdm_endpoint, remote_type | PDM-managed remote (links to PBS or PVE remotes managed by PDM) |

All endpoint models that inherit `EndpointBase` share the `enabled` field. When
that field is `False`, the row is inventory-only: keep it visible in UI/API
surfaces, but return before backend registration, status/keepalive checks,
OpenAPI reads, sync scopes, or any proxbox-api, PVE, PBS, PDM, NetBox, or
companion-plugin network attempt. Use
`netbox_proxbox.services.endpoint_enabled.disabled_endpoint_detail()` at the
start of new endpoint operational paths.

`ProxmoxEndpoint.allowed_tenants` is a tenant allow-list consumed by NMS Cloud.
An empty relation means the endpoint stays in the default/global pool. A
non-empty relation pins the endpoint to the listed tenants. The paired backend
uses explicit grants as an override: if a tenant matches any explicitly granted
endpoint, global/default endpoints are hidden for that tenant; otherwise the
tenant continues to see only the default/global rows.

!!! warning "Single FastAPIEndpoint constraint"
    The plugin's HTTP and WebSocket helpers resolve the backend via `FastAPIEndpoint.objects.first()`. If multiple `FastAPIEndpoint` rows exist, whichever sorts first in the queryset is used for all backend communication. Keep exactly one row in production.

### Infrastructure Models

| Model | FK to | Purpose |
|---|---|---|
| `ProxmoxCluster` | `ProxmoxEndpoint`, `Cluster` (NetBox core) | Mirrors a Proxmox cluster into a NetBox Cluster object |
| `ProxmoxNode` | `ProxmoxEndpoint`, `Device` (NetBox core), `ProxmoxCluster` | Mirrors a Proxmox hypervisor node into a NetBox Device |
| `ProxmoxStorage` | `ProxmoxEndpoint` | Inventory of storage pools/directories on a Proxmox cluster |
| `ProxmoxStorageVirtualDisk` | `ProxmoxStorage`, `VirtualDisk` (NetBox core) | Join table linking storage entries to NetBox virtual disk objects |
| `NodeSSHCredential` | `ProxmoxNode` | SSH credentials for per-node hardware-discovery SSH sessions |
| `ProxmoxDatacenterCpuModel` | `ProxmoxEndpoint` | Custom CPU model definitions synced from Proxmox datacenter config |

### VM Data Models

| Model | FK to | Purpose |
|---|---|---|
| `VMBackup` | `VirtualMachine` (NetBox core) | Per-VM backup inventory (volid, format, size) |
| `VMSnapshot` | `VirtualMachine` (NetBox core) | Per-VM snapshot inventory (name, description, parent) |
| `VMTaskHistory` | `VirtualMachine` (NetBox core) | Per-VM task history from the Proxmox task log (UPID, status, type) |
| `ProxmoxVMTemplate` | `ProxmoxCluster`, `ProxmoxNode`, `VirtualMachine` (optional) | VM template inventory; `source_vm` and `cloned_vms` M2M track lineage |
| `ProxmoxVMCloudInit` | `VirtualMachine` (NetBox core) | Cloud-init configuration record for a VM |
| `CloudImageTemplate` | — | Image factory catalog entry for QEMU/cloud-image provisioning |

### Firewall Models

Six read-only models persist Proxmox VE firewall objects synced from proxbox-api:

| Model | Purpose |
|---|---|
| `ProxmoxFirewallSecurityGroup` | Named firewall security group (with inline rules) |
| `ProxmoxFirewallRule` | Individual firewall rule (datacenter or per-VM) |
| `ProxmoxFirewallIPSet` | IP set definition |
| `ProxmoxFirewallIPSetEntry` | Entry within an IP set |
| `ProxmoxFirewallAlias` | IP alias definition |
| `ProxmoxFirewallOptions` | Firewall options object (per datacenter or per VM) |

### SDN Models (PVE 9.2+)

| Model | Purpose |
|---|---|
| `ProxmoxSdnFabric` | SDN fabric definition synced from Proxmox |
| `ProxmoxSdnRouteMap` | SDN route-map definition |
| `ProxmoxSdnPrefixList` | SDN prefix-list definition |

### Operational Models

| Model | Purpose |
|---|---|
| `BackupRoutine` | Backup routine definitions synced from Proxmox (vzdump jobs) |
| `Replication` | Replication job definitions synced from Proxmox |
| `ProxmoxApplyJob` | Tracks a NetBox-to-Proxmox intent apply job |
| `DeletionRequest` | Auditable delete-request workflow requiring explicit authorization |
| `ProxboxPluginSettings` | Singleton plugin settings including sync modes, batch tunables, and feature flags |

---

## proxbox-api SQLite Models

The `proxbox-api` backend stores its own configuration in a local SQLite database (`database.db`). These models are managed by SQLModel and are separate from the NetBox database.

```mermaid
erDiagram
    NetBoxEndpoint_BE["NetBoxEndpoint\n(SQLite)"] {
        int     id
        string  url
        string  token_version
        string  token
        string  token_key
        bool    verify_ssl
    }
    ProxmoxEndpoint_BE["ProxmoxEndpoint\n(SQLite)"] {
        int     id
        string  url
        string  token
        string  username
        bool    verify_ssl
        string  cluster_name
    }
    ApiKey {
        int     id
        string  key_hash
        string  description
        datetime created_at
    }
    AuthLockout {
        string  ip
        int     attempts
        datetime last_attempt
    }
```

### Firecracker Cloud Models

Firecracker inventory is separate from NetBox core `VirtualMachine` rows. The NMS Cloud UI uses these models when the user chooses the Firecracker runtime, while the existing QEMU path continues to use `CloudImageTemplate` and NetBox virtualization objects.

| Model | FK to | Purpose |
|---|---|---|
| `FirecrackerHostPool` | `Tenant` M2M | Tenant-visible capacity pool for Firecracker host-agent VMs |
| `FirecrackerHost` | `FirecrackerHostPool`, optional `VirtualMachine`, optional `ProxmoxNode` | A host-agent VM capable of launching Firecracker micro-VMs |
| `FirecrackerImageTemplate` | `Tenant` M2M | Kernel/rootfs image bundle shown in the NMS Cloud runtime selector |
| `FirecrackerMicroVM` | `FirecrackerHost`, `FirecrackerImageTemplate`, optional `Tenant` | Provisioned Firecracker instance tracked with `instance_ref="firecracker:<id>"` |

!!! info "Two NetBoxEndpoint concepts"
    The `NetBoxEndpoint` in the NetBox plugin (PostgreSQL) stores the remote NetBox address from the plugin's perspective. The `NetBoxEndpoint` in proxbox-api's SQLite stores the same information from the backend's perspective. They are kept in sync via Django signals and the `FastAPIEndpoint.signals` auto-registration flow.

### SQLite Model Purpose

| Model | Purpose |
|---|---|
| `NetBoxEndpoint` (SQLite) | NetBox connection details used by the FastAPI session layer |
| `ProxmoxEndpoint` (SQLite) | Proxmox connection details used by the FastAPI session layer |
| `ApiKey` | bcrypt-hashed API keys for `X-Proxbox-API-Key` authentication |
| `AuthLockout` | IP-based brute-force lockout tracking (5 attempts, 300 s lock) |
