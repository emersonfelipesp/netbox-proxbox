# Certification

`netbox-proxbox` is prepared for the NetBox Plugin Certification Program as
the main Proxbox plugin for Proxmox inventory synchronization.

| Requirement | Evidence |
| --- | --- |
| License | Apache-2.0 in the repository and package metadata |
| Package | Published as `netbox-proxbox` on PyPI with source, docs, and issues URLs |
| Compatibility | NetBox `4.5.8` through `4.7.0`, including official `v4.7.0` GA; verified against `v4.5.8`, `v4.5.9`, `v4.5.10`, `v4.6.0`, `v4.6.1`, `v4.6.2`, `v4.6.3`, `v4.6.4`, `v4.6.5`, `v4.6.6`, and `v4.7.0` (v4.7.0: plugin/Django compatibility only) |
| Tests | GitHub Actions run lint, typecheck, compile, pytest, E2E Docker, page coverage, screenshots, docs, and release validation. Limitation: end-to-end PVE synchronization on NetBox 4.7.0 through the published backend this line pairs with (proxbox-api 0.0.19.post5 through 0.0.21.post7) is known-broken and excluded from the release-validation matrix; the NetBox 4.7.0 entry covers plugin/Django compatibility only. |
| Docs | README plus MkDocs installation, backend, configuration, feature, API, operation, developer, and release-note pages |
| Screenshots | `docs/assets/screenshots` contains UI screenshots and `docs-screenshots.yml` refreshes them on demand |
| Support | GitHub Issues and community links in `emersonfelipesp/netbox-proxbox` |

The family-level certification application packet is available at
[Application Packet](application-packet.md).
