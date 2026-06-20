# Version 0.0.20.post3

netbox-proxbox `0.0.20.post3` pairs with the `proxbox-api 0.0.17.post1`
backend release, the `proxmox-sdk 0.0.11.post1` Proxmox SDK, and
`netbox-sdk 0.0.9.post1`. NetBox compatibility is unchanged: `4.5.8` through
`4.6.99` (validated against `4.5.8`, `4.5.9`, `4.6.0`, and the official
`4.6.1`).

## Highlights

- **Disabled endpoints are inventory-only.** Endpoint-like rows with
  `enabled=False` remain visible in UI/API output, but operational paths now
  return before any proxbox-api, NetBox, Proxmox, PBS, PDM, OpenAPI, keepalive,
  backend registration, startup/signal, or sync network attempt.
- **Disabled Proxmox status is not an error.** Proxmox endpoint list, detail,
  and dashboard status surfaces render disabled rows as a gray **Disabled**
  badge and omit live status polling metadata.
- **Shared guard for companion endpoints.** The enabled-state guard applies to
  `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `PBSEndpoint`,
  `PDMEndpoint`, and companion endpoint objects that expose an `enabled` field.
- **Maintenance coverage.** LLM-facing and developer docs now describe the
  all-endpoint no-connection invariant, and regression tests cover
  PBSEndpoint/PDMEndpoint shared `EndpointBase.enabled` behavior plus guard
  wiring in operational modules.

## Compatibility

| NetBox  | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.20.post3 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20.post2 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20.post1 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20 | v0.0.17 | v0.0.8.post1 | v0.0.11 |

`proxbox-api` is not a Python dependency of this plugin; the services
communicate over HTTP/SSE/WebSocket. Install the matching
`proxbox-api 0.0.17.post1` backend separately. This release supports NetBox
`4.5.8` through `4.6.99` and requires Python `>=3.12`.

## Upgrade Notes

- Upgrade the plugin to `netbox-proxbox 0.0.20.post3` and keep the backend on
  `proxbox-api 0.0.17.post1`.
- Use `proxmox-sdk 0.0.11.post1` and `netbox-sdk 0.0.9.post1` in the paired
  backend environment.
- Run the normal NetBox plugin upgrade flow: install the package, run
  `python manage.py migrate netbox_proxbox`, collect static files, and restart
  NetBox/RQ workers.
- No model, migration, dependency, NetBox compatibility, or backend-contract
  version changes are included in this post-release patch.
