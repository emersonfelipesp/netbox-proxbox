# Compatibility Matrix

> `proxbox-api` is a separately deployed backend service, not a Python package dependency.
> `netbox-proxbox` communicates with it over REST, SSE, and WebSocket.

## NetBox support tiers

Declared once in [`netbox_proxbox/compat.py`](netbox_proxbox/compat.py) and
vendored byte-identically across the whole Proxbox plugin stack
(`netbox-proxbox`, `netbox-ceph`, `netbox-packer`, `netbox-pbs`, `netbox-pdm`):

| Tier | NetBox range | Constant | Behaviour |
|---|---|---|---|
| Stable | `4.5.8` – `4.6.99` | `STABLE_MIN_NETBOX_VERSION` / `STABLE_MAX_NETBOX_VERSION` | Certified, CI-gated, silent. |
| Experimental | `4.7.0` – `4.7.99` | `EXPERIMENTAL_MIN_NETBOX_VERSION` / `EXPERIMENTAL_MAX_NETBOX_VERSION` | Loads and runs; warns once via system check `netbox_proxbox.W001`. |

`PluginConfig.min_version` is the stable floor; `PluginConfig.max_version` is
the **experimental** ceiling (`4.7.99`). Admitting 4.7 without an opt-in is
deliberate: an operator upgrading NetBox never has to touch plugin
configuration. The warning is silenceable through Django's stock
`SILENCED_SYSTEM_CHECKS`; the plugin adds no setting of its own.

Anything below `4.5.8` or from `4.8` onward is refused by NetBox's own plugin
version gate.

### Upgrading to NetBox 4.7 upgrades the whole plugin stack at once

`PluginConfig.validate()` raises `IncompatiblePluginError` **while
`netbox/settings.py` is still executing**, so a single installed plugin whose
`max_version` still reads `4.6.99` prevents NetBox from starting at all — it is
not a degraded mode or a disabled plugin, it is a failed boot.

That makes the Proxbox-family plugins an all-or-nothing set on 4.7. Upgrading
`netbox-proxbox` while leaving `netbox-ceph`, `netbox-packer`, `netbox-pbs`, or
`netbox-pdm` at an older release fails exactly as hard as the reverse. Before
moving a NetBox instance to 4.7, upgrade **every** installed Proxbox-family
plugin to a release carrying the `4.7.99` ceiling; on 4.5.8–4.6.x, mixed
versions remain fine as before.

**Beta version strings.** NetBox's `release.yaml` at tag `v4.7.0-beta1` reads
`version: "4.7.0"` with `designation: "beta1"`, and `netbox/settings.py` passes
`RELEASE.version` — the bare `"4.7.0"` — to `PluginConfig.validate()`. The
`4.7.99` ceiling is sized for that comparison string;
`RELEASE.full_version` (`"4.7.0-beta1"`) is used only for display.

Current backend-runtime pairing: netbox-proxbox 0.0.24 <-> proxbox-api 0.0.20 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| netbox-proxbox | NetBox | Python | proxbox-api | proxbox-api internal netbox-sdk (REST only) | proxmox-sdk |
|---|---|---|---|---|---|
| v0.0.24 | >=4.5.8 | >=3.12 | v0.0.20 | v0.0.10 | v0.0.13 |
| v0.0.23.post2 | >=4.5.8 | >=3.12 | guest-VM-interface writer build / next release | v0.0.10 | v0.0.12 |
| v0.0.23.post1 | >=4.5.8 | >=3.12 | guest-VM-interface writer build / next release | v0.0.10 | v0.0.12 |
| v0.0.23 | >=4.5.8 | >=3.12 | guest-VM-interface writer build / next release | v0.0.10 | v0.0.12 |
| v0.0.22 | >=4.5.8 | >=3.12 | v0.0.19.post5 | v0.0.10 | v0.0.12 |
| v0.0.21 | >=4.5.8 | >=3.12 | v0.0.18.post5 | v0.0.10 | v0.0.12 |
| v0.0.20.post3 | >=4.5.8 | >=3.12 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| v0.0.20.post2 | >=4.5.8 | >=3.12 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| v0.0.20.post1 | >=4.5.8 | >=3.12 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| v0.0.20 | >=4.5.8 | >=3.12 | v0.0.17 | v0.0.8.post1 | v0.0.11 |
| v0.0.19 | >=4.5.8 | >=3.12 | v0.0.16 | v0.0.8.post1 | v0.0.9 |
| v0.0.18.post1 | ≥4.5.8 | ≥3.12 | v0.0.14 | v0.0.8.post1 | v0.0.3.post1 |
| v0.0.18 | ≥4.5.8 | ≥3.12 | v0.0.14 | v0.0.8.post1 | v0.0.3.post1 |
| v0.0.17 | ≥4.5.8 | ≥3.12 | v0.0.13 | v0.0.8.post1 | v0.0.3.post1 |
| v0.0.16 | ≥4.5.8 | ≥3.12 | v0.0.12 | v0.0.8.post1 | v0.0.3.post1 |
| v0.0.15.post2 | ≥4.5.8 | ≥3.12 | v0.0.11.post2 | v0.0.8.post1 | v0.0.5.post1 |
| v0.0.15.post1 | ≥4.5.8 | ≥3.12 | v0.0.11.post1 | v0.0.8.post1 | v0.0.3.post1 |
| v0.0.15 | ≥4.5.8 | ≥3.12 | v0.0.11 | v0.0.8.post1 | v0.0.3.post1 |
| v0.0.14 | ≥4.5.8 | ≥3.12 | v0.0.10.post2 | v0.0.8.post1 | v0.0.3.post1 |
| v0.0.13.post4 | ≥4.5.8 | ≥3.12 | v0.0.9.post2 | v0.0.7.post6 | v0.0.3.post1 |
| v0.0.13.post2 | ≥4.6.0-beta2 | ≥3.12 | v0.0.9.post1 | v0.0.7.post6 | v0.0.3.post1 |
| v0.0.13.post1 | ≥4.6.0-beta2 | ≥3.12 | v0.0.9 | v0.0.7.post6 | v0.0.3.post1 |
| v0.0.12 | ≥4.6.0-beta1 | ≥3.12 | v0.0.8.post1 | v0.0.7.post6 | v0.0.3.post1 |
| v0.0.11 | ≥4.5.7 | ≥3.12 | v0.0.7 | v0.0.7.post4 | v0.0.2.post2 |
