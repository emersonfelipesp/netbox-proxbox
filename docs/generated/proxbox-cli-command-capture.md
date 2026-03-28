# proxbox_cli command capture

This file is machine-generated. Regenerate it with:

```bash
cd /path/to/netbox-proxbox
python docs/generate_proxbox_cli_docs.py
# or: pxb docs generate-capture
```

## Metadata

- Generated at: `2026-03-28T14:49:37.241515+00:00`
- Python: `3.13.3`
- Platform: `Linux-6.8.12-4-pve-x86_64-with-glibc2.41`

## Core Commands

### Root Help

Command: `pxb --help`

Top-level entrypoint and root command groups.

```text
                                                                                
 Usage: python -m proxbox_cli [OPTIONS] COMMAND [ARGS]...                       
                                                                                
 Proxbox CLI — interact with the proxbox-api backend.                           
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ init            Interactively configure the proxbox-api base URL.            │
│ config          Show the current CLI configuration.                          │
│ test            Test connectivity to the proxbox-api server.                 │
│ info            Show proxbox-api project info.                               │
│ cache           Show the in-memory cache contents.                           │
│ clear-cache     Clear the in-memory cache on the proxbox-api server.         │
│ full-update     Run a full sync: creates devices (nodes) then VMs. [NOTE:    │
│                 long-running operation]                                      │
│ netbox          NetBox integration commands.                                 │
│ proxmox         Proxmox integration commands.                                │
│ dcim            DCIM (datacenter infrastructure) commands.                   │
│ virtualization  Virtualization commands.                                     │
│ extras          Extras commands (custom fields, etc.).                       │
│ docs            Documentation generation commands.                           │
│ sync-processes  Sync process commands.                                       │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Init Help

Command: `pxb init --help`

Interactive configuration bootstrap for the proxbox-api base URL.

```text
                                                                                
 Usage: python -m proxbox_cli init [OPTIONS]                                    
                                                                                
 Interactively configure the proxbox-api base URL.                              
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Docs Generate Capture Help

Command: `pxb docs generate-capture --help`

Regenerates the machine-generated CLI reference artifacts used by MkDocs.

```text
                                                                                
 Usage: python -m proxbox_cli docs generate-capture [OPTIONS]                   
                                                                                
 Generate machine-readable CLI docs artifacts for the MkDocs site.              
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --output                TEXT  Markdown snapshot output path.                 │
│ --raw-dir               TEXT  Raw JSON artifact directory.                   │
│ --catalog-output        TEXT  Command catalog JSON output path.              │
│ --help                        Show this message and exit.                    │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Sync Processes Help

Command: `pxb sync-processes --help`

Shows the sync-process subcommands exposed by the backend.

```text
                                                                                
 Usage: python -m proxbox_cli sync-processes [OPTIONS] COMMAND [ARGS]...        
                                                                                
 Sync process commands.                                                         
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ list    List all sync processes from NetBox.                                 │
│ create  Create a new sync process record in NetBox.                          │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## NetBox Commands

### NetBox Help

Command: `pxb netbox --help`

NetBox status, OpenAPI, and endpoint CRUD commands.

```text
                                                                                
 Usage: python -m proxbox_cli netbox [OPTIONS] COMMAND [ARGS]...                
                                                                                
 NetBox integration commands.                                                   
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ status    Show NetBox API status.                                            │
│ openapi   Fetch the NetBox OpenAPI schema.                                   │
│ endpoint  NetBox endpoint CRUD.                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### NetBox Endpoint Create Help

Command: `pxb netbox endpoint create --help`

Payload-driven endpoint creation command.

```text
                                                                                
 Usage: python -m proxbox_cli netbox endpoint create [OPTIONS]                  
                                                                                
 Create a NetBox endpoint record.                                               
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --body-json        TEXT  JSON payload string.                                │
│ --body-file        PATH  Path to JSON payload file.                          │
│ --json                   Output raw JSON.                                    │
│ --yaml                   Output YAML.                                        │
│ --help                   Show this message and exit.                         │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## Proxmox Commands

### Proxmox Help

Command: `pxb proxmox --help`

Cluster, node, viewer, and endpoint commands.

