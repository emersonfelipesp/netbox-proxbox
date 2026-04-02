# Network (IPAM)

Proxbox can populate interface and IP data discovered from Proxmox guests and nodes into NetBox.

## Current Scope

- Node interface creation is available from the CLI and sync workflows.
- VM interface and IP address synchronization are part of the virtualization sync toolchain.
- Interface naming can prefer guest-agent names when enabled in **Proxbox plugin settings**.

## Notes

Network synchronization is designed to enrich NetBox inventory from Proxmox discovery. It is not a full bidirectional IPAM controller for Proxmox.
