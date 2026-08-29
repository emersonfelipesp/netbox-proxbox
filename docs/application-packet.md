# Plugin Certification Application Packet

This packet covers the Proxbox plugin family.

| Plugin | Repository | PyPI | Certification release |
| --- | --- | --- | --- |
| netbox-proxbox | <https://github.com/emersonfelipesp/netbox-proxbox> | <https://pypi.org/project/netbox-proxbox/> | 0.0.25 (local source) |
| netbox-pbs | <https://github.com/emersonfelipesp/netbox-pbs> | <https://pypi.org/project/netbox-pbs/> | 0.0.1.post1 |
| netbox-pdm | <https://github.com/emersonfelipesp/netbox-pdm> | <https://pypi.org/project/netbox-pdm/> | 0.0.1.post1 |
| netbox-ceph | <https://github.com/emersonfelipesp/netbox-ceph> | <https://pypi.org/project/netbox-ceph/> | 0.0.1.post1 |
| netbox-packer | <https://github.com/emersonfelipesp/netbox-packer> | <https://pypi.org/project/netbox-packer/> | 0.0.2.post2 |

## Maintainer Access

The repositories remain under the `emersonfelipesp` GitHub account. NetBox
Labs staff can be invited as collaborators with the access level requested by
the certification process.

## Compatibility Target

The certification matrix covers NetBox `v4.5.8` through `v4.5.10` and `v4.6.0`
through `v4.6.6` in the **stable** tier, plus `v4.7.0-beta2` at exact commit
`aa1d49d0f5021a28e6efc2d0364b84c5bcec7137` in the
**experimental** tier. `netbox-proxbox` declares `min_version = "4.5.8"` and
`max_version = "4.7.0"`, sourced from its vendored `compat.py`, then requires
canonical `release.yaml` identity `version: "4.7.0"` plus `designation:
"beta2"`. Other 4.7 identities are omitted fail-closed while NetBox continues
startup. Each source-matrix cell verifies the checked-out commit and NetBox
release metadata, checksums that commit's upstream requirements, and enforces a
reviewed Python 3.12/Linux dependency lock with artifact hashes.

**This statement is scoped to `netbox-proxbox` alone.** The companion plugins
(`netbox-ceph`, `netbox-packer`, `netbox-pbs`, `netbox-pdm`) carry the same
vendored `compat.py`, but only in releases published after this change; every
earlier companion artifact still declares `max_version = "4.6.99"`.
A companion left at the old ceiling does **not** fail the boot — `settings.py`
catches `IncompatiblePluginError`, warns, and **skips** that plugin, so NetBox
starts without it. That is the more dangerous outcome for a certification
reader: the symptom is an absence (missing views, REST routes, background jobs)
rather than an error, and a health probe against NetBox still returns 200. Do
not read this section as clearance to move a mixed installation to 4.7. Upgrade
every installed Proxbox-family plugin to a 4.7-capable release first, then
verify each is registered with `apps.is_installed()` rather than inferring it
from a successful start.

NetBox `v4.7.0-beta2` is additionally an **upstream pre-release**. Upstream
does not support pre-releases in production and does not guarantee an upgrade
path from a pre-release to the final release, so the experimental tier is
evaluation evidence on disposable data — not a production certification.

## Evidence

- Every package declares Apache-2.0 license metadata and includes a top-level
  `LICENSE` file.
- Every PyPI package exposes source, documentation, and issue tracker URLs.
- GitHub Actions validate package build, tests, docs, release publishing, and
  NetBox install smoke coverage.
- Screenshot capture workflows use `netboxcommunity/netbox:v4.6.6`.
- Support is handled through GitHub Issues, with family coordination tracked in
  <https://github.com/emersonfelipesp/netbox-proxbox/issues/499>.
