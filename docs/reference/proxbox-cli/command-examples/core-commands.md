# Core Commands

Representative command help output captured automatically from the local checkout.

Generated: `2026-11-17T14:30:50.842882+00:00`

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
│ dcim            DCIM (datacenter infrastructure) commands.                   │
│ virtualization  Virtualization commands.                                     │
│ sync            Run Proxbox sync jobs from the CLI.                          │
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
│ --keep-api-key          Keep the stored API key when changing the backend    │
│                         origin.                                              │
│ --help                  Show this message and exit.                          │
╰──────────────────────────────────────────────────────────────────────────────╯

```

## Docs Generate Capture Help

Command: `pxb docs generate-capture --help`

Regenerates the machine-generated CLI reference artifacts used by MkDocs.

```text

 Usage: python -m proxbox_cli docs generate-capture [OPTIONS]

 Generate machine-readable CLI docs artifacts for the MkDocs site.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --output                <str>  Markdown snapshot output path.                │
│ --raw-dir               <str>  Raw JSON artifact directory.                  │
│ --catalog-output        <str>  Command catalog JSON output path.             │
│ --help                         Show this message and exit.                   │
╰──────────────────────────────────────────────────────────────────────────────╯

```
