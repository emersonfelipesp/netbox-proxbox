# Plugin Certification Application Packet

This packet covers the Proxbox plugin family.

| Plugin | Repository | PyPI | Certification release |
| --- | --- | --- | --- |
| netbox-proxbox | <https://github.com/emersonfelipesp/netbox-proxbox> | <https://pypi.org/project/netbox-proxbox/> | 0.0.18.post1 |
| netbox-pbs | <https://github.com/emersonfelipesp/netbox-pbs> | <https://pypi.org/project/netbox-pbs/> | 0.0.1.post1 |
| netbox-pdm | <https://github.com/emersonfelipesp/netbox-pdm> | <https://pypi.org/project/netbox-pdm/> | 0.0.1.post1 |
| netbox-ceph | <https://github.com/emersonfelipesp/netbox-ceph> | <https://pypi.org/project/netbox-ceph/> | 0.0.1.post1 |
| netbox-packer | <https://github.com/emersonfelipesp/netbox-packer> | <https://pypi.org/project/netbox-packer/> | 0.0.2.post2 |

## Maintainer Access

The repositories remain under the `emersonfelipesp` GitHub account. NetBox
Labs staff can be invited as collaborators with the access level requested by
the certification process.

## Compatibility Target

The certification target is NetBox `v4.6.4`, with compatibility preserved for
NetBox `v4.5.8+` where each plugin declares `max_version = "4.6.99"`.

## Evidence

- Every package declares Apache-2.0 license metadata and includes a top-level
  `LICENSE` file.
- Every PyPI package exposes source, documentation, and issue tracker URLs.
- GitHub Actions validate package build, tests, docs, release publishing, and
  NetBox install smoke coverage.
- Screenshot capture workflows use `netboxcommunity/netbox:v4.6.4`.
- Support is handled through GitHub Issues, with family coordination tracked in
  <https://github.com/emersonfelipesp/netbox-proxbox/issues/499>.
