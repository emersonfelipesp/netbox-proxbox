# VM Data API

These models store per-virtual-machine data synced from Proxmox: guest OS interface metadata, guest-interface address links, backup records, snapshot records, and task history entries.

For common API conventions (authentication, pagination, nested serializers), see [API Overview](index.md).

---

## Guest VM Interfaces

`GuestVMInterface` records QEMU guest-agent OS interface names without renaming
the core NetBox VM interface. Proxmox-side NICs remain
`virtualization.VMInterface` rows named `net0`, `net1`, etc. Guest-agent rows
use names such as `ens18` or `eth0` and link to the core VM interface when the
MAC address matches. The `vm_interface` relation is nullable for agent-only
interfaces such as Linux bridges.

```
GET    /api/plugins/proxbox/guest-vm-interfaces/
GET    /api/plugins/proxbox/guest-vm-interfaces/{id}/
POST   /api/plugins/proxbox/guest-vm-interfaces/
PUT    /api/plugins/proxbox/guest-vm-interfaces/{id}/
PATCH  /api/plugins/proxbox/guest-vm-interfaces/{id}/
DELETE /api/plugins/proxbox/guest-vm-interfaces/{id}/
```

**Filterable fields:** `id`, `virtual_machine`, `vm_interface`, `name`,
`mac_address`, `enabled`, `mtu`

## Guest VM Interface Addresses

`GuestVMInterfaceAddress` links a guest OS interface to an existing core
`ipam.IPAddress`. It deliberately reuses the same IP object already assigned to
the core VM interface and protects that IP from deletion while the link exists.

```
GET    /api/plugins/proxbox/guest-vm-interface-addresses/
GET    /api/plugins/proxbox/guest-vm-interface-addresses/{id}/
POST   /api/plugins/proxbox/guest-vm-interface-addresses/
PUT    /api/plugins/proxbox/guest-vm-interface-addresses/{id}/
PATCH  /api/plugins/proxbox/guest-vm-interface-addresses/{id}/
DELETE /api/plugins/proxbox/guest-vm-interface-addresses/{id}/
```

**Filterable fields:** `id`, `guest_interface`, `ip_address`,
`virtual_machine`, `vm_interface`

---

## VM Backup

A backup record for a virtual machine or container, as reported by Proxmox storage.

```
GET    /api/plugins/proxbox/backups/
GET    /api/plugins/proxbox/backups/{id}/
POST   /api/plugins/proxbox/backups/
PUT    /api/plugins/proxbox/backups/{id}/
PATCH  /api/plugins/proxbox/backups/{id}/
DELETE /api/plugins/proxbox/backups/{id}/
```

**Example — list all backups for a virtual machine:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/backups/?virtual_machine_id=10"
```

**Example — filter for PBS VM backups:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/backups/?format=pbs-vm"
```

**Filterable fields:** `id`, `proxmox_storage`, `virtual_machine`, `subtype`, `format`, `creation_time`, `size`, `used`, `encrypted`, `volume_id`, `vmid`

**Searchable fields (`?q=`):** virtual machine name, storage name, `volume_id`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/backups/1/",
  "display": "vm-100 backup (2026-04-01)",
  "proxmox_storage": {
    "id": 2,
    "url": "/api/plugins/proxbox/storage/2/",
    "display": "backup-storage",
    "cluster": {"id": 5, "name": "prod-cluster"},
    "name": "backup-storage"
  },
  "virtual_machine": {
    "id": 10,
    "url": "/api/virtualization/virtual-machines/10/",
    "display": "web-server-01",
    "name": "web-server-01"
  },
  "storage": "backup-storage",
  "subtype": {"value": "qemu", "label": "QEMU"},
  "format": {"value": "pbs-vm", "label": "PBS VM"},
  "creation_time": "2026-04-01T02:00:00Z",
  "size": 10737418240,
  "notes": "nightly backup",
  "volume_id": "vm/100/2026-04-01T02:00:00Z",
  "vmid": 100,
  "used": 8589934592,
  "encrypted": "a]b:c1:d2:e3",
  "verification_state": "ok",
  "verification_upid": "UPID:pve-node-01:...",
  "tags": [],
  "custom_fields": {},
  "created": "2026-04-01T02:05:00Z",
  "last_updated": "2026-04-01T02:05:00Z"
}
```

### Data Model

| Field | Type | Description |
|---|---|---|
| `proxmox_storage` | nested ProxmoxStorage (nullable) | Storage backend where this backup resides |
| `virtual_machine` | nested VirtualMachine | Backed-up virtual machine |
| `storage` | string | Raw Proxmox storage ID string |
| `subtype` | choice (nullable) | Guest type. Choices: `undefined`, `lxc`, `ct`, `qemu`, `vm` |
| `format` | choice (nullable) | Backup format. Choices: `undefined`, `pbs-vm`, `pbs-ct`, `zst`, `iso`, `tzst`, `tgz`, `qcow2`, `raw`, `tar`, `tbz` |
| `creation_time` | datetime | When the backup was created in Proxmox |
| `size` | integer | Backup size in bytes |
| `notes` | string | Free-text notes attached to the backup |
| `volume_id` | string | Proxmox volume identifier |
| `vmid` | integer | Proxmox VM ID |
| `used` | integer | Disk space actually used by this backup in bytes |
| `encrypted` | string | Encryption fingerprint from Proxmox (empty string = not encrypted) |
| `verification_state` | string | Last verification result (e.g. `ok`, `failed`) |
| `verification_upid` | string | UPID of the last verification task |

---

## VM Snapshot

A snapshot record for a virtual machine or container.

```
GET    /api/plugins/proxbox/snapshots/
GET    /api/plugins/proxbox/snapshots/{id}/
POST   /api/plugins/proxbox/snapshots/
PUT    /api/plugins/proxbox/snapshots/{id}/
PATCH  /api/plugins/proxbox/snapshots/{id}/
DELETE /api/plugins/proxbox/snapshots/{id}/
```

**Example — list all snapshots for a virtual machine:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/snapshots/?virtual_machine_id=10"
```

