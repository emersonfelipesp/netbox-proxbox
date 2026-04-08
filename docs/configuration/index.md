# Proxbox Configuration

Configuration in current Proxbox releases is split across three endpoint models plus one plugin settings object inside NetBox.

## Required Endpoint Objects

Create these objects under **Plugins > Proxbox** before running a sync:

1. **Proxmox API**: the Proxmox cluster or node you want to discover.
2. **NetBox API**: the NetBox API credentials the backend will use.
3. **ProxBox API (FastAPI)**: the separate `proxbox-api` backend service.

## Plugin Settings

The plugin exposes a singleton-style **Proxbox plugin settings** object for runtime behavior, organized into three groups:

- **Core behavior** — guest-agent interface naming, Proxmox fetch concurrency, IPv6 link-local filtering.
- **NetBox integration** — concurrency limits, retry policy, GET cache TTL, bulk-batch tuning, and VM sync parallelism.
- **SSRF protection** — enable/disable endpoint IP validation, private IP allowances, and explicit CIDR block/allow lists.

See [Plugin Settings](./plugin-settings.md) for the full field reference.

## Next Steps

- Review [Required Parameters](./required-parameters.md) before creating endpoint records.
- Configure [Plugin Settings](./plugin-settings.md) to tune sync performance and security.
- Use [Scheduled Sync](../features/scheduled-sync.md) when you want recurring background jobs instead of manual syncs.
