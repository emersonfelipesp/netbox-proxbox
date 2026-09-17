# Version 0.0.26.post10

## Release-validation end-to-end matrix scoped to its backend

The public release validation workflow runs an end-to-end Docker matrix that
installs a published backend (proxbox-api from PyPI, TestPyPI, or Docker Hub).
That backend is certified through NetBox 4.6.6: on the NetBox 4.7.0 image its
PVE synchronization fails at NetBox object creation while the PBS and PDM
services pass, so the two PVE cells on 4.7.0 blocked publication on every
attempt.

Those two cells are now excluded only in the published-backend dependency
modes. Runs that build the backend from source (pull requests, scheduled runs,
and manual dev-backend runs) keep every NetBox 4.7.0 cell, and the 4.7.0 PBS
and PDM cells stay in the release lane.

End-to-end PVE synchronization on NetBox 4.7.0 with the published backend this
line pairs with is known-broken (observed failures in NetBox object creation)
and is not validated by this release. The Django compatibility matrix still
runs the plugin's own test suite on NetBox 4.7.0; it does not exercise the
backend-to-NetBox synchronization path. The NetBox 4.7.0 certification entry
therefore covers plugin/Django compatibility only; operators on NetBox 4.7.0
should treat PVE synchronization through proxbox-api 0.0.19.post5 through
0.0.21.post7 as known-broken.

No plugin runtime changes. This release exists so the 0.0.26 line can be
published publicly.

Limitation: end-to-end PVE synchronization on NetBox 4.7.0 through the published backend this line pairs with (proxbox-api 0.0.19.post5 through 0.0.21.post7) is known-broken and excluded from the release-validation matrix; the NetBox 4.7.0 entry covers plugin/Django compatibility only.

## Compatibility

Identical runtime to 0.0.26.post9.

Current backend-runtime pairing: netbox-proxbox 0.0.26.post10 <-> proxbox-api 0.0.21.post7 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.26.post10 | v0.0.21.post7 | v0.0.10 | v0.0.13 |
