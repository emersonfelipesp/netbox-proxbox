# NetBox Plugin Certification Evidence

This checklist tracks readiness for the NetBox Plugin Certification Program.

| Requirement | Evidence |
| --- | --- |
| Open source license | Apache-2.0 in `LICENSE` and `pyproject.toml` |
| Package metadata | PyPI project `netbox-proxbox`, project URLs, classifiers, Python `>=3.12` |
| NetBox compatibility | Plugin config declares `min_version = "4.5.8"` and `max_version = "4.6.99"` |
| Dependency policy | `proxbox-api` is deployed separately; the plugin communicates with it over REST, SSE, and WebSocket |
| CI | GitHub Actions run lint, typecheck, compile, pytest, E2E Docker, page coverage, screenshots, docs, and release validation |
| Documentation | README, MkDocs site, installation, backend setup, configuration, user guide, API, release notes, and support links |
| Screenshots | Committed screenshots live in `docs/assets/screenshots`; `docs-screenshots.yml` refreshes them against NetBox v4.6.4 |
| Icon | NetBox menu uses Material Design Icons class `mdi mdi-dns` |
| Maintainer access | Repositories stay under `emersonfelipesp`; NetBox Labs staff can be invited as collaborators when requested |

## Application Summary

- Repository: <https://github.com/emersonfelipesp/netbox-proxbox>
- Documentation: <https://emersonfelipesp.github.io/netbox-proxbox/>
- PyPI: <https://pypi.org/project/netbox-proxbox/>
- Support: <https://github.com/emersonfelipesp/netbox-proxbox/issues>
- Certification target release: `0.0.18.post1`
- Verified NetBox targets: `v4.5.8`, `v4.5.9`, `v4.6.0`, `v4.6.1`, `v4.6.2`, `v4.6.3`, and `v4.6.4`
- Family tracking issue: <https://github.com/emersonfelipesp/netbox-proxbox/issues/499>