```text
                                                                                
 Usage: python -m proxbox_cli proxmox [OPTIONS] COMMAND [ARGS]...               
                                                                                
 Proxmox integration commands.                                                  
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ overview         Show Proxmox overview (access, cluster, nodes, pools,       │
│                  storage, version).                                          │
│ sessions         List all active Proxmox sessions.                           │
│ version          Get Proxmox version from all connected sessions.            │
│ storage          Get storage info from all Proxmox sessions.                 │
│ storage-content  Get storage content (backups, images) for a node and        │
│                  storage.                                                    │
│ top-level        Query a dynamic top-level Proxmox path.                     │
│ vm-config        Get VM config for a specific VM.                            │
│ endpoints        Proxmox endpoint CRUD (local DB).                           │
│ viewer           Proxmox API codegen and viewer commands.                    │
│ cluster          Proxmox cluster commands.                                   │
│ nodes            Proxmox node commands.                                      │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Proxmox Viewer Generate Help

Command: `pxb proxmox viewer generate --help`

Code-generation pipeline entrypoint for the proxmox viewer endpoints.

```text
                                                                                
 Usage: python -m proxbox_cli proxmox viewer generate [OPTIONS]                 
                                                                                
 Run the Proxmox API Viewer crawl and code generation pipeline.                 
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --body-json        TEXT  JSON config string.                                 │
│ --body-file        PATH  Path to JSON config file.                           │
│ --json                   Output raw JSON.                                    │
│ --yaml                   Output YAML.                                        │
│ --help                   Show this message and exit.                         │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Proxmox Storage Content Help

Command: `pxb proxmox storage-content --help`

Example of a command with required arguments and optional filters.

```text
                                                                                
 Usage: python -m proxbox_cli proxmox storage-content [OPTIONS] NODE STORAGE_ID 
                                                                                
 Get storage content (backups, images) for a node and storage.                  
                                                                                
╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│ *    node            TEXT  Node name. [required]                             │
│ *    storage_id      TEXT  Storage ID. [required]                            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --vmid           TEXT  Filter by VM ID.                                      │
│ --content        TEXT  Filter by content type.                               │
│ --json                 Output raw JSON.                                      │
│ --yaml                 Output YAML.                                          │
│ --help                 Show this message and exit.                           │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## Infrastructure Commands

### DCIM Help

Command: `pxb dcim --help`

Node device and interface sync commands.

```text
                                                                                
 Usage: python -m proxbox_cli dcim [OPTIONS] COMMAND [ARGS]...                  
                                                                                
 DCIM (datacenter infrastructure) commands.                                     
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ devices                List devices.                                         │
│ devices-create         Sync Proxmox nodes to NetBox devices. [NOTE: triggers │
│                        a full node sync]                                     │
│ interfaces-create      Create interfaces and IPs for a specific node device. │
│ interfaces-create-all  Create interfaces for all node devices.               │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Virtualization Help

Command: `pxb virtualization --help`

Cluster and virtual-machine sync commands.

```text
                                                                                
 Usage: python -m proxbox_cli virtualization [OPTIONS] COMMAND [ARGS]...        
                                                                                
 Virtualization commands.                                                       
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ cluster-types-create  Create cluster types in NetBox.                        │
│ clusters-create       Create clusters in NetBox.                             │
│ vms                   Virtual machine commands.                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Virtualization Backups Sync Help

Command: `pxb virtualization vms backups-sync-all --help`

Long-running VM backup synchronization command.

```text
                                                                                
 Usage: python -m proxbox_cli virtualization vms backups-sync-all               
            [OPTIONS]                                                           
                                                                                
 Sync ALL backups across all clusters/nodes/storages. [NOTE: long-running sync] 
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --delete-stale          Delete stale backup records.                         │
│ --json                  Output raw JSON.                                     │
│ --yaml                  Output YAML.                                         │
│ --help                  Show this message and exit.                          │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Extras Help

Command: `pxb extras --help`

Custom-field initialization and related helper commands.

```text
                                                                                
 Usage: python -m proxbox_cli extras [OPTIONS] COMMAND [ARGS]...                
                                                                                
 Extras commands (custom fields, etc.).                                         
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ custom-fields-create  Create predefined Proxbox custom fields in NetBox      │
│                       (proxmox_vm_id, start_at_boot, etc.).                  │
╰──────────────────────────────────────────────────────────────────────────────╯
```
