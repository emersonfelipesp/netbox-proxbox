# Infrastructure Commands

Representative command help output captured automatically from the local checkout.

Generated: `2026-04-01T15:39:42.389783+00:00`

## DCIM Help

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

## Virtualization Help

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

## Virtualization Backups Sync Help

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

## Extras Help

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
