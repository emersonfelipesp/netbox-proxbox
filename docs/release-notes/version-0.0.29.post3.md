# Version 0.0.29.post3

## Summary

This maintenance release admits every NetBox 4.7 patch release and corrects how
the OCI testing appliance image selects the plugin version it installs. It adds
no database migration and changes no plugin runtime behavior.

## Release identity

The package and plugin source both identify this maintenance release as
`0.0.29.post3`.

## NetBox 4.7 patch releases

The plugin now declares NetBox `4.7.99` as its maximum version, so NetBox 4.7
patch releases such as `4.7.2` load without a plugin update. The certified
baseline is unchanged: continuous integration verifies NetBox `4.5.8` through
the `4.7.0` GA release.

## OCI testing appliance image

The appliance publication workflow used to install the newest stable plugin
release found on PyPI when the image was built. Because PyPI publication runs in
parallel with the image build, an image could be built before its release
reached PyPI and install the previous release while its tag named the new
release commit. Version `0.0.29.post2` was affected: its image contains plugin
`0.0.29.post1`.

On a GitHub Release the build now installs exactly the plugin version named by
the release tag. It waits for that version to appear on PyPI, retries transient
PyPI errors, refuses prerelease tags, and verifies the installed plugin version
inside the built image before publishing. The versioned image is published
first. The mutable `oci` tag then moves to it only if the released version is
the newest stable release ever published, so rebuilding an older release never
downgrades the tag. Manual and pull-request runs still use the newest stable
release and publish nothing.

If you run the appliance image, pull the image published for this release. The
`oci` tag from the previous release contains plugin `0.0.29.post1`, which lacks
the `netbox_proxbox.W107` system check.

## Upgrade

Upgrade from any `0.0.29` release with the usual package upgrade and
`manage.py migrate`; this release adds no migration.

## Compatibility baseline

Current backend-runtime pairing: netbox-proxbox 0.0.29.post3 <-> proxbox-api 0.0.23.post3 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.29.post3 | v0.0.23.post3 | v0.0.13 | v0.0.15 |