**Example — filter for active QEMU snapshots:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/snapshots/?subtype=qemu&status=active"
```

**Example — search by snapshot name:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/snapshots/?q=pre-upgrade"
```

**Filterable fields:** `id`, `proxmox_storage`, `virtual_machine`, `subtype`, `status`, `name`, `description`, `vmid`, `node`, `parent`, `snaptime`

**Searchable fields (`?q=`):** virtual machine name, storage name, snapshot `name`, `node`, `description`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/snapshots/1/",
  "display": "pre-upgrade",
  "proxmox_storage": null,
  "virtual_machine": {
    "id": 10,
    "url": "/api/virtualization/virtual-machines/10/",
    "display": "web-server-01",
    "name": "web-server-01"
  },
  "name": "pre-upgrade",
  "description": "Before OS upgrade",
  "vmid": 100,
  "node": "pve-node-01",
  "snaptime": "2026-03-15T10:00:00Z",
  "parent": "current",
  "subtype": {"value": "qemu", "label": "QEMU"},
  "status": {"value": "active", "label": "Active"},
  "tags": [],
  "custom_fields": {},
  "created": "2026-03-15T10:01:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

### Data Model

| Field | Type | Description |
|---|---|---|
| `proxmox_storage` | nested ProxmoxStorage (nullable) | Storage backend associated with this snapshot |
| `virtual_machine` | nested VirtualMachine | Snapshotted virtual machine |
| `name` | string | Snapshot name in Proxmox |
| `description` | string | Free-text snapshot description |
| `vmid` | integer | Proxmox VM ID |
| `node` | string | Node where the snapshot was created |
| `snaptime` | datetime | When the snapshot was taken |
| `parent` | string | Name of the parent snapshot (or `current`) |
| `subtype` | choice | Guest type. Choices: `qemu`, `lxc` |
| `status` | choice | Sync status. Choices: `active`, `stale` — `stale` means the snapshot no longer exists in Proxmox |

---

## VM Task History

A record of a Proxmox task run for a virtual machine (backup, migration, snapshot, start, stop, etc.).

```
GET    /api/plugins/proxbox/task-history/
GET    /api/plugins/proxbox/task-history/{id}/
POST   /api/plugins/proxbox/task-history/
PUT    /api/plugins/proxbox/task-history/{id}/
PATCH  /api/plugins/proxbox/task-history/{id}/
DELETE /api/plugins/proxbox/task-history/{id}/
```

!!! note "Upsert on POST"
    POST requests are idempotent by `upid`. If a task history record with the same UPID already exists, the POST updates it rather than returning a conflict error.

**Example — list all task history for a virtual machine:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/task-history/?virtual_machine_id=10"
```

**Example — filter for failed backup tasks:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/task-history/?task_type=vzdump&task_state=ERROR"
```

**Example — search by UPID:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/task-history/?q=UPID:pve-node-01"
```

**Filterable fields:** `id`, `virtual_machine`, `vm_type`, `upid`, `node`, `pid`, `pstart`, `task_id`, `task_type`, `username`, `start_time`, `end_time`, `description`, `status`, `task_state`, `exitstatus`

**Searchable fields (`?q=`):** virtual machine name, `vm_type`, `upid`, `node`, `task_id`, `task_type`, `username`, `description`, `status`, `task_state`, `exitstatus`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/task-history/1/",
  "display": "vzdump on pve-node-01 (2026-04-01)",
  "virtual_machine": {
    "id": 10,
    "url": "/api/virtualization/virtual-machines/10/",
    "display": "web-server-01",
    "name": "web-server-01"
  },
  "vm_type": "qemu",
  "upid": "UPID:pve-node-01:00001A2B:3C4D5E6F:67890ABC:vzdump:100:root@pam:",
  "node": "pve-node-01",
  "pid": 6699,
  "pstart": 1009001583,
  "task_id": "100",
  "task_type": "vzdump",
  "username": "root@pam",
  "start_time": "2026-04-01T02:00:00Z",
  "end_time": "2026-04-01T02:08:32Z",
  "description": "VM 100 backup",
  "status": "OK",
  "task_state": "stopped",
  "exitstatus": "OK",
  "tags": [],
  "custom_fields": {},
  "created": "2026-04-01T02:08:33Z",
  "last_updated": "2026-04-01T02:08:33Z"
}
```

### Data Model

| Field | Type | Description |
|---|---|---|
| `virtual_machine` | nested VirtualMachine | VM this task ran on |
| `vm_type` | string | Guest type (`qemu` or `lxc`) |
| `upid` | string | Proxmox Unique Process ID — globally unique task identifier |
| `node` | string | Node where the task ran |
| `pid` | integer | OS process ID |
| `pstart` | integer | Process start time (kernel ticks) |
| `task_id` | string | Proxmox task ID (usually the VMID) |
| `task_type` | string | Task type (e.g. `vzdump`, `vzmigrate`, `qmstart`, `qmstop`) |
| `username` | string | Proxmox user who initiated the task |
| `start_time` | datetime | When the task started |
| `end_time` | datetime (nullable) | When the task ended |
| `description` | string | Human-readable task description |
| `status` | string | Task completion status (e.g. `OK`, `error message`) |
| `task_state` | string | Task execution state (e.g. `stopped`, `running`) |
| `exitstatus` | string | Exit status string from Proxmox |
