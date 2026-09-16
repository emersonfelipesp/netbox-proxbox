# Version 0.0.26.post8

## Public release validation lane restored

The GitHub release validation workflow runs an end-to-end Docker matrix and a
page-coverage gate before anything is published to PyPI. Both create the mock
Proxmox endpoint through the plugin API, and since 0.0.26 that request resolved
to OpenBao credential storage, which the validation stack does not provide. The
endpoint create failed closed and no 0.0.26 build reached PyPI.

The plugin settings singleton predates the credential-storage column, so it
kept that migration's `openbao` default. The validation harness now pins the
plugin setting to `legacy_encrypted` before it creates any endpoint. Explicit
selections never fall back to OpenBao, so the gates run without
`netbox-openbao`. The plugin's
write-mode OpenBao rule and every runtime behaviour are unchanged; this release
exists so the 0.0.26 line can be published publicly.

Continuous integration on Gitea now also runs for `release-*` branches, which
carry post-release repairs for an already-superseded integration line.

## Compatibility

Identical runtime to 0.0.26.post7.

Current backend-runtime pairing: netbox-proxbox 0.0.26.post8 <-> proxbox-api 0.0.21.post7 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.26.post8 | v0.0.21.post7 | v0.0.10 | v0.0.13 |
