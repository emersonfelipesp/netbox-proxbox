- [x] Inspect existing CI and plugin/backend integration constraints.
- [x] Design containerized GitHub Actions e2e topology with mocked Proxmox service.
- [x] Implement Proxmox mock API server for required proxbox-api routes.
- [x] Implement end-to-end stack validation script covering endpoint setup, sync trigger, and route checks.
- [x] Add scheduled + manual GitHub Actions workflow that boots stack and runs e2e checks.
- [x] Document e2e architecture and workflow with Mermaid diagrams.
- [x] Extend e2e to validate update behavior by mutating mocked VM status and asserting NetBox status transition.

## Review

- Added a dedicated workflow to validate real NetBox plugin routes and proxbox-api routes against a mocked Proxmox upstream.
- The test path configures all three plugin endpoints (Proxmox, NetBox, FastAPI), triggers full-update sync, waits for NetBox Job completion, and verifies synced plugin API data.
- On failures, workflow emits container logs for NetBox, worker, proxbox-api, mock Proxmox, Postgres, and Redis.
- Added docs page with architecture and sequence diagrams for the e2e stack and data flow.
- Added update-path validation: changing mocked Proxmox VM status now triggers a NetBox VM status transition assertion (`active` to `offline`) after re-sync.
