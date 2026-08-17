# Compatibility Matrix

> `proxbox-api` is a separately deployed backend service, not a Python package dependency.
> `netbox-proxbox` communicates with it over REST, SSE, and WebSocket.

## NetBox support tiers

Declared once in [`netbox_proxbox/compat.py`](netbox_proxbox/compat.py) and
vendored byte-identically across the whole Proxbox plugin stack
(`netbox-proxbox`, `netbox-ceph`, `netbox-packer`, `netbox-pbs`, `netbox-pdm`):

| Tier | NetBox range | Constant | Behaviour |
|---|---|---|---|
| Stable | `4.5.8` – `4.6.99` | `STABLE_MIN_NETBOX_VERSION` / `STABLE_MAX_NETBOX_VERSION` | Admitted silently. Directly exercised in CI at v4.5.8, v4.5.10, v4.6.0 and v4.6.6; the rest of the band is admitted on the strength of those. |
| Experimental | `4.7.0` – `4.7.99` | `EXPERIMENTAL_MIN_NETBOX_VERSION` / `EXPERIMENTAL_MAX_NETBOX_VERSION` | Loads and runs; warns once via system check `netbox_proxbox.W001`. |

`PluginConfig.min_version` is the stable floor; `PluginConfig.max_version` is
the **experimental** ceiling (`4.7.99`). Admitting 4.7 without an opt-in is
deliberate: an operator upgrading NetBox never has to touch plugin
configuration. The warning is silenceable through Django's stock
the `silence_netbox_compatibility_warning` key in this plugin's `PLUGINS_CONFIG` entry — see below; NetBox does not read `SILENCED_SYSTEM_CHECKS` from `configuration.py`.

Anything below `4.5.8` or from `4.8` onward is refused by NetBox's own plugin
version gate.

> **These tiers describe the *next* release, not the currently published
> package.** Every artifact published before this change declares
> `max_version = "4.6.99"` and will refuse NetBox 4.7 regardless of what this
> table says. `pip install` of an older version therefore still caps at 4.6.99.

### Upgrading to NetBox 4.7 means upgrading the whole plugin stack

A Proxbox-family plugin left at the old `4.6.99` ceiling does **not** stop
NetBox from starting. `netbox/settings.py` catches `IncompatiblePluginError`,
emits a Python `warnings.warn`, and **skips that plugin** — NetBox comes up
without it.

That is easy to miss and worth stating plainly, because the quiet failure is
the dangerous one. `warnings.warn` does not reach the application log in a
normal production deployment, so the visible symptom is not an error but an
*absence*: the plugin's navigation entries, views, REST API routes, and
background jobs are simply gone, and anything that depended on them fails later
and further away. A health probe against NetBox itself still returns 200.

So before moving an instance to 4.7, upgrade **every** installed Proxbox-family
plugin to a release carrying the `4.7.99` ceiling, and afterwards verify each
one is actually registered rather than trusting that NetBox started:

```bash
python manage.py shell -c "from django.apps import apps; print([p for p in ('netbox_proxbox','netbox_pbs','netbox_pdm','netbox_ceph','netbox_packer') if apps.is_installed(p)])"
```

On 4.5.8–4.6.x, mixed versions remain fine as before.

### netbox-branching does not support NetBox 4.7 yet

`netboxlabs-netbox-branching` declares `max_version = "4.6.99"` (checked
through 1.0.3), so on NetBox 4.7 **NetBox skips it** — the package stays
importable, but its Django app is absent from `INSTALLED_APPS` and its models
and schemas do not exist.

If you use branch-isolated sync (`branching_enabled = True`), **do not move to
NetBox 4.7 until a 4.7-capable netbox-branching release exists.** The
availability detector here now requires the loaded app rather than an
importable package, so a skipped branching app is correctly reported as
unavailable; but a sync configured for branch isolation that finds branching
unavailable currently proceeds against `main` rather than refusing, which
silently drops the isolation boundary you configured. Tightening that to
fail closed is tracked separately.

Installations that do not use branching are unaffected.

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
