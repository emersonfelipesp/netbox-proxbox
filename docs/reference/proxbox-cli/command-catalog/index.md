# Proxbox CLI Command Reference

Machine-generated command inventory for the `proxbox_cli` package.

!!! info "Generated"
    Last updated: `2026-04-01T19:39:49.416217+00:00`
    Command groups: `14`
    Leaf commands: `63`

| Command | Kind | Summary | Example |
|---------|------|---------|---------|
| `pxb` | `group` | Proxbox CLI — interact with the proxbox-api backend. | `pxb --help` |
| `pxb cache` | `command` | Show the in-memory cache contents. | `pxb cache` |
| `pxb clear-cache` | `command` | Clear the in-memory cache on the proxbox-api server. | `pxb clear-cache` |
| `pxb config` | `command` | Show the current CLI configuration. | `pxb config` |
| `pxb dcim` | `group` | DCIM (datacenter infrastructure) commands. | `pxb dcim --help` |
| `pxb dcim devices` | `command` | List devices. | `pxb dcim devices` |
| `pxb dcim devices-create` | `command` | Sync Proxmox nodes to NetBox devices. [NOTE: triggers a full node sync] | `pxb dcim devices-create` |
| `pxb dcim interfaces-create` | `command` | Create interfaces and IPs for a specific node device. | `pxb dcim interfaces-create <NODE>` |
| `pxb dcim interfaces-create-all` | `command` | Create interfaces for all node devices. | `pxb dcim interfaces-create-all` |
| `pxb docs` | `group` | Documentation generation commands. | `pxb docs --help` |
| `pxb docs generate-capture` | `command` | Generate machine-readable CLI docs artifacts for the MkDocs site. | `pxb docs generate-capture` |
| `pxb extras` | `group` | Extras commands (custom fields, etc.). | `pxb extras --help` |
| `pxb extras custom-fields-create` | `command` | Create predefined Proxbox custom fields in NetBox (proxmox_vm_id, start_at_boot, etc.). | `pxb extras custom-fields-create` |
| `pxb full-update` | `command` | Run a full sync: creates devices (nodes) then VMs. [NOTE: long-running operation] | `pxb full-update` |
| `pxb info` | `command` | Show proxbox-api project info. | `pxb info` |
| `pxb init` | `command` | Interactively configure the proxbox-api base URL. | `pxb init` |
| `pxb netbox` | `group` | NetBox integration commands. | `pxb netbox --help` |
| `pxb netbox endpoint` | `group` | NetBox endpoint CRUD. | `pxb netbox endpoint --help` |
| `pxb netbox endpoint create` | `command` | Create a NetBox endpoint record. | `pxb netbox endpoint create` |
| `pxb netbox endpoint delete` | `command` | Delete a NetBox endpoint record. | `pxb netbox endpoint delete <NETBOX-ID>` |
| `pxb netbox endpoint get` | `command` | Get a single NetBox endpoint by ID. | `pxb netbox endpoint get <NETBOX-ID>` |
| `pxb netbox endpoint list` | `command` | List NetBox endpoint records. | `pxb netbox endpoint list` |
| `pxb netbox endpoint update` | `command` | Update a NetBox endpoint record. | `pxb netbox endpoint update <NETBOX-ID>` |
| `pxb netbox openapi` | `command` | Fetch the NetBox OpenAPI schema. | `pxb netbox openapi` |
| `pxb netbox status` | `command` | Show NetBox API status. | `pxb netbox status` |
| `pxb proxbox` | `group` | Proxbox plugin and backend info commands. | `pxb proxbox --help` |
| `pxb proxbox default-settings` | `command` | Show Proxbox default settings from the NetBox plugin config. | `pxb proxbox default-settings` |
| `pxb proxbox plugins-config` | `command` | Show plugin configuration from NetBox PLUGINS_CONFIG. | `pxb proxbox plugins-config` |
| `pxb proxbox settings` | `command` | Show resolved Proxbox plugin configuration from NetBox. | `pxb proxbox settings` |
| `pxb proxmox` | `group` | Proxmox integration commands. | `pxb proxmox --help` |
| `pxb proxmox cluster` | `group` | Proxmox cluster commands. | `pxb proxmox cluster --help` |
| `pxb proxmox cluster resources` | `command` | Get cluster resources, optionally filtered by type. | `pxb proxmox cluster resources` |
| `pxb proxmox cluster status` | `command` | Get cluster status (name, nodes, quorate, mode). | `pxb proxmox cluster status` |
| `pxb proxmox endpoints` | `group` | Proxmox endpoint CRUD (local DB). | `pxb proxmox endpoints --help` |
| `pxb proxmox endpoints create` | `command` | Create a Proxmox endpoint record. | `pxb proxmox endpoints create` |
| `pxb proxmox endpoints delete` | `command` | Delete a Proxmox endpoint record. | `pxb proxmox endpoints delete <ENDPOINT-ID>` |
| `pxb proxmox endpoints get` | `command` | Get a single Proxmox endpoint by ID. | `pxb proxmox endpoints get <ENDPOINT-ID>` |
| `pxb proxmox endpoints list` | `command` | List Proxmox endpoint records. | `pxb proxmox endpoints list` |
| `pxb proxmox endpoints update` | `command` | Update a Proxmox endpoint record. | `pxb proxmox endpoints update <ENDPOINT-ID>` |
| `pxb proxmox nodes` | `group` | Proxmox node commands. | `pxb proxmox nodes --help` |
| `pxb proxmox nodes list` | `command` | Get node info (cpu, mem, status, fingerprint) from all sessions. | `pxb proxmox nodes list` |
| `pxb proxmox nodes lxc` | `command` | List LXC containers on a specific node. | `pxb proxmox nodes lxc <NODE>` |
| `pxb proxmox nodes network` | `command` | Get network interfaces for a node. | `pxb proxmox nodes network <NODE>` |
| `pxb proxmox nodes qemu` | `command` | List QEMU VMs on a specific node. | `pxb proxmox nodes qemu <NODE>` |
| `pxb proxmox overview` | `command` | Show Proxmox overview (access, cluster, nodes, pools, storage, version). | `pxb proxmox overview` |
| `pxb proxmox sessions` | `command` | List all active Proxmox sessions. | `pxb proxmox sessions` |
| `pxb proxmox storage` | `command` | Get storage info from all Proxmox sessions. | `pxb proxmox storage` |
| `pxb proxmox storage-content` | `command` | Get storage content (backups, images) for a node and storage. | `pxb proxmox storage-content <NODE> <STORAGE-ID>` |
| `pxb proxmox top-level` | `command` | Query a dynamic top-level Proxmox path. | `pxb proxmox top-level <PATH>` |
| `pxb proxmox version` | `command` | Get Proxmox version from all connected sessions. | `pxb proxmox version` |
| `pxb proxmox viewer` | `group` | Proxmox API codegen and viewer commands. | `pxb proxmox viewer --help` |
| `pxb proxmox viewer contracts` | `command` | Report Proxmox and NetBox schema contract diagnostics. | `pxb proxmox viewer contracts` |
| `pxb proxmox viewer generate` | `command` | Run the Proxmox API Viewer crawl and code generation pipeline. | `pxb proxmox viewer generate` |
| `pxb proxmox viewer openapi` | `command` | Return the generated Proxmox OpenAPI schema. | `pxb proxmox viewer openapi` |
| `pxb proxmox viewer openapi-embedded` | `command` | Return the Proxmox OpenAPI as embedded in the FastAPI custom schema. | `pxb proxmox viewer openapi-embedded` |
| `pxb proxmox viewer pydantic` | `command` | Print the generated Pydantic v2 model source code. | `pxb proxmox viewer pydantic` |
| `pxb proxmox vm-config` | `command` | Get VM config for a specific VM. | `pxb proxmox vm-config <NODE> <VM-TYPE> <VMID>` |
| `pxb test` | `command` | Test connectivity to the proxbox-api server. | `pxb test` |
| `pxb version` | `command` | Show the proxbox-api backend version. | `pxb version` |
| `pxb virtualization` | `group` | Virtualization commands. | `pxb virtualization --help` |
| `pxb virtualization cluster-types-create` | `command` | Create cluster types in NetBox. | `pxb virtualization cluster-types-create` |
| `pxb virtualization clusters-create` | `command` | Create clusters in NetBox. | `pxb virtualization clusters-create` |
| `pxb virtualization storage-create` | `command` | Sync Proxmox storage definitions into NetBox. [NOTE: triggers sync] | `pxb virtualization storage-create` |
| `pxb virtualization vms` | `group` | Virtual machine commands. | `pxb virtualization vms --help` |
| `pxb virtualization vms backups-create` | `command` | Create backups for a specific node/storage. [NOTE: triggers sync] | `pxb virtualization vms backups-create` |
| `pxb virtualization vms backups-sync-all` | `command` | Sync ALL backups across all clusters/nodes/storages. [NOTE: long-running sync] | `pxb virtualization vms backups-sync-all` |
| `pxb virtualization vms create` | `command` | Sync VMs from Proxmox to NetBox (creates VMs, interfaces, IPs). [NOTE: triggers full sync] | `pxb virtualization vms create` |
| `pxb virtualization vms create-test` | `command` | Create a hardcoded test VM in NetBox. | `pxb virtualization vms create-test` |
| `pxb virtualization vms disks-create` | `command` | Create virtual disks for VMs in NetBox. [NOTE: triggers sync] | `pxb virtualization vms disks-create` |
| `pxb virtualization vms get` | `command` | Get a single VM by ID. | `pxb virtualization vms get <VM-ID>` |
| `pxb virtualization vms interfaces-create` | `command` | Create VM interfaces in NetBox. [NOTE: triggers sync] | `pxb virtualization vms interfaces-create` |
| `pxb virtualization vms ip-address-create` | `command` | Create IP addresses for VM interfaces in NetBox. [NOTE: triggers sync] | `pxb virtualization vms ip-address-create` |
| `pxb virtualization vms list` | `command` | List all virtual machines from NetBox. | `pxb virtualization vms list` |
| `pxb virtualization vms snapshots-create` | `command` | Sync VM snapshots for all VMs or a specific VM. [NOTE: triggers sync] | `pxb virtualization vms snapshots-create` |
| `pxb virtualization vms snapshots-sync-all` | `command` | Sync ALL VM snapshots across all clusters/nodes. [NOTE: long-running sync] | `pxb virtualization vms snapshots-sync-all` |
| `pxb virtualization vms summary` | `command` | Get summary for a specific VM by ID. | `pxb virtualization vms summary <VM-ID>` |
| `pxb virtualization vms summary-example` | `command` | Return an example VirtualMachineSummary response. | `pxb virtualization vms summary-example` |
