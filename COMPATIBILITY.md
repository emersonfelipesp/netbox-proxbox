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
| Experimental | exact canonical `4.7.0-beta2` | `APPROVED_EXPERIMENTAL_NETBOX_VERSION` / `APPROVED_EXPERIMENTAL_NETBOX_DESIGNATION` | Loads for evaluation; warns once via system check `netbox_proxbox.W001`. |

`PluginConfig.min_version` is the stable floor; `PluginConfig.max_version` is
the bare held-line ceiling (`4.7.0`). NetBox uses this same bare value for
beta2, later prereleases, and GA, so `ProxboxConfig.validate()` also requires
canonical `release.yaml` identity `version: "4.7.0"` plus `designation:
"beta2"`. The beta maturity warning is silenceable through the
`silence_netbox_compatibility_warning` key in this plugin's `PLUGINS_CONFIG`
entry; the identity guard is not.

Anything below `4.5.8` or above bare `4.7.0` is refused by NetBox's own plugin
version gate. Other identities on bare `4.7.0` fail the canonical guard.

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

So before evaluating exact beta2, upgrade **every** installed Proxbox-family
plugin to a release carrying the same canonical identity guard, and afterwards
verify each one is actually registered rather than trusting that NetBox started:

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

**Beta version strings.** NetBox's `release.yaml` at tag `v4.7.0-beta2` reads
`version: "4.7.0"` with `designation: "beta2"`, and `netbox/settings.py` passes
`RELEASE.version` — the bare `"4.7.0"` — to `PluginConfig.validate()`. The
numeric ceiling admits that comparison value, then the guard reads canonical
`release.yaml` directly. Optional `local/release.yaml` may contain only
informational `build`; it cannot replace canonical version or designation.
The guard intentionally does not call overlaying `load_release_data()`.

**Current pre-release evidence.** The required real-NetBox Django matrix runs
against exact NetBox `v4.7.0-beta2` commit
`aa1d49d0f5021a28e6efc2d0364b84c5bcec7137`; all existing 4.5 and 4.6 cells
remain required as backward-compatibility evidence. Every cell independently
checks the checked-out commit, `release.yaml` version/designation, and upstream
requirements checksum before installing a reviewed Python 3.12/Linux lock with
artifact hashes and an explicit PyPI first-index policy.

Current backend-runtime pairing: netbox-proxbox 0.0.25 <-> proxbox-api 0.0.20 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| netbox-proxbox | NetBox | Python | proxbox-api | proxbox-api internal netbox-sdk (REST only) | proxmox-sdk |
|---|---|---|---|---|---|
| v0.0.25 | 4.5.8-4.6.x; exact canonical 4.7.0-beta2 | >=3.12 | v0.0.20 | v0.0.10 | v0.0.13 |
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
