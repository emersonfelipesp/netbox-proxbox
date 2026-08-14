# Version 0.0.24

netbox-proxbox `0.0.24` pairs with `proxbox-api 0.0.20`,
`proxmox-sdk 0.0.13`, and the backend's REST dependency
`netbox-sdk 0.0.10`. The plugin supports NetBox `4.5.8` through `4.6.99` and
is validated against `4.5.8` through `4.5.10` plus `4.6.0` through `4.6.6`.

Current backend-runtime pairing: netbox-proxbox 0.0.24 <-> proxbox-api 0.0.20 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| >=4.5.8 | v0.0.24 | v0.0.20 | v0.0.10 | v0.0.13 |

## Compatibility and correctness

- Certifies NetBox `4.6.6`, including the PDM registry override required by its
  current plugin loading contract.
- Preserves serializer source identity and corrects storage-node capacity,
  detail-template, InfluxDB, and sync-state behavior against real Django/NetBox
  models.
- Treats an empty configured encryption key as uninitialized and safely creates
  the key when a primary endpoint secret is first stored.

## Release integrity

- Builds one wheel and one sdist in an untrusted job and binds them to a
  canonical, repository-linked Gitea release manifest.
- Uses checksum-pinned uv with fresh per-run tool and managed-Python roots. A
  data-only wheel/sdist/manifest/canonical-request handoff carries no package or
  mirror credential. The separately administered control plane verifies the
  pinned workflow, exact first-attempt run, request, manifest, and artifact
  bytes on an isolated builder before sealing them for its isolated publisher.
  Only fixed digest-locked publisher tooling can read publication credentials.
- Requires authenticated Gitea CI run, run-attempt, and job evidence for the
  exact canonical `develop` commit before accepting a tag.
- Reuses the exact Gitea bytes for TestPyPI and PyPI; uploads never use
  `--skip-existing`, so failures always advance to a new immutable version.
- Promotes a final tag to the authorized GitHub repository only from canonical
  `main`, after exact package and host-issued production deployment evidence
  are verified.

## Upgrade

Deploy `proxbox-api 0.0.20` first, then install `netbox-proxbox 0.0.24`, run
the normal NetBox migration and static-collection steps, restart NetBox and its
workers, and verify the Proxbox plugin API and synchronization health.
