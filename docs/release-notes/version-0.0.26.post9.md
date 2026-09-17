# Version 0.0.26.post9

## Release-validation page-coverage gate aligned with its backend

The public release validation workflow runs a page-coverage gate that drives a
full Proxmox synchronization through a pinned PyPI backend (proxbox-api
0.0.18.post5). That backend is certified through NetBox 4.6.6, but the gate had
moved to the NetBox 4.7.0 image, so every virtual-machine creation failed and
the gate blocked publication. The gate now runs the NetBox 4.6.6 image pinned by digest, the last green
baseline for this backend; NetBox 4.7.0 GA certification continues to be
carried by the Django compatibility matrix and the end-to-end matrix.

No plugin runtime changes. This release exists so the 0.0.26 line can be
published publicly.

## Compatibility

Identical runtime to 0.0.26.post8.

Current backend-runtime pairing: netbox-proxbox 0.0.26.post9 <-> proxbox-api 0.0.21.post7 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.26.post9 | v0.0.21.post7 | v0.0.10 | v0.0.13 |
