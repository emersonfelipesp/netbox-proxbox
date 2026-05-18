# Version 0.0.17 (split out)

Starting with the `v0.0.16` line, the previously co-developed sibling plugins
have been **extracted from this monorepo** into independent repositories under
[@emersonfelipesp](https://github.com/emersonfelipesp). The `0.0.17` release
line is no longer produced from this repository.

## New repository layout

| Repository | Plugin module | Depends on |
|---|---|---|
| [`emersonfelipesp/netbox-proxbox`](https://github.com/emersonfelipesp/netbox-proxbox) | `netbox_proxbox` (base) | NetBox |
| [`emersonfelipesp/netbox-pbs`](https://github.com/emersonfelipesp/netbox-pbs) | `netbox_pbs` (Proxmox Backup Server) | `netbox-proxbox>=0.0.16` |
| [`emersonfelipesp/netbox-pdm`](https://github.com/emersonfelipesp/netbox-pdm) | `netbox_pdm` (Proxmox Datacenter Manager) | `netbox-proxbox>=0.0.16` |
| [`emersonfelipesp/netbox-ceph`](https://github.com/emersonfelipesp/netbox-ceph) | `netbox_ceph` (Proxmox-managed Ceph) | `netbox-proxbox>=0.0.16` |
| [`emersonfelipesp/netbox-packer`](https://github.com/emersonfelipesp/netbox-packer) | `netbox_packer` (HashiCorp Packer image factory) | `netbox-proxbox>=0.0.16` |

All five plugins continue to talk to the same shared `proxbox-api` backend.
Each sibling repository ships its own documentation site (Material for
MkDocs), CI test suite, E2E workflow, and PyPI release pipeline. Install only
the plugins you need — the sibling plugins are optional, and `netbox-proxbox`
does **not** depend on any of them.

## What changed in this repository

- Removed `netbox_pbs/`, `netbox_ceph/`, and `netbox_packer/` source trees.
- Removed `tests/test_ceph_*.py` and `tests/test_packer_*.py`.
- Removed `docs/features/ceph.md` and `docs/installation/ceph-plugin.md`.
- Removed Ceph and PBS entries from the docs navigation.
- Reverted `tests/netbox_test_configuration.py` to load only `netbox_proxbox`.
- Updated CI to compile only `netbox_proxbox tests`.

The `netbox_packer` image-factory code (PRs #457, #458, #459, #460, #461,
#462) was carried over to the standalone
[`emersonfelipesp/netbox-packer`](https://github.com/emersonfelipesp/netbox-packer)
repository before this commit removed it from the monorepo, so the work is
preserved in the new repository's `main` branch and remains available in this
branch's git history.

## Migration notes for operators

If you previously installed in-tree sibling plugins:

1. Uninstall the in-tree wheels (`pip uninstall netbox-pbs netbox-ceph
   netbox-pdm netbox-packer`).
2. Install the standalone wheels from PyPI once each sibling repository
   publishes its first release, or from source against the standalone
   repository.
3. Keep your `PLUGINS` list in NetBox's `configuration.py` — the Python
   module names (`netbox_pbs`, `netbox_ceph`, `netbox_pdm`, `netbox_packer`)
   are unchanged.

Backend (`proxbox-api`) configuration is unchanged: every plugin still
authenticates against the same `FastAPIEndpoint` row in `netbox-proxbox` and
uses the same `/ceph/*`, `/pbs/*`, `/packer/*`, and related routes.
