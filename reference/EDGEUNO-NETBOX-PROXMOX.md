# `edgeuno/netbox-proxbox` — Detailed Reference

> Reference dossier for the EdgeUno fork of `netbox-proxbox`, mirrored
> locally at `/root/nms/edgeuno/netbox-proxbox`.
>
> This document exists inside the upstream `netbox-proxbox` repository so
> that contributors here can consult an authoritative summary of how the
> EdgeUno fork diverged: its directory layout, configuration model, sync
> engines, runtime modes, and the operational quirks an operator inherits
> when running it.
>
> Source revision basis:
>
> - Upstream remote: `https://github.com/edgeuno/netbox-proxbox` (`origin`).
> - Default branch: `develop`.
> - Latest release tag visible in `git log`: `0.1.0` (commit `45c474d`,
>   "(Release) Bump Version 0.0.12 -> 0.1.0"). The plugin nonetheless still
>   self-reports `0.0.5` from `PluginConfig.version` (see §6.1).
> - This reference describes the project **as it exists on disk** at the
>   tip of `develop`, not as it documents itself externally.

---

## Table of Contents

1. [Overview](#1-overview)
2. [System Requirements & Compatibility](#2-system-requirements--compatibility)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Repository Layout](#4-repository-layout)
5. [Configuration Model](#5-configuration-model)
6. [Plugin Surface](#6-plugin-surface)
7. [The v1 Sync Engine — `proxbox_api/`](#7-the-v1-sync-engine--proxbox_api)
8. [The v2 Sync Engine — `proxbox_api_v2/`](#8-the-v2-sync-engine--proxbox_api_v2)
9. [Standalone & Containerised Runtime](#9-standalone--containerised-runtime)
10. [Documentation Site](#10-documentation-site)
11. [Dependencies](#11-dependencies)
12. [Operational Notes](#12-operational-notes)
13. [Known Issues & Quirks](#13-known-issues--quirks)
14. [Glossary](#14-glossary)

---

## 1. Overview

`edgeuno/netbox-proxbox` is a NetBox plugin that imports Proxmox VE
inventory state into NetBox. Its lineage:

- Originally authored by **Emerson Felipe**
  (`emerson.felipe@nmultifibra.com.br`) as `netdevopsbr/netbox-proxbox`.
- Forked and substantially diverged by **Javier Alejandro Ruiz**
  (`javier.ruiz@edgeuno.com`) for EdgeUno’s internal use. The fork carries
  EdgeUno-specific business logic (default tenant assignment by regex,
  description-field parsing for client/email/IP hints, role pinning to
  `"VPS"` and `"LXC"`).

| Attribute | Value |
|---|---|
| Original author | Emerson Felipe (`emerson.felipe@nmultifibra.com.br`) |
| Fork maintainer | Javier Alejandro Ruiz (`javier.ruiz@edgeuno.com`) |
| License | Apache 2.0 |
| Upstream | `https://github.com/edgeuno/netbox-proxbox` |
| Default branch | `develop` |
| Documentation | `https://proxbox.netbox.dev.br/` (MkDocs Material; pages currently stub-only) |
| Plugin version (`PluginConfig`) | `0.0.5` |
| Plugin version (`pyproject.toml`) | `0.0.5` |
| Plugin version (`setup.py`) | `0.1.0` |
| Latest release tag | `0.1.0` |

### What it IS

- A NetBox plugin (Django app + models + migrations + views + REST API).
- A **Proxmox→NetBox importer** that mirrors clusters, nodes, virtual
  machines, and LXC containers into NetBox’s `dcim` and `virtualization`
  apps.
- A **multi-cluster** importer in its v2 path: a single
  `configuration_options.json` file lists every Proxmox cluster the
  plugin should walk in one sync run.
- A **dual-mode runtime**: the same code can be invoked synchronously from
  the NetBox UI ("Full Update" button via the v1 path) or asynchronously
  from a scheduled container ("scrapper" via the v2 path).

### What it IS NOT

- Not a desired-state controller. It does not push state from NetBox into
  Proxmox; all Proxmox API calls are read-only `GET`s.
- Not a NetBox Labs project. It is the EdgeUno fork of a community plugin,
  unaffiliated with `netboxlabs/netbox-proxmox-automation`.
- Not in active feature development externally — the documentation site
  pages are skeletons (every page contains only an H1 heading), and the
  most recent commits on `develop` are bug fixes and the standalone
  Docker mode.
- Not a complete replacement for the upstream `netbox-proxbox`. The fork
  has diverged structurally (two coexisting sync engines, different
  configuration model, different plugin surface), so changes here do not
  propagate to upstream.

---

## 2. System Requirements & Compatibility

### 2.1. Compatibility table

The version table is documented only in `README.md` (lines 68–76); it is
not enforced by `min_version` / `max_version` on `PluginConfig`.

| NetBox | Proxmox VE | Proxbox plugin |
|---|---|---|
| ≥ 4.0.7 | ≥ 6.2.0 | 0.0.12 |
| ≥ 3.5.2 | ≥ 6.2.0 | 0.0.11 |
| ≥ 3.2.0 | ≥ 6.2.0 | 0.0.4 |

The `Dockerfile` (`Dockerfile:3`) pins `ARG NETBOX_VERSION=4.5.8` as the
default NetBox release the container will pull and install on top of.

### 2.2. Python

Three sources disagree:

| Source | Constraint |
|---|---|
| `pyproject.toml:13` | `python = "^3.8"` |
| `setup.py` | `python_requires=">=3.7"` |
| `Dockerfile:1` | `FROM python:3.12-slim` |

In practice, the container builds and runs on Python 3.12; the lower
bounds are aspirational.

### 2.3. Authentication

Authentication is **token-only on Proxmox** (username + token name +
token value) and **token-only on NetBox** (`api_token`). The
configuration JSON also accepts a `password` field, but the active code
paths use the token.

### 2.4. Mandatory NetBox custom fields

Before a sync runs, the operator must manually create the following
custom fields on `virtualization.virtualmachine`:

| Custom field | Type | Used by |
|---|---|---|
| `proxmox_id` | integer | both sync engines — primary VM identity key |
| `proxmox_node` | text | both sync engines — node residence |
| `proxmox_type` | text | both sync engines — `"qemu"` or `"lxc"` |
| `proxmox_keep_interface` | boolean | v1 — prevents v1 interface sync from rewriting an interface |

The plugin does not auto-create these — without them, VM lookups fall
back to name-only matching, which is fragile.

---

## 3. High-Level Architecture

```
                       ┌─────────────────────────────────────┐
                       │  configuration_options.json         │
                       │  proxmox: [ {domain, token, ...} ]  │
                       │  netbox:  { api, tenant, ... }      │
                       └────────────────┬────────────────────┘
                                        │  read at import time
                                        ▼
                       ┌─────────────────────────────────────┐
                       │  proxbox_api_v2/plugins_config.py   │
                       │  PROXMOX_SESSIONS_LIST  (list)      │
                       │  PROXMOX_SESSIONS       (dict)      │
                       └────────────────┬────────────────────┘
                                        │
       ┌────────────────────────────────┴─────────────────────────────────┐
       │                                                                  │
       │  v2 path (active)                          v1 path (legacy UI)   │
       │                                                                  │
       │  python manage.py proxboxscrapper          GET /plugins/proxbox/ │
       │      │                                          full_update/    │
       │      ▼                                            │              │
       │  Scrapper.async_run()                             ▼              │
       │   ├─ get_all_clusters   (asyncio.gather)    proxbox_api.update  │
       │   ├─ get_all_nodes      (asyncio.gather)        .all()           │
       │   ├─ get_all_vms        (batched gather)        │                │
       │   └─ async_clear_vms    (raw SQL by latest_job) │ pynetbox       │
       │      │                                          │ session        │
       │      │ Django ORM                               ▼                │
       │      ▼                                    NetBox REST API        │
       │  ┌─────────────────────────────────┐                             │
       │  │  netbox_handler/  (per resource)│                             │
       │  │  upsert_cluster                 │                             │
       │  │  upsert_cluster_type            │                             │
       │  │  upsert_site                    │                             │
       │  │  upsert_manufacturer            │                             │
       │  │  upsert_device_type             │                             │
       │  │  upsert_role                    │                             │
       │  │  upsert_nodes                   │                             │
       │  │  upsert_proxbox_item            │                             │
       │  │  upsert_netbox_vm               │                             │
       │  │  tag / custom_tag / base_tag    │                             │
       │  └────────────┬────────────────────┘                             │
       │               │                                                  │
       └───────────────┼──────────────────────────────────────────────────┘
                       ▼
                ┌────────────────────────────┐
                │  NetBox (Django) database  │
                │  + the plugin's own        │
                │  ProxmoxVM shadow records  │
                └────────────────────────────┘
                       ▲
                       │ HTTPS GET only (proxmoxer, token auth)
                ┌──────┴─────────────────────┐
                │     Proxmox VE clusters    │
                │    (one or many)           │
                └────────────────────────────┘
```

**Key invariants:**

- All Proxmox traffic is read-only. `proxmoxer` is used only via `.get()`.
- The v2 path writes to NetBox via the **Django ORM directly**, since it
  runs in-process inside a NetBox-aware Python interpreter (the
  `proxboxscrapper` management command).
- The v1 path writes to NetBox via **pynetbox HTTP**, even though it
  also runs in-process inside NetBox. This is a structural artefact of
  v1 having predated the plugin form-factor.
- v2 runs are identified by a UUID `job_id` written to
  `ProxmoxVM.latest_job`. Stale-VM cleanup uses raw SQL to find rows
  whose `latest_job` does not match the current run.

---

## 4. Repository Layout

### 4.1. Repository root

```
edgeuno/netbox-proxbox/
├── README.md                              556 lines — installation, configuration, usage
├── CONTRIBUTING.md                        contribution guidelines
├── LICENSE                                Apache 2.0
├── CNAME                                  proxbox.netbox.dev.br
├── pyproject.toml                         Poetry metadata (version 0.0.5)
├── setup.py                               setuptools shim (version 0.1.0)
├── poetry.lock
├── MANIFEST.in
├── mkdocs.yml                             docs site (Material theme)
├── tasks.py                               316 lines — Invoke runner (build/test/lint/Docker wrappers)
├── proxbox_runner.sh                      30 lines — finds manage.py and runs proxboxscrapper
├── configuration_options_default.json     24 lines — JSON config template
├── Dockerfile                             51 lines — python:3.12-slim + NetBox 4.5.8 + plugin
├── docker-compose.yaml                    24 lines — long-running scheduler service
├── docker-compose-single-exec.yml         25 lines — one-shot sync container
│
├── docker/
│   └── entrypoint/
│       ├── scanner-runner.sh              5 lines — shell wrapper to scanner_scheduler.py
│       └── scanner_scheduler.py           210 lines — four-mode scheduler daemon
│
├── runtime/
│   ├── configuration.py.example           42 lines — NetBox configuration.py template
│   └── scanner.env.example                7 lines — scheduler env template, default off
│
├── etc/
│   └── img/                               4 PNGs (logos and screenshots)
│
├── docs/                                  MkDocs source — every page is a stub (H1 only)
│   ├── introduction.md
│   ├── installation/
│   ├── features/
│   ├── configuration/
│   ├── models/
│   └── release-notes/
│
├── .github/
│   └── workflows/
│       ├── ci.yml                         flake8 on develop (Python 3.6/3.7/3.8)
│       └── python-package.yml             flake8 on main (Python 3.7/3.8)
│
└── netbox_proxbox/                        the Django plugin package
```

### 4.2. The plugin package — `netbox_proxbox/`

```
netbox_proxbox/
├── __init__.py                  52 lines — ProxboxConfig (PluginConfig)
├── admin.py                      7 lines — Django admin for ProxmoxVM
├── choices.py                   81 lines — TaskTypeChoices, TaskStatusChoices, RemoveStatusChoices
├── example.py                   committed Python dict of ~50 historical VM names
├── filters.py                   71 lines — ProxmoxVMFilter (django_filters)
├── forms.py                     74 lines — ProxmoxVMForm + ProxmoxVMFilterForm
├── icon_classes.py              16 lines — status → CSS icon class mapping
├── models.py                   353 lines — ProxmoxVM + SyncTask
├── navigation.py                95 lines — PluginMenu (v3 + v4 compatibility shim)
├── release.py                    8 lines — runtime NetBox version detection
├── tables.py                    24 lines — ProxmoxVMTable
├── template_content.py          23 lines — PluginTemplateExtension on virtual_machine detail
├── urls.py                      37 lines — plugin URL routes
├── views.py                    173 lines — class-based views (Home, Full Update, CRUD)
│
├── api/
│   ├── __init__.py              empty
│   ├── serializers.py           44 lines — ProxmoxVMSerializer (DRF ModelSerializer)
│   ├── urls.py                  11 lines — DefaultRouter, /api/plugins/proxbox/
│   └── views.py                 37 lines — ProxmoxVMView (mixin viewset)
│
├── management/commands/
│   └── proxboxscrapper.py       25 lines — asyncio.run(Scrapper.async_run())
│
├── migrations/                  16 numbered migrations + __init__
│
├── mixin/
│   └── ModelDiffMixin.py        46 lines — field-level diff tracking
│
├── others/
│   └── db.py                    namedtuplefetchall / dictfetchall raw-SQL helpers
│
├── proxbox_api/                 v1 sync engine (legacy, web-triggered)
│   ├── __init__.py              all imports commented out
│   ├── plugins_config.py        178 lines — pynetbox + proxmoxer sessions at import time
│   ├── update.py                503 lines — vm_full_update, node_full_update, all()
│   ├── remove.py                181 lines — stale-VM removal
│   ├── create/
│   │   ├── dcim.py              manufacturer / device_type / site / node helpers
│   │   ├── extras.py            tag / role helpers
│   │   └── virtualization.py    cluster_type / cluster / virtual_machine helpers
│   └── updates/
│       ├── extras.py            tag-on-VM updater
│       ├── node.py              node field updaters
│       └── virtual_machine.py   VM field + interface + IP updaters
│
├── proxbox_api_v2/              v2 sync engine (active, async, multi-cluster)
│   ├── plugins_config.py         54 lines — reads PLUGINS_CONFIG.filePath, builds session list
│   ├── proxbox_session.py       158 lines — ProxboxSession dataclass, JSON parser
│   ├── scrapper.py              139 lines — Scrapper.async_run pipeline
│   ├── proxmox/
│   │   ├── proxmox_cluster.py        96 lines — ProxmoxCluster dataclass + async_instance_cluster
│   │   ├── proxmox_node.py          121 lines — ProxmoxNodes dataclass + async_get_node_network
│   │   └── proxmox_virtualmachine.py 177 lines — ProxmoxVirtualMachine + async_clear_vms
│   └── netbox_handler/
│       ├── nb_cluster.py             53 lines — upsert_cluster
│       ├── nb_cluster_type.py        41 lines — upsert_cluster_type (DoesNotExist bug)
│       ├── nb_device_role.py         93 lines — upsert_role
│       ├── nb_device_type.py         69 lines — upsert_device_type
│       ├── nb_manufactorer.py        51 lines — upsert_manufacturer (sic)
│       ├── nb_nodes.py              374 lines — upsert_nodes, find_node_by_ip, node_full_update
│       ├── nb_proxbox.py            220 lines — upsert_proxbox_item, get_proxmox_config
│       ├── nb_site.py                82 lines — upsert_site
│       ├── nb_tag.py                137 lines — tag, custom_tag, base_tag, dedupe_vm_tagged_items
│       └── nb_virtualmachine.py     942 lines — upsert_netbox_vm + every VM sub-routine
│
├── static/
│   ├── netbox_proxbox/proxmox-logo.svg
│   └── proxmox-logo.svg
│
├── templates/netbox_proxbox/    10 HTML templates (see §6.7)
│
└── templatetags/
    └── plugin_helpers.py        custom template tag library (uses eval())
```

---

## 5. Configuration Model

Configuration flows in three hops.

### 5.1. NetBox `configuration.py`

Operators add only one entry — the path to the JSON file. The template
lives at `runtime/configuration.py.example`:

```python
PLUGINS = ["netbox_proxbox"]
PLUGINS_CONFIG = {
    "netbox_proxbox": {
        "proxmox": {
            "filePath": "/opt/netbox/plugins/netbox-proxbox/configuration_options.json"
        }
    },
}
```

(`runtime/configuration.py.example:36–42`)

### 5.2. The JSON file — `configuration_options.json`

Created by copying `configuration_options_default.json` (24 lines). Two
top-level keys:

```jsonc
{
  "proxmox": [
    {
      "domain": "proxbox.example.com",
      "http_port": 8006,
      "user": "root@pam",
      "token_name": "tokenID",
      "token_value": "039az154-23b2-4be0-8d20-b66abc8c4686",
      "ssl": false,
      "site_name": "SITENAME",
      "node_role_name": "Hypervisor"
    }
  ],
  "netbox": {
    "manufacturer": "Dell",
    "virtualmachine_role_id": 0,
    "virtualmachine_role_name": "Proxbox Basic Role",
    "node_role_id": 0,
    "site_id": 0,
    "tenant_name": "EdgeUno",
    "tenant_regex_validator": "^prefix-",
    "tenant_description": "...",
    "create_device_when_not_found": false
  }
}
```

#### `proxmox[]` keys

| Key | Type | Default in template | Purpose |
|---|---|---|---|
| `domain` | str | `proxbox.example.com` | Proxmox host FQDN or IP |
| `http_port` | int | `8006` | Proxmox API port |
| `user` | str | `root@pam` | Proxmox API user |
| `token_name` | str | `tokenID` | Proxmox API token name |
| `token_value` | str | example UUID | Proxmox API token secret |
| `ssl` | bool | `false` | Verify TLS on Proxmox connection |
| `site_name` | str | `SITENAME` | NetBox Site name for nodes in this cluster |
| `node_role_name` | str | `Hypervisor` | NetBox DeviceRole name for nodes |

#### `netbox` keys

| Key | Type | Default in template | Purpose |
|---|---|---|---|
| `manufacturer` | str | `Dell` | Manufacturer name for node DeviceType |
| `virtualmachine_role_id` | int | `0` | NetBox role ID for VMs (`0` = ignored, name takes over) |
| `virtualmachine_role_name` | str | `Proxbox Basic Role` | Default VM role (overridden per VM type by `update_vm_role()`) |
| `node_role_id` | int | `0` | DeviceRole ID for nodes |
| `site_id` | int | `0` | Site ID fallback when `site_name` is missing |
| `tenant_name` | str | `EdgeUno` | Default tenant for VMs whose name matches `tenant_regex_validator` |
| `tenant_regex_validator` | str | `^prefix-` | Regex applied to VM name |
| `tenant_description` | str | text | Description for an auto-created default tenant |
| `create_device_when_not_found` | bool | `false` | Whether to create a Device for a node that doesn’t already exist |

> Note: `create_device_when_not_found` lives in
> `configuration_options_default.json:23` and is consumed by
> `nb_nodes.upsert_nodes()` (`netbox_handler/nb_nodes.py:333+`). It is
> **not** declared in `ProxboxConfig.default_settings`; if the operator
> omits it from the JSON, the v2 path treats it as falsy.

### 5.3. The session list

`proxbox_api_v2/plugins_config.py` (54 lines) reads the file path from
`PLUGINS_CONFIG`, calls `ProxboxSession.get_list_from_file()`
(`proxbox_session.py:130–158`), and produces:

- `PROXMOX_SESSIONS_LIST: list[ProxboxSession]` — one per cluster.
- `PROXMOX_SESSIONS: dict[domain, ProxboxSession]` — same content keyed
  by domain.

`ProxboxSession.get_list_from_file()` merges the shared `netbox` block
into every `proxmox[]` entry via `mix_proxmox_netbox_config()`, then
instantiates a `ProxboxSession` dataclass which immediately calls
`ProxmoxAPI(...)` to establish a live Proxmox session.

There is no environment-variable substitution inside the JSON. Env vars
appear only on the **scheduler** side (see §9.4).

### 5.4. `ProxboxConfig.default_settings`

`netbox_proxbox/__init__.py:7–50` declares fallback values used when the
JSON file or `PLUGINS_CONFIG` is incomplete. The default dict still
contains an example token (`token_value =
"039az154-23b2-4be0-8d20-b66abc8c4686"`) — see §13.

---

## 6. Plugin Surface

### 6.1. PluginConfig

```python
class ProxboxConfig(PluginConfig):
    name = "netbox_proxbox"
    verbose_name = "Proxbox"
    description = "Integrates Proxmox and Netbox"
    version = "0.0.5"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emerson.felipe@nmultifibra.com.br"
    base_url = "proxbox"
    required_settings = []
    default_settings = { ... }
```

(`netbox_proxbox/__init__.py:7–50`)

- `min_version` and `max_version` are **not** declared — the README is
  the only compatibility source.
- Line 52: `from . import proxbox_api`. Because `proxbox_api` is the v1
  engine and `proxbox_api/plugins_config.py` opens live Proxmox + NetBox
  connections at import time, **every Django process that loads this
  plugin attempts those connections at startup** (see §7.2 and §13).

### 6.2. Models

Both models inherit from `extras.models.models.ChangeLoggedModel` (the
older NetBox base, **not** `NetBoxModel`). Both declare
`RestrictedQuerySet.as_manager()` as their manager.

#### `ProxmoxVM` (`models.py:35`)

The plugin’s join table — links a Proxmox VM to its NetBox
`VirtualMachine` and its hypervisor `Device`. Populated only by sync.

| Field | Type | Notes |
|---|---|---|
| `name` | `CharField(255, blank, null)` | Proxmox VM name |
| `domain` | `CharField(512, blank, null)` | Proxmox cluster domain/IP |
| `url` | `CharField(512, blank, null)` | Proxmox UI deep-link |
| `latest_job` | `CharField(255, blank, null)` | UUID of the last scrapper run that touched this row |
| `latest_update` | `DateTimeField(null, blank)` | Timestamp of last sync |
| `cluster` | FK → `virtualization.Cluster` (`SET_NULL`) | |
| `node` | `CharField(64, blank, null)` | Proxmox node name (string, not FK) |
| `virtual_machine` | FK → `virtualization.VirtualMachine` (`SET_NULL`) | The actual NetBox VM |
| `status` | `CharField` (`VirtualMachineStatusChoices`) | Default `active` |
| `proxmox_vm_id` | `PositiveIntegerField` | Proxmox vmid |
| `vcpus` | `PositiveIntegerField` | |
| `memory` | `PositiveIntegerField` | MB |
| `disk` | `PositiveIntegerField` | GB |
| `device` | FK → `dcim.Device` (`SET_NULL`) | The hypervisor node’s device row |
| `type` | `CharField(64)` | `"qemu"` or `"lxc"` |
| `description` | `CharField(200)` | |
| `instance_data` | `JSONField` | Raw cluster-resource JSON |
| `config_data` | `JSONField` | Raw `qemu/<vmid>/config` or `lxc/<vmid>/config` |

`__str__` returns `str(self.virtual_machine)` if linked, else `name`,
else `"No name of virtual machine"`. `get_absolute_url` resolves
`plugins:netbox_proxbox:proxmoxvm`.

A `validate_unique` block exists but is commented out (`models.py:178–
190`).

#### `SyncTask` (`models.py:193`)

Inherits from `ModelDiffMixin` + `ChangeLoggedModel`. Designed to record
the lifecycle of a sync operation, but **not actually wired** into the
v2 path: the v2 scrapper writes its `job_id` directly into
`ProxmoxVM.latest_job` and never instantiates a `SyncTask`. The v1 path
also does not write `SyncTask` rows. The model survives because of
historical migrations (`0005_synctask` onward).

| Field | Type |
|---|---|
| `task_id` | `UUIDField(default=uuid.uuid4, unique=True)` |
| `name`, `job_id` | `CharField(blank, null)` |
| `timestamp` | `DateTimeField(auto_now_add=True)` |
| `task_type` | `CharField(TaskTypeChoices, default="undefined")` |
| `status` | `CharField(TaskStatusChoices, default="unknown")` |
| `message`, `fail_reason` | `CharField(512)` |
| `done` | `BooleanField(default=False)` |
| `remove_unused` | `BooleanField(default=True)` |
| `scheduled_time`, `start_time`, `end_time` | `DateTimeField` |
| `duration` | `PositiveIntegerField` |
| `log` | `TextField` |
| `user`, `domain` | `CharField` |
| `parent` | FK → `self` (`SET_NULL`) |
| `device` | FK → `dcim.Device` (`CASCADE`) |
| `cluster` | FK → `virtualization.Cluster` (`CASCADE`) |
| `virtual_machine` | FK → `virtualization.VirtualMachine` (`CASCADE`) |
| `data_instance` | `JSONField` |
| `progress`, `progress_status` | `PositiveIntegerField` / `CharField` |
| `finish_remove_unused` | `CharField(RemoveStatusChoices, default="not_started")` |
| `proxmox_vm` | FK → `ProxmoxVM` (`SET_NULL`) |

`save()` is overridden but the override body is commented out
(`models.py:347–353`). `ModelDiffMixin` still exposes `diff`,
`has_changed`, `changed_fields`, and `get_field_diff()`.

### 6.3. Migrations

16 numbered migration files plus `__init__`.

| File | Notable event |
|---|---|
| `0001_initial` (2021-04-19) | Creates `VmResources` (the original model name) |
| `0002_vmresources_description` | Adds `description` |
| `0003_auto_20210419_2330` | **Renames `VmResources` → `ProxmoxVM`** |
| `0004_alter_proxmoxvm_id` (2022-01-20) | `id` → `BigAutoField` |
| `0005_synctask` (2022-02-18) | **Creates `SyncTask`** |
| `0006_auto_20220419_1530` | Both models → `BigAutoField` ids |
| `0007_synctask_data_instance` | Adds `data_instance` JSONField |
| `0008_auto_20220503_2238` | (field tweaks) |
| `0009_auto_20220706_2033` | Adds `finish_remove_unused` |
| `0010_auto_20220722_1502` | (field tweaks) |
| `0011_auto_20220725_2058` | (field tweaks) |
| `0012_synctask_proxmox_vm` | Adds `proxmox_vm` FK |
| `0013_auto_20220726_1844` | (field tweaks) |
| `0014_auto_20220726_1847` | (field tweaks) |
| `0015_alter_synctask_proxmox_vm` | Alters `proxmox_vm` FK |
| `0016_auto_20220726_2003` | Latest. Switches `cluster`, `device`, `virtual_machine` on `ProxmoxVM` and `parent`, `proxmox_vm` on `SyncTask` to `SET_NULL` |

Several `ProxmoxVM` fields visible in `models.py` today (`domain`,
`url`, `latest_job`, `latest_update`, `instance_data`, `config_data`)
have **no corresponding `AddField` migration** in the committed set —
the model and the migration history are out of sync, and a
`makemigrations` run is needed on a fresh install.

### 6.4. Views & URLs

All routes mount under `proxbox/` (`ProxboxConfig.base_url`).

| URL pattern | View class | URL name |
|---|---|---|
| `proxbox/` | `HomeView` | `home` |
| `proxbox/list/` | `ProxmoxVMListView` | `proxmoxvm_list` |
| `proxbox/<int:pk>/` | `ProxmoxVMView` | `proxmoxvm` |
| `proxbox/add/` | `ProxmoxVMCreateView` | `proxmoxvm_add` |
| `proxbox/<int:pk>/delete/` | `ProxmoxVMDeleteView` | `proxmoxvm_delete` |
| `proxbox/<int:pk>/edit/` | `ProxmoxVMEditView` | `proxmoxvm_edit` |
| `proxbox/changelog/<int:pk>` | `ProxmoxVMEditView` (TODO — see §13) | `proxmoxvm_changelog` |
| `proxbox/full_update/` | `ProxmoxFullUpdate` | `proxmoxvm_full_update` |

Notes:

- `HomeView` has **no** `PermissionRequiredMixin`. Anyone authenticated
  can render the configuration dump.
- `ProxmoxFullUpdate` requires `netbox_proxbox.view_proxmoxvm` and runs
  `proxbox_api.update.all(remove_unused=True)` synchronously inside the
  request/response cycle. It blocks the worker for the duration of the
  full sync and then renders the JSON result via
  `proxmox_vm_full_update.html`.
- `ProxmoxVMListView` paginates 25 rows per page via `RequestConfig` and
  contains a stray `print("test")` (`views.py:130`).
- There are no webhook receivers, status endpoints, or progress views.

### 6.5. REST API surface

Mounted at `/api/plugins/proxbox/` via `DefaultRouter`
(`api/urls.py:11`).

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/plugins/proxbox/` | List `ProxmoxVM` |
| `POST` | `/api/plugins/proxbox/` | Create |
| `GET` | `/api/plugins/proxbox/<id>/` | Retrieve |
| `PUT` / `PATCH` | `/api/plugins/proxbox/<id>/` | Update |
| `DELETE` | `/api/plugins/proxbox/<id>/` | Delete |

`ProxmoxVMView` (`api/views.py:9`) is composed manually from DRF
mixins — `CreateModelMixin`, `DestroyModelMixin`, `ListModelMixin`,
`RetrieveModelMixin`, `UpdateModelMixin`, `GenericViewSet` — rather
than inheriting from `NetBoxModelViewSet`.

`ProxmoxVMSerializer` (`api/serializers.py:10`) is a plain
`serializers.ModelSerializer` (not `NetBoxModelSerializer`). Exposed:
`id`, `cluster`, `virtual_machine`, `proxmox_vm_id`, `status`, `node`,
`vcpus`, `memory`, `disk`, `type`, `description`. Not exposed:
`domain`, `url`, `latest_job`, `latest_update`, `instance_data`,
`config_data`, `device`.

`SyncTask` has no API endpoint.

### 6.6. Forms, tables, filtersets, navigation, choices

| Module | Class / contents |
|---|---|
| `forms.py` | `ProxmoxVMForm` (ModelForm; docstring incorrectly says "BgpPeering"); `ProxmoxVMFilterForm` (manual fields including `node` declared as `IntegerField` against a CharField column — see §13) |
| `tables.py` | `ProxmoxVMTable(NetBoxTable)` — columns `id`, `cluster`, `virtual_machine`, `proxmox_vm_id`; meta fields `id`, `virtual_machine`, `proxmox_vm_id`, `status`, `type`, `node`, `cluster` |
| `filters.py` | `ProxmoxVMFilter(django_filters.FilterSet)` — `q` search across `type` + `description`; `cluster` and `virtual_machine` `ModelMultipleChoiceFilter`; `node` `CharFilter(icontains)`; `proxmox_vm_id` `CharFilter(exact)` |
| `navigation.py` | Tries `extras.plugins`, falls back to `netbox.plugins`. Builds a `PluginMenu` named "ProxBox" with a single item linking to `proxmoxvm_list` |
| `choices.py` | `TaskTypeChoices` (20 values), `TaskStatusChoices` (7), `RemoveStatusChoices` (3) |

### 6.7. Templates and template injection

Ten templates under `netbox_proxbox/templates/netbox_proxbox/`:

| Template | Used by |
|---|---|
| `home.html` | `HomeView` — dumps current config |
| `proxmox_vm_list.html` | `ProxmoxVMListView` |
| `proxmox_vm.html` | `ProxmoxVMView` (detail) |
| `proxmox_vm_edit.html` | `ProxmoxVMCreateView` + `ProxmoxVMEditView` |
| `proxmox_vm_delete.html` | `ProxmoxVMDeleteView` |
| `proxmox_vm_full_update.html` | `ProxmoxFullUpdate` |
| `proxbox_vm_attach.html` | `template_content.py` — VM right-panel injection |
| `update_result.html` | not referenced from any view |
| `virtualmachine_proxmox_fields.html` | not referenced from any view |
| `footer.html`, `paginator.html` | shared partials |

`template_content.py` registers `ProxboxVMAttachFields(PluginTemplateExtension)`
for `model = 'virtualization.virtualmachine'`. It uses `right_page()` to
render `proxbox_vm_attach.html` — the linked `ProxmoxVM` row — into the
NetBox VM detail page.

Static assets:
`netbox_proxbox/static/proxmox-logo.svg` and
`netbox_proxbox/static/netbox_proxbox/proxmox-logo.svg`. No JS or CSS.

### 6.8. Custom fields the operator must create

The plugin reads but does not create:

- `proxmox_id` (integer) — primary VM identity key.
- `proxmox_node` (text) — node residence.
- `proxmox_type` (text) — `"qemu"` or `"lxc"`.
- `proxmox_keep_interface` (boolean) — v1 interface-sync opt-out.

Without `proxmox_id` and `proxmox_node`, VM lookups in
`upsert_netbox_vm()` (`nb_virtualmachine.py:728`) fall back to a
name-only `name__iexact` match within the cluster — fragile against
renames and case differences.

---

## 7. The v1 Sync Engine — `proxbox_api/`

The original synchronous engine. Still triggered by the
`ProxmoxFullUpdate` web view (§6.4). Writes to NetBox via pynetbox HTTP.

### 7.1. File map

| File | Role |
|---|---|
| `proxbox_api/__init__.py` | All imports commented out — module exports nothing |
| `proxbox_api/plugins_config.py` (178 lines) | Builds `proxmox` (proxmoxer) and `nb` (pynetbox) sessions at import time |
| `proxbox_api/update.py` (503 lines) | Public `all()`, `vm_full_update()`, `node_full_update()`, `virtual_machine()`, `nodes()` |
| `proxbox_api/remove.py` (181 lines) | `all()` stale-VM removal |
| `proxbox_api/create/dcim.py` | manufacturer / device_type / site / node creation helpers |
| `proxbox_api/create/extras.py` | tag / role helpers |
| `proxbox_api/create/virtualization.py` | cluster_type / cluster / virtual_machine helpers |
| `proxbox_api/updates/extras.py` | tag-on-VM updater |
| `proxbox_api/updates/node.py` | `status`, `cluster`, `interfaces` |
| `proxbox_api/updates/virtual_machine.py` | `status`, `custom_fields`, `local_context_data`, `resources`, `interfaces`, `interfaces_ips` |

### 7.2. Credential loading

`plugins_config.py` reads `netbox.settings.PLUGINS_CONFIG["netbox_proxbox"]`
at import time and:

1. Falls back to `ProxboxConfig.default_settings` for missing keys.
2. Builds the Proxmox session: if `token_value` is non-empty, uses token
   auth (`plugins_config.py:125–156`); otherwise falls back to
   username + password.
3. Builds the NetBox session via `pynetbox.api()` with a
   `requests.Session()` whose `verify = False` is set unconditionally
   (`plugins_config.py:165`). A `# TODO: CREATES SSL VERIFICATION -
   Issue #32` comment sits at line 161.

Sessions are module-level singletons. Because `netbox_proxbox/__init__.py:52`
unconditionally imports `proxbox_api`, **NetBox process boot fails with
`RuntimeError` if either Proxmox or NetBox is unreachable**.

### 7.3. Entry point — `update.all()` (`update.py:433`)

1. `proxmox.cluster.status.get()` for cluster + node summary.
2. `create.virtualization.cluster()` to upsert the NetBox cluster row.
3. For each node: `update.nodes(proxmox_json=..., proxmox_cluster=...)`.
4. For each VM from `proxmox.cluster.resources.get(type='vm')`:
   `update.virtual_machine(proxmox_json=...)`.
5. Optionally `remove.all()` to delete stale VMs.

### 7.4. VM sync flow — `update.virtual_machine()` (`update.py:129`)

1. **Search Proxmox** by priority: NetBox `local_context.proxmox.id` →
   `proxmox_id` custom field → name.
2. **Search NetBox** via `nb.virtualization.virtual_machines.get(name=...)`.
3. **Verify** the VM has the "Proxbox" tag (collision guard).
4. If found, run `vm_full_update()`:
   - `updates.virtual_machine.status()` — `running` → `active`,
     `stopped` → `offline`.
   - `updates.virtual_machine.custom_fields()` — writes `proxmox_id`,
     `proxmox_node`, `proxmox_type` via raw HTTP `PATCH` (a comment at
     line 155 calls out that pynetbox could not do this directly).
   - `updates.virtual_machine.local_context_data()` — writes a `proxmox`
     key holding name, URL, id, node, type, memory(GB), disk(GB), vcpu.
   - `updates.virtual_machine.resources()` — `vcpus`, `memory` (MB),
     `disk` (GB).
   - `updates.virtual_machine.interfaces()` (line 288) — for QEMU pulls
     `proxmox.nodes(node).qemu(vmid).config.get()` and parses keys
     matching `^net*`; for LXC, the LXC equivalent. Compares by MAC.
     If `mtu == 1`, resolves the MTU from the node’s bridge interface
     in NetBox (line 317).
   - `updates.virtual_machine.interfaces_ips()` (line 372) — for QEMU,
     uses the qemu-guest-agent (`agent.get('network-get-interfaces')`)
     when `agent` is set in config; for LXC, parses `ip=`/`ip6=` from
     the `net*` config strings. Compares by MAC→IP mapping.
   - `updates.extras.tag()` — ensures the "Proxbox" tag.
5. If not found, calls `create.virtualization.virtual_machine()` then
   runs `vm_full_update()`.

### 7.5. Node sync flow — `update.nodes()` (`update.py:336`)

1. Look up by name in `nb.dcim.devices`.
2. If missing, call `create.dcim.node()` — creates manufacturer,
   device_type, site, device_role first (defaulting to "Proxbox Basic
   …" names unless IDs are configured).
3. If existing, verify the "Proxbox" tag and run `node_full_update()`:
   `updates.node.status` (online/offline), `updates.node.cluster`,
   `updates.node.interfaces` (eth, OVSBond `bond`, OVSIntPort
   `virtual`, OVSBridge `bridge`, with VLAN tagging).

### 7.6. Removal — `remove.all()`

Iterates every NetBox VM via `nb.virtualization.virtual_machines.all()`.
For each, `is_vm_on_proxmox()` compares by name and `local_context`
proxmox id. If absent on Proxmox **and** the VM carries the "Proxbox"
tag, calls `netbox_obj.delete()`. Untagged VMs are never deleted.

### 7.7. Duplicate handling

When v1 finds a VM or node in NetBox without the "Proxbox" tag, it
appends `" (2)"` to the name and creates a new object alongside the
existing one rather than overwriting. The behaviour is deliberate (the
plugin treats untagged objects as operator-managed) but produces
ever-growing `" (2)" / " (3)"` chains on noisy environments.

---

## 8. The v2 Sync Engine — `proxbox_api_v2/`

The active production path. Async, multi-cluster, Django-ORM-based.

### 8.1. Entry point

```bash
python manage.py proxboxscrapper
```

(`netbox_proxbox/management/commands/proxboxscrapper.py:25`)

The command takes no arguments (`add_arguments` is an empty stub) and
calls `asyncio.run(Scrapper.async_run())`. A synchronous fallback
`Scrapper.run()` exists (`scrapper.py:135`) but is commented out in the
handler.

The shell wrapper `proxbox_runner.sh` (30 lines) probes three
candidate `manage.py` paths under `/opt/netbox/` and invokes the
command; it accepts but ignores positional `<tenant>` arguments
(leftover from the removed port-scanner).

### 8.2. `Scrapper.async_run()` (`scrapper.py:88`)

```
        ┌──────────────────────────────────────────┐
        │  job_id = str(uuid.uuid4())              │
        └──────────────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────────┐
        │  get_all_clusters()                      │
        │  asyncio.gather over PROXMOX_SESSIONS    │
        │  -> [ProxmoxCluster, ...]                │
        │     each upserts the NetBox Cluster      │
        └──────────────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────────┐
        │  get_all_nodes(clusters)                 │
        │  for each cluster: build ProxmoxNodes    │
        │  asyncio.gather node.async_get_node_     │
        │  network() across all nodes              │
        │  each calls upsert_nodes()               │
        └──────────────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────────┐
        │  get_all_vms(clusters, nodes)            │
        │  for each cluster: cluster.resources.get │
        │  (type='vm'); skip template==1; batches  │
        │  of 5 VMs through asyncio.gather calling │
        │  vm.async_add_vm_to_netbox() ->          │
        │  upsert_proxbox_item()                   │
        └──────────────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────────┐
        │  ProxmoxVirtualMachine.async_clear_vms   │
        │  raw SQL: latest_job <> current job_id   │
        │  -> delete_vm() for each stale row       │
        └──────────────────────────────────────────┘
```

### 8.3. `ProxboxSession` (`proxbox_session.py`)

Dataclass holding one Proxmox + NetBox configuration set. Defaults
include `token_value: str = '039az154-23b2-4be0-8d20-b66abc8c4686'`
(harmless as a dataclass default but notable — see §13). Constructor
calls `ProxmoxAPI(...)` to open the live Proxmox session.

`get_list_from_file(file_path)` (`proxbox_session.py:130–158`):

1. Reads the JSON file.
2. Calls `mix_proxmox_netbox_config()` to merge the shared `netbox`
   block into every `proxmox[]` entry.
3. Returns a list of `ProxboxSession` instances.

The result list is what `proxbox_api_v2/plugins_config.py` exports as
`PROXMOX_SESSIONS_LIST` and `PROXMOX_SESSIONS`. The `QUEUE_NAME`
constant (`plugins_config.py:27`) is defined but never read anywhere in
the codebase.

### 8.4. Per-stage handlers

#### Cluster — `nb_cluster.upsert_cluster()` (53 lines)

Get-or-create on `(name, type)` — the cluster type is upserted by
`nb_cluster_type.upsert_cluster_type()` first. (See §13 for the
`DoesNotExist` bug in the latter.)

#### Site / manufacturer / device type / role

Helper modules `nb_site.py` (82 lines), `nb_manufactorer.py` (51 lines —
note misspelling), `nb_device_type.py` (69 lines), `nb_device_role.py`
(93 lines). All are simple get-or-create routines with default values
sourced from the merged config.

#### Nodes — `nb_nodes.upsert_nodes()` (374 lines)

1. `find_node_by_ip()` — uses PostgreSQL’s `HOST()` function on
   `IPAddress.address` to resolve a `Device` by node IP.
2. Falls back to `Device.objects.filter(name=node.name).first()`.
3. If `create_device_when_not_found` is `False`, skips creation.
4. `create_node()` creates the `Device` with role / device_type / site
   / cluster, applies the "Proxbox" tag.
5. `node_full_update()`: status, cluster, role, device_type
   manufacturer (refreshed if still on the "Proxbox Basic
   Manufacturer" placeholder), `interface_ip_assign()` to create a
   `bond0` interface and assign the CIDR-normalised IP (defaulting to
   `/32` or `/128` if Proxmox does not provide a prefix).

#### Plugin shadow record — `nb_proxbox.upsert_proxbox_item()` (220 lines)

1. Fetches the VM config from Proxmox (`qemu(vmid).config.get()` /
   `lxc(vmid).config.get()`) with a 3-attempt retry and 2-second sleep.
2. Looks up `ProxmoxVM` by `(domain, proxmox_vm_id)` then by
   `(domain, name)`.
3. Creates or updates the `ProxmoxVM` row — sets `latest_job`,
   `latest_update`, resources, cluster FK, device FK, `instance_data`
   and `config_data` JSON blobs.
4. Calls `upsert_netbox_vm(proxmox_vm, config)`.

#### NetBox VM — `nb_virtualmachine.upsert_netbox_vm()` (`nb_virtualmachine.py` is 942 lines, the largest file in the project)

1. Look up by `(cluster_id, custom_field_data__proxmox_id,
   proxmox_node)` first, then by `(cluster_id, name__iexact)`.
2. Create the `VirtualMachine` if missing.
3. Set `status`, `cluster`, `name`, custom fields (`proxmox_id`,
   `proxmox_node`, `proxmox_type`), `local_context_data`, resources.
4. `base_add_configuration()` — apply tenant assignment via regex
   match against `NETBOX_TENANT_REGEX_VALIDATOR`; parse the
   description field for `client: <name> (<id>)` and `email:
   <addr>` patterns to assign tenants and create contacts.
5. `update_vm_role()` — pin role to `"VPS"` for QEMU or `"LXC"` for
   LXC (overrides the configured `virtualmachine_role_name`).
6. `base_add_ip()` — read `ipconfig0` from the QEMU config or `net0`
   from the LXC config; extract `ip=` and `ip6=` via regex; also look
   for `main ip:` and `ip address allocation:` patterns in the VM
   description; create `IPAddress` rows and assign them to a
   synthetic `eth0` interface.
7. Apply the "Proxbox" tag and the EdgeUno `base_tag()` (either
   `tenant_name` tag or "Customer" tag based on the regex outcome).
   `dedupe_vm_tagged_items()` first removes any duplicate M2M tag
   associations.

Finally, `ProxmoxVM.virtual_machine` is linked back to the new
`VirtualMachine` row.

### 8.5. Stale-VM cleanup

`ProxmoxVirtualMachine.async_clear_vms(job_id)` runs raw SQL via
`others/db.namedtuplefetchall` to find `netbox_proxbox_proxmoxvm` rows
whose `latest_job` does not equal the current run’s UUID. For each
stale row, `nb_virtualmachine.delete_vm()` runs:

1. Confirms the linked VM has the "Proxbox" tag.
2. Calls `get_proxmox_config()` to re-check the VM still exists on
   Proxmox.
3. If the config returns `None`, calls `full_vm_delete()`: nulls
   `ProxmoxVM` FKs, deletes the `ProxmoxVM`, then deletes the
   `VirtualMachine`.
4. If the config is present but the `ProxmoxVM` record was missing
   (race), recreates the `ProxmoxVM` and updates `latest_job` so the
   row survives the next run.

### 8.6. Tag system (`nb_tag.py`, 137 lines)

- Base "Proxbox" tag (color `ff5722`) on every synced object.
- `base_tag()` applies either the `NETBOX_TENANT_NAME` tag or the
  literal "Customer" tag based on whether the VM name matches
  `NETBOX_TENANT_REGEX_VALIDATOR`.
- `custom_tag()` is a generic get-or-create.
- `dedupe_vm_tagged_items()` removes duplicate M2M tag rows before
  applying tags (a defensive measure for environments where prior
  syncs left dup rows).

### 8.7. v1 ↔ v2 isolation

The two engines share **no code**. v1 writes via pynetbox HTTP; v2
writes via the Django ORM. Both can independently create
`VirtualMachine` rows. Running both in the same NetBox install can lead
to conflicts; the EdgeUno deployment relies on v2 exclusively, and the
v1 path remains only because the "Full Update" UI button still calls
into it.

---

## 9. Standalone & Containerised Runtime

### 9.1. Three entry points

| Entry point | What it runs | When to use |
|---|---|---|
| `proxbox_runner.sh` | `python manage.py proxboxscrapper` | Cron jobs, ad-hoc runs |
| `docker-compose-single-exec.yml` | a one-shot container that runs the management command and exits | CI runs, manual sync from a clean container |
| `docker-compose.yaml` + `scanner_scheduler.py` | a long-running scheduler with four modes | Production deployments |

### 9.2. `proxbox_runner.sh` (30 lines)

1. Accepts `<tenant>` arguments but does not pass them through (vestige
   of the removed port-scanner).
2. Searches three candidate paths for `manage.py`:
   `/opt/netbox/netbox/netbox/manage.py`,
   `/opt/netbox/netbox/manage.py`, etc.
3. Runs `/opt/netbox/venv/bin/python "$MANAGE_PY" proxboxscrapper`.

### 9.3. Docker images and compose files

The `Dockerfile` (51 lines):

1. `FROM python:3.12-slim` (overridable via `--build-arg PYTHON_IMAGE`).
2. Installs `build-essential ca-certificates curl libjpeg62-turbo-dev
   libmagic-dev libpq-dev unzip zlib1g-dev`.
3. Downloads the NetBox release at `ARG NETBOX_VERSION=4.5.8`
   (`https://github.com/netbox-community/netbox/archive/refs/tags/v${NETBOX_VERSION}.zip`),
   extracts to `/opt/netbox/netbox/`, and installs NetBox’s own
   `requirements.txt` plus `croniter`.
4. Copies the plugin (`setup.py`, `pyproject.toml`, `MANIFEST.in`,
   `README.md`, `netbox_proxbox/`), the runner shell scripts
   (→ `/usr/local/bin/`), and the scheduler Python script (→ `/usr/local/bin/`).
5. Runs both `pip install -e .` and `python setup.py install` (line 49).
6. Working directory at end: `/opt/netbox/netbox`.

There is no `CMD` or `ENTRYPOINT` — the compose files define them.

#### `docker-compose.yaml` — long-running scheduler

| Key | Value |
|---|---|
| Service | `proxbox-runner` |
| Command | `/usr/local/bin/scanner-runner.sh` |
| Restart | `unless-stopped` |
| Volumes (read-only) | `./runtime/configuration.py` → NetBox `configuration.py`; `./runtime/scanner.env` → `/opt/netbox/runtime/scanner.env`; `./configuration_options.json` → plugin config; `netbox-media` named volume |
| Env | `PROXBOX_CONFIG_FILE=/opt/netbox/runtime/scanner.env` |

`scanner-runner.sh` (5 lines) just `exec`s the scheduler Python script.

#### `docker-compose-single-exec.yml` — one-shot

| Key | Value |
|---|---|
| Service | `proxbox-single-exec` |
| Command | `cd /opt/netbox/netbox/netbox/ && /opt/netbox/venv/bin/python manage.py proxboxscrapper` |
| Restart | not set — the container exits when the sync completes |
| Volumes | only `configuration.py` and `configuration_options.json`; no `scanner.env` |

### 9.4. The scheduler — `scanner_scheduler.py` (210 lines)

Reads its own configuration from one of:
`PROXBOX_CONFIG_FILE`, `SCANNER_CONFIG_FILE`, or
`/opt/netbox/runtime/scanner.env`. Reads the NetBox `configuration.py`
to extract `DATABASE` and `REDIS` blocks.

#### Dependency wait

Polls PostgreSQL and **both** Redis databases (tasks + caching) via TCP
sockets until reachable. Constants: `WAIT_TIMEOUT_SECONDS = 300`,
`WAIT_POLL_SECONDS = 2`. Aborts after five minutes.

#### Mode dispatch

| `PROXBOX_MODE` | Behaviour |
|---|---|
| `off` | Enter `time.sleep(3600)` loop forever — container stays alive but does nothing (this is the default in `runtime/scanner.env.example`) |
| `continuous` | Run `proxbox_runner.sh`; loop immediately (optionally sleep `PROXBOX_RESTART_DELAY_SECONDS`) |
| `interval` | Run `proxbox_runner.sh`, then sleep `PROXBOX_INTERVAL_SECONDS` (default 900) |
| `cron` | Use `croniter(PROXBOX_CRON_EXPRESSION)` to compute the next run time; sleep until then |

`run_scanner_once()` (`scanner_scheduler.py:111–121`) shells out to
`subprocess.run(["/usr/local/bin/proxbox_runner.sh"])` — so the
scheduled path still goes through the shell wrapper into the
management command.

#### Scheduler env vars

| Variable | Purpose |
|---|---|
| `PROXBOX_MODE` (alias: `SCANNER_MODE`) | `off` / `continuous` / `interval` / `cron` |
| `PROXBOX_INTERVAL_SECONDS` | Interval mode delay (default 900) |
| `PROXBOX_CRON_EXPRESSION` | Cron mode schedule |
| `PROXBOX_RESTART_DELAY_SECONDS` | Optional gap between continuous-mode iterations |
| `PROXBOX_CONFIG_FILE` / `SCANNER_CONFIG_FILE` | Path to the env file |
| `NETBOX_CONFIGURATION_FILE` | Path override for `configuration.py` |
| `TIME_ZONE` | Read by `models.py:31` |

Note that **none of these env vars affect the JSON config**. Multi-cluster
configuration is JSON-only.

---

## 10. Documentation Site

`mkdocs.yml` (108 lines) configures a Material-themed site at
`https://proxbox.netbox.dev.br/` (CNAME committed at the repo root).
Plugins: `search`, `social`. Light/dark theme toggle.

### 10.1. Page list

Every documentation page is a **stub** — a one-line file containing
only the H1 heading. There is no body content anywhere.

| Page title | File | Status |
|---|---|---|
| Introduction | `docs/introduction.md` | stub |
| Installing Proxbox | `docs/installation/index.md` | stub |
| Upgrading Proxbox | `docs/installation/upgrading.md` | stub |
| Virtual Machine (VM) | `docs/features/virtual-machine.md` | stub |
| Containers (LXC) | `docs/features/containers.md` | stub |
| Network (IPAM) | `docs/features/network.md` | stub |
| VLAN Management | `docs/features/vlan-management.md` | stub |
| Storage | `docs/features/storage.md` | stub |
| Backup | `docs/features/backup.md` | stub |
| Monitoring | `docs/features/monitoring.md` | stub |
| Synchronized Data | `docs/features/synchronized-data.md` | stub |
| Background Jobs | `docs/features/background-jobs.md` | stub |
| API & Integration | `docs/features/api-integration.md` | stub |
| Configuring ProxBox | `docs/configuration/index.md` | stub |
| Required Parameters | `docs/configuration/required-parameters.md` | stub |
| Virtual Machine (Data Model) | `docs/models/virtual-machine.md` | stub |
| Containers (Data Model) | `docs/models/containers.md` | stub |
| Others | `docs/models/others.md` | stub |
| Release Notes Summary | `docs/release-notes/index.md` | stub |
| Versions 0.0.1 – 0.0.6 | `docs/release-notes/version-0.0.{1..6}.md` | all stubs |

### 10.2. Defects in the docs config

- `mkdocs.yml` `nav:` (lines 104–108) maps **every** release-notes
  entry (0.0.1 through 0.0.6) to `docs/release-notes/version-0.0.1.md`,
  even though the other files exist on disk.
- A second `mkdocs.yml` lives at `docs/mkdocs.yml`; it is the older
  upstream config and is **not** the one used by the live site.

The README (`README.md`, 556 lines) is the only substantive prose
documentation in the repository.

---

## 11. Dependencies

### 11.1. Runtime — `pyproject.toml` (`pyproject.toml:12–17`)

| Package | Pin |
|---|---|
| `python` | `^3.8` |
| `pynetbox` | `^7.0.1` |
| `proxmoxer` | `^2.0.1` |
| `requests` | `>=2` |
| `pytz` | `*` |

`pynetbox` is used only by the v1 `proxbox_api/plugins_config.py`. The
v2 path goes through Django ORM and never opens a pynetbox session.

### 11.2. Runtime — `setup.py` (broader, includes vestiges)

```python
requires = [
    'poetry', 'invoke', 'numpy', 'matplotlib',
    'requests>=2', 'pynetbox>=5', 'paramiko>=2',
    'proxmoxer>=1', 'pytz'
]
```

`numpy`, `matplotlib`, and `paramiko` are leftovers from the removed
port-scanner sub-project (commit `437f8fc`, "Clean up the portscanner
part of the project because it was spin in its own project"). No
current code in `netbox_proxbox/` imports them.

### 11.3. Implicit Dockerfile-only — `croniter`

`croniter` is `pip install`ed inside the Dockerfile (line 35) but is
**not declared** in either `pyproject.toml` or `setup.py`. It is
required only when running the scheduler in `cron` mode. A non-Docker
install will lack `croniter` unless the operator installs it manually.

### 11.4. Dev tooling — `pyproject.toml` (`[tool.poetry.dev-dependencies]`)

`bandit ^1.7.0`, `black ^20.8b1`, `invoke ^1.5.0`, `pylint ^2.7.4`,
`pylint-django ^2.4.3`, `pydocstyle ^6.0.0`, `yamllint ^1.26.1`.
`setup.py` also lists `pytest>=3.7` in `dev_requires`, but **no test
suite exists in the repository** (see §12).

### 11.5. CI

Two GitHub workflows under `.github/workflows/`:

| Workflow | Trigger | Python | Action |
|---|---|---|---|
| `ci.yml` | push to `develop` | 3.6 / 3.7 / 3.8 | `flake8` only |
| `python-package.yml` | push to `main` | 3.7 / 3.8 | `flake8` only |

Neither runs tests, type checks, or Docker builds.

---

## 12. Operational Notes

- **Sessions are opened at Django startup.** Because
  `netbox_proxbox/__init__.py` imports `proxbox_api`, every NetBox
  worker boot attempts a live Proxmox + NetBox connection. Network
  outages at boot translate into worker boot failures.
- **NetBox SSL is unconditionally disabled in v1.** `requests.Session`
  has `verify = False` regardless of any operator setting
  (`proxbox_api/plugins_config.py:165`).
- **Scheduler default is `off`.** `runtime/scanner.env.example` ships
  with `PROXBOX_MODE=off` so the long-running container is inert until
  an operator opts in.
- **Multi-cluster config is JSON-only.** No environment-variable
  substitution is performed inside `configuration_options.json`. The
  scheduler env vars affect only the cadence of runs.
- **No test suite.** No `tests/` directory, no `test_*.py` files, no
  `conftest.py`. CI runs `flake8` only.
- **Logging is `print()`-based.** The v1 `update.py` mixes Python
  `logging` and `print()`; the entire v2 codebase uses `print()` with
  `logging` imports that have been commented out everywhere. Captured
  output ends up on the management-command stdout.
- **Mandatory pre-existing custom fields.** The operator must create
  `proxmox_id`, `proxmox_node`, `proxmox_type`, and (for v1) the
  optional `proxmox_keep_interface` custom fields on
  `virtualization.virtualmachine` before any sync runs (§6.8).
- **Duplicate-name behaviour.** When v1 finds an untagged collision, it
  appends `" (2)"` to the name and creates a new object — over time
  this can produce `" (3)" / " (4)"` chains in environments with
  manual edits.
- **Stale VM cleanup is per-run.** Only v2 prunes — and only objects
  that carry the "Proxbox" tag and whose `ProxmoxVM.latest_job` does
  not match the current run.
- **Document site is structurally complete but textually empty.**
  Operators should rely on the README and this reference, not on
  `https://proxbox.netbox.dev.br/`.

---

## 13. Known Issues & Quirks

This list is mechanical and exhaustive — every item below was verified
against the source.

| # | Issue | Where |
|---|---|---|
| 1 | Plugin self-reports version `0.0.5` in `PluginConfig.version` while `setup.py` and the latest git tag both say `0.1.0` | `__init__.py:11` vs `setup.py` vs `git tag` |
| 2 | `QUEUE_NAME = 'netbox_proxbox.netbox_proxbox'` is defined but never read anywhere | `proxbox_api_v2/plugins_config.py:27` |
| 3 | `ProxmoxVMFilterForm.node` is declared as `forms.IntegerField`, but `ProxmoxVM.node` is a `CharField` — the filter never matches | `forms.py:49` |
| 4 | URL `proxbox/changelog/<int:pk>` is mapped to `ProxmoxVMEditView` instead of a changelog view; a `# TODO<javier Ruiz>` acknowledges it | `urls.py:32` |
| 5 | `nb_cluster_type.upsert_cluster_type()` uses `ClusterType.objects.get(...)` (raises `DoesNotExist`) before its `if cluster_type_proxbox is None` check — the check is dead code | `netbox_handler/nb_cluster_type.py:21` |
| 6 | `default_settings` and the `ProxboxSession` dataclass default both contain a hardcoded example token (`039az154-23b2-4be0-8d20-b66abc8c4686`) | `__init__.py:23–25,31`; `proxbox_session.py:15` |
| 7 | `templatetags/plugin_helpers.py` uses `eval(f'model.{param}')` to resolve dynamic field names | `templatetags/plugin_helpers.py:85` |
| 8 | `proxbox_api/__init__.py` has every import commented out — the module exports nothing, and the `from . import proxbox_api` in the plugin `__init__.py` only triggers the side effects of `plugins_config.py` | `proxbox_api/__init__.py` |
| 9 | `proxbox_api/update.py` retains an `if __name__ == "__main__":` block from the pre-plugin standalone-script era | `proxbox_api/update.py:497–503` |
| 10 | `example.py` is a committed Python literal containing roughly 50 historical VM names from a real sync run | `netbox_proxbox/example.py` |
| 11 | `proxbox_runner.sh` retains a comment `# Example: ./portscanner_runner.sh` from the removed sub-project | `proxbox_runner.sh` |
| 12 | `runtime/scanner.env.example` ships with `PROXBOX_MODE=off` as the default | `runtime/scanner.env.example` |
| 13 | `update_result.html` and `virtualmachine_proxmox_fields.html` are templates that no view references | `netbox_proxbox/templates/netbox_proxbox/` |
| 14 | `views.ProxmoxVMListView` contains a stray `print("test")` | `views.py:130` |
| 15 | `forms.ProxmoxVMForm` docstring incorrectly says "BgpPeering" (copy-paste artefact) | `forms.py` |
| 16 | NetBox SSL verification is hardcoded `False` in v1 | `proxbox_api/plugins_config.py:165` (`# TODO: CREATES SSL VERIFICATION - Issue #32` at line 161) |
| 17 | `ProxmoxVM` model has fields not covered by any `AddField` migration (`domain`, `url`, `latest_job`, `latest_update`, `instance_data`, `config_data`); a `makemigrations` on a fresh install is needed | `models.py` vs `migrations/` |
| 18 | `croniter` is required by `cron` mode but absent from both `pyproject.toml` and `setup.py` — installed only by the Dockerfile | `Dockerfile:35` |
| 19 | `mkdocs.yml` `nav:` points every release-notes entry to `version-0.0.1.md` | `mkdocs.yml:104–108` |
| 20 | `SyncTask.save()` is overridden but the override body is commented out; `SyncTask` itself has no callers in the active codebase | `models.py:347–353` |
| 21 | `HomeView` declares no `PermissionRequiredMixin` — any authenticated user can render the configuration dump | `views.py:27` |
| 22 | `nb_manufactorer.py` uses the misspelled module name | `proxbox_api_v2/netbox_handler/nb_manufactorer.py` |
| 23 | The "Full Update" UI button runs `update.all(remove_unused=True)` synchronously inside the request/response cycle — the worker is blocked for the duration of the full sync | `views.py:50` |
| 24 | The `django_queues` branch is referenced in git history but never merged; `SyncTask` and `QUEUE_NAME` are residue from that abandoned attempt | git branch listing |

---

## 14. Glossary

- **`ProxmoxVM`** — the plugin’s own join-table model. One row per
  Proxmox VM seen on a given cluster, linking a NetBox `VirtualMachine`
  to a `Cluster`, a `Device` (the hypervisor), and the raw Proxmox JSON
  payloads.
- **`SyncTask`** — model designed to track sync-run lifecycle. Carries
  `task_type` (a 20-value enum from `TaskTypeChoices`) and `status`
  (`TaskStatusChoices`). Currently dormant: nothing in the active
  codebase writes to it.
- **`proxboxscrapper`** — Django management command at
  `netbox_proxbox/management/commands/proxboxscrapper.py`. Wraps
  `asyncio.run(Scrapper.async_run())`.
- **`Scrapper`** — orchestrator class in
  `proxbox_api_v2/scrapper.py`. Owns the four-stage async pipeline:
  clusters → nodes → VMs → stale-VM cleanup.
- **`ProxboxSession`** — dataclass in
  `proxbox_api_v2/proxbox_session.py`. Holds one Proxmox + NetBox
  configuration set, opens the live Proxmox session in `__init__`.
- **`PROXMOX_SESSIONS_LIST` / `PROXMOX_SESSIONS`** — module-level
  exports from `proxbox_api_v2/plugins_config.py`. List form is iterated
  by `Scrapper`; dict form is keyed by `domain` for direct lookup.
- **`PLUGINS_CONFIG.filePath`** — the only key NetBox’s
  `configuration.py` needs to set. It points at
  `configuration_options.json`, which holds every Proxmox cluster and
  the shared NetBox settings.
- **`latest_job`** — a stringified UUID stored on `ProxmoxVM` rows to
  identify the v2 sync run that last touched a row. The cleanup stage
  uses raw SQL to find rows whose `latest_job` differs from the current
  run’s UUID and deletes the underlying VMs.
- **`PROXBOX_MODE`** — env var read by `scanner_scheduler.py`.
  Selects between `off`, `continuous`, `interval`, and `cron` runtime
  modes. Default `off`.
- **"Proxbox" tag** — the marker tag (color `ff5722`) attached to every
  synced object. Used as a guard against name collisions with
  operator-managed objects: only tagged objects are ever updated or
  removed.
- **`base_tag()`** — EdgeUno-specific tag function that applies the
  configured `tenant_name` tag or the literal "Customer" tag based on
  whether the VM name matches `tenant_regex_validator`.

---

*End of reference.*
