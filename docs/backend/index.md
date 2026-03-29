# Backend Overview

Proxbox uses a separate FastAPI service as its backend. The NetBox plugin does not talk to Proxmox directly.

## How It Works

The backend:

- connects to Proxmox
- connects back to NetBox
- exposes HTTP endpoints used by the plugin
- supports SSE streaming (`text/event-stream`) for real-time per-object sync progress
- can optionally provide WebSocket updates for sync progress

The NetBox plugin stores and manages endpoint records, then triggers sync requests against the backend. Sync can run in two modes:

- **POST polling**: traditional request/response that waits for completion.
- **GET SSE stream**: the plugin proxies the backend's streaming response to the browser, rendering granular progress (e.g., `Processing device pve01`, `Synced virtual_machine vm101`) in real time.

## Architecture

![Proxbox Architecture Image](./proxbox-architecture.png)
