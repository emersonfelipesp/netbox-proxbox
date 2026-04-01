# API Integration

Proxbox exposes two API layers:

- The NetBox plugin API for Proxbox models inside NetBox
- The separate `proxbox-api` backend that performs Proxmox discovery and sync orchestration

## Current Flow

1. The NetBox plugin stores endpoint records.
2. A UI action or scheduled job triggers a Proxbox sync.
3. The plugin calls `proxbox-api`, usually through SSE-backed job execution.
4. The backend talks to Proxmox and NetBox APIs, then streams progress back.

The plugin is primarily an integration and synchronization layer, not a replacement control plane for Proxmox.
