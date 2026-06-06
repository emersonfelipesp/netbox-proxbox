# Version 0.0.20

netbox-proxbox `0.0.20` pairs with the `proxbox-api 0.0.17` backend release and
the `proxmox-sdk 0.0.11` Proxmox SDK. NetBox compatibility is unchanged:
`4.5.8` through `4.6.99` (validated against `4.5.8`, `4.5.9`, `4.6.0`, and the
official `4.6.1`).

## Highlights

- **IP-address ownership safety (backend).** The paired `proxbox-api 0.0.17`
  release completes the fix that stops VM-interface IP sync from matching
  (stealing) an address that already belongs to a different server's
  interface, across every sync path (bulk, individual, and node).
- **Interface-batch settings persistence (plugin).** `interface_batch_size`
  and `interface_batch_delay_ms` entered on the plugin Settings page now
  persist to the database (they were previously silently dropped on save).
- **Repository hygiene.** Removed a stray committed git-worktree gitlink and
  added `.claude/` / `.worktrees/` to `.gitignore`.

## Compatibility

| NetBox  | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.20 | v0.0.17 | v0.0.8.post1 | v0.0.11 |
| >=4.5.8 | v0.0.19 | v0.0.16 | v0.0.8.post1 | v0.0.9 |

`proxbox-api` is not a Python dependency of this plugin; the services
communicate over HTTP/SSE/WebSocket. Install the matching `proxbox-api 0.0.17`
backend separately.
