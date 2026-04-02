# Other Data Models

The plugin's main plugin-specific models are:

- `ProxmoxEndpoint`: Proxmox cluster or node credentials and connectivity settings
- `NetBoxEndpoint`: target NetBox API endpoint and token configuration
- `FastAPIEndpoint`: `proxbox-api` backend connectivity settings
- `ProxmoxStorage`: synchronized storage rows linked to NetBox clusters and virtual disks
- `VMBackup`: backup metadata for synchronized virtual machines
- `VMSnapshot`: snapshot metadata for synchronized virtual machines
- `VMTaskHistory`: archived Proxmox task history linked to virtual machines
- `ProxboxPluginSettings`: singleton-style plugin behavior toggles

These models are exposed through the plugin UI and plugin REST API using standard NetBox model views and viewsets.
