# Proxbox Configuration

Configuration in current Proxbox releases is split across three endpoint models plus one plugin settings object inside NetBox.

## Required Endpoint Objects

Create these objects under **Plugins > Proxbox** before running a sync:

1. **Proxmox API**: the Proxmox cluster or node you want to discover.
2. **NetBox API**: the NetBox API credentials the backend will use.
3. **ProxBox API (FastAPI)**: the separate `proxbox-api` backend service.

## Plugin Settings

The plugin also exposes a singleton-style **Proxbox plugin settings** object for runtime behavior:

- **Use guest agent interface name**: prefer guest-agent interface names such as `ens18` instead of generic `net0`.
- **Proxmox fetch max concurrency**: cap parallel fetch operations per sync stage.

## Next Steps

- Review [Required Parameters](./required-parameters.md) before creating endpoint records.
- Use [Scheduled Sync](../features/scheduled-sync.md) when you want recurring background jobs instead of manual syncs.
