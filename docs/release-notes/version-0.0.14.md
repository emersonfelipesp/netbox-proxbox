# Version 0.0.14

## Summary

Version `0.0.14` is a certification bump that pairs the plugin with the separate `proxbox-api` backend release `0.0.10.post2`. There are no plugin runtime code changes: the REST routes consumed by the plugin, SSE event vocabulary, WebSocket auth handshake, `X-Proxbox-API-Key` auth header, and the cross-repo `SyncOverwriteFlags` contract (22 fields, captured in `contracts/overwrite_flags.json`) remain compatible with the previous `0.0.13.post4` / backend `0.0.9.post2` pair.

`proxbox-api` is not a direct Python dependency of `netbox-proxbox`. The plugin installs independently and communicates with the backend over REST, SSE, and WebSocket.

## Compatibility

| NetBox         | netbox-proxbox  | proxbox-api  | netbox-sdk   | proxmox-sdk    |
|----------------|-----------------|--------------|--------------|----------------|
| >=4.5.8         | v0.0.14         | v0.0.10.post2 | v0.0.8.post1 | v0.0.3.post1   |
| >=4.5.8         | v0.0.13.post4   | v0.0.9.post2 | v0.0.7.post6 | v0.0.3.post1   |
| >=4.6.0-beta2  | v0.0.13.post2   | v0.0.9.post1 | v0.0.7.post6 | v0.0.3.post1   |
| >=4.6.0-beta2  | v0.0.13.post1   | v0.0.9       | v0.0.7.post6 | v0.0.3.post1   |
| >=4.6.0-beta1  | v0.0.13         | v0.0.9       | v0.0.7.post6 | v0.0.3.post1   |

NetBox compatibility range: `4.5.8` – `4.6.99` (unchanged). This line is certified simultaneously against NetBox `v4.5.8`, `v4.5.9`, and official `v4.6.0`.

The `netbox-sdk` column reflects the version bundled inside the `proxbox-api` backend (`0.0.8.post1` in backend release `0.0.10.post2`, up from `0.0.7.post6`); it is not a plugin-side dependency.

---

## What Changed in `proxbox-api` 0.0.9.post2 → 0.0.10.post2

This release certifies the plugin against the new backend release so operators can upgrade both services in lockstep. Notable upstream changes (none of which require plugin code changes):

- **Backend security fix.** `X-Forwarded-For` is no longer trusted unless the operator explicitly opts in via `PROXBOX_TRUSTED_PROXIES` on the backend container. If you run `proxbox-api` behind a reverse proxy and want per-client rate-limiting / brute-force lockout to track real client IPs, set `PROXBOX_TRUSTED_PROXIES` to a CIDR list. Otherwise rate limits and lockouts are computed against the proxy's IP. This is a backend-side configuration; the plugin itself does not care.
- **Backend `VM_ROLE_MAPPINGS` slug normalization.** The fallback role slug shifted from `virtual-machine` to `unknown`, and `qemu` / `lxc` gain colors plus `vm_role: True`. The plugin's three remaining `"virtual-machine"` literals (`sync_stages.py`, `views/sync.py`) are NetBox content-type discriminators in `dependencies_synced` payloads, not device-role slugs, so they are unaffected.
- **Live NetBox version gates.** The backend detects NetBox via `/api/status/` and gates 4.6-only `VirtualMachineType` sync, so one backend release supports NetBox `4.5.8`, `4.5.9`, and `4.6.0`.
- **Internal `netbox-sdk` bump.** `0.0.7.post6` → `0.0.8.post1` is internal to the backend image and not a plugin dependency.
- **REST retry override precedence.** Explicit `PROXBOX_NETBOX_*` environment overrides now take precedence over backend-stored retry settings.

Routes, SSE event types (`step` / `discovery` / `substep` / `item_progress` / `phase_summary` / `error_detail` / `error` / `complete`), `SseCompletePayload`, and the WebSocket frame protocol are all unchanged.

---

## CI / Release Pipeline

- `e2e-docker.yml` and `docs-screenshots.yml` now pin the runtime backend image version to `0.0.10.post2`.
- `nightly-contracts.yml` validates committed REST/SSE/overwrite-flag wire contracts without installing or importing `proxbox-api`.
- The two Docker-pulling workflows depend on the `emersonfelipesp/proxbox-api:0.0.10.post2` image being on Docker Hub. If the image lags PyPI publication, those workflows will fail until the image lands.
- Docker-based CI passes a deterministic `PROXBOX_ENCRYPTION_KEY` because the backend refuses to start without an encryption key or explicit plaintext opt-in.
- `nightly-contracts.yml` validates local plugin contracts and is unaffected by Docker Hub timing.

## Database Migrations

None. No model or schema changes ship in `0.0.14`.

## Upgrade Guidance

Standard upgrade flow ([`installation/upgrading.md`](../installation/upgrading.md)):

```bash
cd /opt/netbox/netbox
source /opt/netbox/venv/bin/activate
pip install -U netbox-proxbox
sudo systemctl restart netbox
```

Then upgrade the backend image / package to `0.0.10.post2`. There are no migrations to run for the plugin.
