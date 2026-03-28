# Backend Overview

Proxbox uses a separate FastAPI service as its backend. The NetBox plugin does not talk to Proxmox directly.

## How It Works

The backend:

- connects to Proxmox
- connects back to NetBox
- exposes HTTP endpoints used by the plugin
- can optionally provide WebSocket updates for sync progress

The NetBox plugin stores and manages endpoint records, then triggers sync requests against the backend.

## Architecture

![Proxbox Architecture Image](./proxbox-architecture.png)
