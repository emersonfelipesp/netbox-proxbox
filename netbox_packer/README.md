# netbox-packer

`netbox-packer` is a sibling NetBox plugin for `netbox-proxbox`.

Version 0.0.1 is scaffold-only. It defines the persisted Packer image
definition, build, settings, choices, and REST API surfaces used by later
phases of the Packer support epic. UI views, background job execution,
proxbox-api HTTP calls, and CloudImageTemplate publication are intentionally
out of scope for this package version.

## Included Models

- Packer image definitions
- Packer image builds
- Packer plugin settings

## API

The API is exposed under `/api/plugins/packer/`:

- `image-definitions/`
- `image-builds/`
- `plugin-settings/`
