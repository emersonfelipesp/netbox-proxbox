# Compatibility Matrix

> `proxbox-api` is a separately deployed backend service, not a Python package dependency.
> `netbox-proxbox` communicates with it over REST, SSE, and WebSocket.

## NetBox support tiers

Declared once in [`netbox_proxbox/compat.py`](netbox_proxbox/compat.py) and
vendored byte-identically across the whole Proxbox plugin stack
(`netbox-proxbox`, `netbox-ceph`, `netbox-packer`, `netbox-pbs`, `netbox-pdm`):

| Tier | NetBox range | Constant | Behaviour |
|---|---|---|---|
| Stable | `4.5.8` – `4.7.0` | `STABLE_MIN_NETBOX_VERSION` / `STABLE_MAX_NETBOX_VERSION` | Admitted silently. CI exercises NetBox 4.5.8, 4.5.10, 4.6.0, 4.6.6, and 4.7.0. |
| Experimental | NetBox 4.7.0 pre-release builds within the declared loader range | Advisory warning via system check `netbox_proxbox.W001`; not a GA support promise. |

`PluginConfig.min_version` is `4.5.8` and `PluginConfig.max_version` is
`4.7.0`. Official NetBox 4.7.0 GA is stable, so an operator can upgrade
NetBox without changing plugin configuration or database state. Pre-release
builds are outside the GA promise and receive an advisory warning.

Anything below `4.5.8` or above `4.7.0` is refused by NetBox's own plugin
version gate. The pre-release advisory is silenceable through the
`silence_netbox_compatibility_warning` key in this plugin's `PLUGINS_CONFIG`
entry.

> **The current source contract applies to the next published package.** Older
> artifacts retain their historical ceiling; install the GA-capable package
> before upgrading a production NetBox instance.

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

So before upgrading to NetBox 4.7, upgrade **every** installed Proxbox-family
plugin to a GA-capable release, and afterwards verify each one is actually
registered rather than trusting that NetBox started:

```bash
python manage.py shell -c "from django.apps import apps; print([p for p in ('netbox_proxbox','netbox_pbs','netbox_pdm','netbox_ceph','netbox_packer') if apps.is_installed(p)])"
```

Older NetBox 4.5/4.6 installations remain supported by the same package.

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

**GA evidence.** The required real-NetBox Django matrix retains the 4.5 and 4.6
cells for backward compatibility and adds exact NetBox `v4.7.0` at commit
`5f06007e4c9bacc93ce17c1e645fc1143d60df3d`. Every cell checks the checked-out
commit, final `release.yaml` metadata, and upstream requirements checksum before
installing a reviewed Python 3.12/Linux lock with artifact hashes and an
explicit PyPI first-index policy.

Current backend-runtime pairing: netbox-proxbox 0.0.26.post2 <-> proxbox-api 0.0.21.post6 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| netbox-proxbox | NetBox | Python | proxbox-api | proxbox-api internal netbox-sdk (REST only) | proxmox-sdk |
|---|---|---|---|---|---|
| v0.0.26.post2 | 4.5.8-4.7.0 GA | >=3.12 | v0.0.21.post6 | v0.0.10 | v0.0.13 |
| v0.0.26.post1 | 4.5.8-4.7.0 GA | >=3.12 | v0.0.20 | v0.0.10 | v0.0.13 |
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
