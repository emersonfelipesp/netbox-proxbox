# Core Commands

Representative command help output captured automatically from the local checkout.

Generated: `2026-04-01T19:39:49.416217+00:00`

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
│ version         Show the proxbox-api backend version.                        │
│ info            Show proxbox-api project info.                               │
│ cache           Show the in-memory cache contents.                           │
│ clear-cache     Clear the in-memory cache on the proxbox-api server.         │
│ full-update     Run a full sync: creates devices (nodes) then VMs. [NOTE:    │
│                 long-running operation]                                      │
│ netbox          NetBox integration commands.                                 │
│ proxmox         Proxmox integration commands.                                │
│ proxbox         Proxbox plugin and backend info commands.                    │
│ dcim            DCIM (datacenter infrastructure) commands.                   │
│ virtualization  Virtualization commands.                                     │
│ extras          Extras commands (custom fields, etc.).                       │
│ docs            Documentation generation commands.                           │
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

## Extras Help

Command: `pxb extras --help`

Shows extras-related CLI commands (custom fields, etc.).

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

## Proxbox Help

Command: `pxb proxbox --help`

Plugin configuration and backend info commands.

```text
                                                                                
 Usage: python -m proxbox_cli proxbox [OPTIONS] COMMAND [ARGS]...               
                                                                                
 Proxbox plugin and backend info commands.                                      
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ settings          Show resolved Proxbox plugin configuration from NetBox.    │
│ plugins-config    Show plugin configuration from NetBox PLUGINS_CONFIG.      │
│ default-settings  Show Proxbox default settings from the NetBox plugin       │
│                   config.                                                    │
╰──────────────────────────────────────────────────────────────────────────────╯
```
