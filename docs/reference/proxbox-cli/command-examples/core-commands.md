# Core Commands

Representative command help output captured automatically from the local checkout.

Generated: `2026-03-28T14:49:37.241515+00:00`

## Root Help

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

## Init Help

Command: `pxb init --help`

Interactive configuration bootstrap for the proxbox-api base URL.

```text
                                                                                
 Usage: python -m proxbox_cli init [OPTIONS]                                    
                                                                                
 Interactively configure the proxbox-api base URL.                              
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## Docs Generate Capture Help

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

## Sync Processes Help

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
