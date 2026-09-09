# NetBox Plugin Certification Evidence

This checklist tracks readiness for the NetBox Plugin Certification Program.

| Requirement | Evidence |
| --- | --- |
| Open source license | Apache-2.0 in `LICENSE` and `pyproject.toml` |
| Package metadata | PyPI project `netbox-proxbox`, project URLs, classifiers, Python `>=3.12` |
| NetBox compatibility | Plugin config supports backward-compatible `4.5.8` through `4.7.0`, including official `v4.7.0` GA |
| Dependency policy | `proxbox-api` is deployed separately; the plugin communicates with it over REST, SSE, and WebSocket |
| CI | GitHub Actions run lint, typecheck, compile, pytest, E2E Docker, page coverage, screenshots, docs, and release validation |
| Documentation | README, MkDocs site, installation, backend setup, configuration, user guide, API, release notes, and support links |
| Screenshots | Committed screenshots live in `docs/assets/screenshots`; `docs-screenshots.yml` refreshes them against NetBox v4.7.0 |
| Icon | NetBox menu uses Material Design Icons class `mdi mdi-dns` |
| Maintainer access | Repositories stay under `emersonfelipesp`; NetBox Labs staff can be invited as collaborators when requested |

## Application Summary

- Repository: <https://github.com/emersonfelipesp/netbox-proxbox>
- Documentation: <https://emersonfelipesp.github.io/netbox-proxbox/>
- PyPI: <https://pypi.org/project/netbox-proxbox/>
- Support: <https://github.com/emersonfelipesp/netbox-proxbox/issues>
- Certification target artifact: `0.0.26.post2` (local source)
- Verified stable NetBox targets: `v4.5.8`, `v4.5.9`, `v4.5.10`, `v4.6.0`, `v4.6.1`, `v4.6.2`, `v4.6.3`, `v4.6.4`, `v4.6.5`, and `v4.6.6`
- Verified GA target: `v4.7.0` at `5f06007e4c9bacc93ce17c1e645fc1143d60df3d`
- Source evidence: checkout commit plus release metadata verification, upstream requirements checksums, and reviewed Python 3.12/Linux artifact-hash locks
- Family tracking issue: <https://github.com/emersonfelipesp/netbox-proxbox/issues/499>
