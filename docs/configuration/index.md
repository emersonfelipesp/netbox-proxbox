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
- **NetBox integration** — concurrency limits, retry policy, GET cache TTL, bulk-batch tuning, VM sync parallelism, and VM reconciliation-engine selection.
- **SSRF protection** — enable/disable endpoint IP validation, private IP allowances, and explicit CIDR block/allow lists.

See [Plugin Settings](./plugin-settings.md) for the full field reference.

## Sync Overwrite Flags

Every `overwrite_*` toggle (device fields, VM fields, tags, primary IP, status) is now configurable both globally on the plugin settings object and per-endpoint on the **Settings** tab of each `ProxmoxEndpoint`. Per-endpoint values use tri-state semantics: **Use plugin default**, **Always overwrite**, or **Never overwrite**.

See [Sync Overwrite Flags](./sync-overwrite-flags.md) for the full flag matrix and merge-vs-replace semantics.

## Next Steps

- Review [Required Parameters](./required-parameters.md) before creating endpoint records.
- Configure [Plugin Settings](./plugin-settings.md) to tune sync performance and security.
- Pin [Sync Overwrite Flags](./sync-overwrite-flags.md) globally or per-endpoint to control which Proxmox fields can replace existing NetBox values.
- Use [Scheduled Sync](../features/scheduled-sync.md) when you want recurring background jobs instead of manual syncs.
