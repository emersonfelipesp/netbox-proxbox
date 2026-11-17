# Proxmox Commands

Representative command help output captured automatically from the local checkout.

Generated: `2026-11-17T14:30:50.842882+00:00`

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

 Run viewer code generation; the backend must enable runtime code generation.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --persist             --no-persist                       Persist generated   │
│                                                          artifacts.          │
│                                                          [default: persist]  │
│ --workers                             <int range>        [default: 10]       │
│                                       [1<=x<=32]                             │
│ --retry-count                         <int range>        [default: 2]        │
│                                       [0<=x<=10]                             │
│ --retry-backoff                       <float range>      [default: 0.35]     │
│                                       [0.0<=x<=5.0]                          │
│ --checkpoint-every                    <int range>        [default: 50]       │
│                                       [1<=x<=500]                            │
│ --source-url                          <str>              Proxmox API viewer  │
│                                                          URL.                │
│                                                          [default:           │
│                                                          https://pve.proxmo… │
│ --version-tag                         <str>              Generated artifact  │
│                                                          version tag.        │
│                                                          [default: latest]   │
│ --json                                                   Output raw JSON.    │
│ --yaml                                                   Output YAML.        │
│ --help                                                   Show this message   │
│                                                          and exit.           │
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
