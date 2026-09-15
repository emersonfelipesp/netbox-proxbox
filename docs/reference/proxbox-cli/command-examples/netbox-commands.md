# NetBox Commands

Representative command help output captured automatically from the local checkout.

Generated: `2026-09-14T17:13:11.556323+00:00`

## NetBox Help

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

## NetBox Endpoint Create Help

Command: `pxb netbox endpoint create --help`

Payload-driven endpoint creation command.

```text

 Usage: python -m proxbox_cli netbox endpoint create [OPTIONS]

 Create a NetBox endpoint record.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --body-json        <str>   JSON payload string.                              │
│ --body-file        <path>  Path to JSON payload file.                        │
│ --json                     Output raw JSON.                                  │
│ --yaml                     Output YAML.                                      │
│ --help                     Show this message and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯

```
