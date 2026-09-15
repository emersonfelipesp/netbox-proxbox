# Proxmox Commands

Representative command help output captured automatically from the local checkout.

Generated: `2026-09-14T17:13:11.556323+00:00`

## Proxmox Help

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

## Proxmox Viewer Generate Help

Command: `pxb proxmox viewer generate --help`

Code-generation pipeline entrypoint for the proxmox viewer endpoints.

```text

 Usage: python -m proxbox_cli proxmox viewer generate [OPTIONS]

 Run the Proxmox API Viewer crawl and code generation pipeline.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --body-json        <str>   JSON config string.                               │
│ --body-file        <path>  Path to JSON config file.                         │
│ --json                     Output raw JSON.                                  │
│ --yaml                     Output YAML.                                      │
│ --help                     Show this message and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯

```

## Proxmox Storage Content Help

Command: `pxb proxmox storage-content --help`

Example of a command with required arguments and optional filters.

```text

 Usage: python -m proxbox_cli proxmox storage-content [OPTIONS] {node}
                                                      {storage_id}

 Get storage content (backups, images) for a node and storage.

╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│ *    node            <str>  Node name. [required]                            │
│ *    storage_id      <str>  Storage ID. [required]                           │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --vmid           <str>  Filter by VM ID.                                     │
│ --content        <str>  Filter by content type.                              │
│ --json                  Output raw JSON.                                     │
│ --yaml                  Output YAML.                                         │
│ --help                  Show this message and exit.                          │
╰──────────────────────────────────────────────────────────────────────────────╯

```

## Proxmox Nodes LXC Help

Command: `pxb proxmox nodes lxc --help`

LXC container listing on a specific node.

```text

 Usage: python -m proxbox_cli proxmox nodes lxc [OPTIONS] {node}

 List LXC containers on a specific node.

╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│ *    node      <str>  Node name. [required]                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --json          Output raw JSON.                                             │
│ --yaml          Output YAML.                                                 │
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯

```
