# `netbox-proxbox` (this repo) vs EdgeUno fork — Side-by-Side Reference

> Companion doc to
> [`EDGEUNO-NETBOX-PROXMOX.md`](./EDGEUNO-NETBOX-PROXMOX.md), which is
> the standalone deep-dive on the EdgeUno fork. This file compares that
> fork to the current upstream pair (`netbox-proxbox 0.0.15` plus
> sibling backend `proxbox-api 0.0.11`) on every axis a contributor or
> operator might care about.
>
> Source revisions:
> - `netbox-proxbox` `0.0.15` (this repo, `v0.0.15` branch). Paired
>   with `proxbox-api 0.0.11` at `/root/nms/proxbox-api/`. Plugin
>   declares `min_version = "4.5.8"` / `max_version = "4.6.99"` in
>   [`netbox_proxbox/__init__.py`](../netbox_proxbox/__init__.py).
> - **EdgeUno** fork at `/root/nms/edgeuno/netbox-proxbox/`. Default
>   branch `develop`. Latest tag `0.1.0` but `PluginConfig.version`
>   still reports `0.0.5`; latest migration
>   `0016_auto_20220726_2003`. Maintained by Javier Alejandro Ruiz
>   (`javier.ruiz@edgeuno.com`).
>
> Both projects share an upstream ancestor in
> `netdevopsbr/netbox-proxbox`. They have not exchanged commits since
> EdgeUno diverged. Both still use the Python module name
> `netbox_proxbox` — they cannot be installed in the same NetBox at
> the same time.

---

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [TL;DR](#2-tldr)
3. [Project Identity at a Glance](#3-project-identity-at-a-glance)
4. [Mental Models](#4-mental-models)
5. [Architecture Diagrams](#5-architecture-diagrams)
6. [Comprehensive Feature Comparison](#6-comprehensive-feature-comparison)
7. [Code Pattern Comparison](#7-code-pattern-comparison)
8. [Operational Verb Coverage Matrix](#8-operational-verb-coverage-matrix)
9. [When to Use Which](#9-when-to-use-which)
10. [Compatibility & Coexistence](#10-compatibility--coexistence)
11. [Migration & Diverged-Lineage Notes](#11-migration--diverged-lineage-notes)
12. [Glossary](#12-glossary)
13. [Cross-Reference Index](#13-cross-reference-index)

---

## 1. Purpose & Scope

`netbox-proxbox` (this repo, paired with `proxbox-api`) and the EdgeUno
fork both started from the same `netdevopsbr/netbox-proxbox` lineage and
both end up doing roughly the same job in operator language: "import
Proxmox state into NetBox so I don't have to keep two inventories in
sync by hand." But they took **opposite architectural paths** from the
shared root:

- This repo split the work across **two services** — a NetBox plugin
  (UI, models, settings, RQ jobs, browser-side SSE) and a separate
  FastAPI backend (`proxbox-api`) that holds Proxmox/NetBox connection
  logic, encrypted credentials, and the long-running sync engine. They
  communicate over HTTP / SSE / optional WebSocket with a pinned wire
  contract.
- The EdgeUno fork doubled down on the **single-process** model — the
  entire sync engine lives inside the plugin itself, in two coexisting
  forms (`proxbox_api/` synchronous v1 and `proxbox_api_v2/` async v2),
  configured from an external JSON file and triggered via a Django
  management command (`python manage.py proxboxscrapper`) and / or a
  standalone four-mode scheduler container.

This document is for:

- Contributors who need to know whether a pattern they see in either
  project is reusable, deliberately diverged, or simply old.
- Operators evaluating which integration fits their environment.
- Reviewers checking that this repo's design choices remain intentional
  in light of how a long-running fork solved the same problem.

It is **not** a replacement for either project's standalone reference
doc — it is a focused comparison.

---

## 2. TL;DR

> **`netbox-proxbox 0.0.15` + `proxbox-api 0.0.11`** is a two-service
> Proxmox→NetBox **mirror**: a NetBox plugin (DB-backed endpoints,
> encrypted credentials, ~80 templates, dashboard, settings page,
> Sync-now buttons via template extensions) plus a FastAPI backend that
> does the actual reads/writes through `proxmox-sdk` and `netbox-sdk`.
> Sync is triggered by an RQ `ProxboxSyncJob` on NetBox's `default`
> queue and streams progress back to the plugin as SSE frames.

> The **EdgeUno fork** (`0.1.0` / self-reported `0.0.5`) is a
> single-process Proxmox→NetBox **mirror with EdgeUno-specific
> writes**. The entire sync engine is embedded in the plugin in two
> coexisting forms: the original synchronous `proxbox_api/` triggered
> from a `ProxmoxFullUpdate` Django view, and the newer asynchronous
> `proxbox_api_v2/` driven by a `proxboxscrapper` management command
> and/or a standalone container scheduler with four modes
> (`off|continuous|interval|cron`). Configuration lives in
> `configuration_options.json` on disk; credentials are plaintext;
> NetBox SSL verification is unconditionally disabled in v1.

The headline difference: this repo separates **what to talk to** (DB
records edited in the NetBox UI) from **how to talk to it** (the
backend service that holds connection logic and contract-pinned wire
schemas). The EdgeUno fork keeps everything in one process and one
JSON file.

### Fork lineage

Both projects descend from `netdevopsbr/netbox-proxbox`, but EdgeUno
forked early — its latest migration is dated `2022-07-26` and its
plugin still self-reports version `0.0.5`. This repo continued
forward, gained a separate FastAPI backend, accumulated 23 additional
migrations (latest `0039_pluginsettings_overwrite_ip_address_dns_name`),
moved off `ChangeLoggedModel` to `NetBoxModel`, and certified against
NetBox `4.5.8` → `4.6.99`. There has been no upstream/fork
cross-pollination since divergence — both must be evaluated as
independent products that happen to share a name and a Python module
identifier.

---

## 3. Project Identity at a Glance

| Attribute | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Repository | `emersonfelipesp/netbox-proxbox` + `emersonfelipesp/proxbox-api` | `edgeuno/netbox-proxbox` (fork of `netdevopsbr/netbox-proxbox`) |
| Maintainer | Emerson Felipe | Javier Alejandro Ruiz / EdgeUno |
| License | Apache-2.0 | Apache-2.0 |
| Language | Python 3.12 + Django + Pydantic v2 (plugin); Python 3.11+ + FastAPI + Pydantic v2 (backend) | Python (three disagreeing sources: `pyproject.toml ^3.8`, `setup.py >=3.7`, `Dockerfile python:3.12-slim`) |
| Versioning | SemVer pair: plugin `0.0.15`, backend `0.0.11`, kept in lock-step via `contracts/*.json` | SemVer; latest tag `0.1.0` but `PluginConfig.version = "0.0.5"` (mismatch with `setup.py`) |
| Project shape | NetBox plugin (Django app, `NetBoxModel` subclasses, Pydantic v2 schemas) **plus** required FastAPI sibling | Single NetBox plugin with two embedded sync engines (`proxbox_api/` + `proxbox_api_v2/`) |
| Python plugin module | `netbox_proxbox` | `netbox_proxbox` (identical — see `setup.py:39` and `__init__.py:8`) |
| Companion service | Required: `proxbox-api 0.0.11` (FastAPI + SQLite + Fernet) | None — sync runs inside NetBox's process or a standalone container |
| NetBox compat | `4.5.8` → `4.6.99` (asserted in `netbox_proxbox/__init__.py:124-125`) | `>=4.0.7` for `0.0.12`; `>=3.5.2` for `0.0.11`; `>=3.2.0` for `0.0.4` |
| Proxmox compat | 8.x (validated through `proxbox-api 0.0.11`; QEMU hostname resolution via `agent/get-host-name`) | `>=6.2.0` (per fork README) |
| `netbox-sdk` (backend) | `0.0.8.post1` | N/A (uses `pynetbox` directly inside the plugin in v1; Django ORM in v2) |
| Distribution | PyPI / TestPyPI staged release pipeline (`pip install netbox-proxbox`) | Git clone or PyPI upload of `netbox-proxbox` (same name; mutually exclusive at install time) |
| Test suite | 50-file pytest suite, AST contract tests, schema mirror tests | None (no `tests/` directory) |

---

## 4. Mental Models

### `netbox-proxbox 0.0.15 + proxbox-api 0.0.11` — two-service mirror

The operator's mental loop:

1. Configure a `ProxmoxEndpoint`, `NetBoxEndpoint`, and
   `FastAPIEndpoint` in the plugin UI (DB-backed; encrypted credentials
   live in the backend's Fernet store, not in NetBox).
2. Click **Full Update** in the dashboard, or schedule a recurring
   `ProxboxSyncJob`, or hit a per-object **Sync Now** button.
3. The plugin enqueues a `ProxboxSyncJob` on NetBox's RQ `default`
   queue with `job_timeout=7200s`.
4. The job calls `proxbox-api`'s SSE streaming endpoints with
   `X-Proxbox-API-Key`, advancing through the 12 ordered stages
   (devices → storage → VMs → vm-disks → backups → snapshots →
   interfaces → IPs → routines → replications → task-history).
5. The plugin observes progress, records Pydantic-validated frames
   into the Job log, surfaces results in dashboard cards, and manages
   plugin-specific Django models (`ProxmoxCluster`, `ProxmoxNode`,
   `ProxmoxStorage`, `VMBackup`, `VMSnapshot`, `Replication`,
   `BackupRoutine`, `VMTaskHistory`).
6. As of `0.0.15` / `0.0.11`, the mirror also writes Proxmox guest
   hostnames into IPAM `IPAddress.dns_name`, gated by the
   `overwrite_ip_address_dns_name` flag on `ProxboxPluginSettings` (and
   tri-state per `ProxmoxEndpoint`).

Loss surface: NetBox is a mirror of Proxmox. The plugin never talks to
Proxmox directly; the backend never talks to NetBox over a path the
plugin cannot observe.

### EdgeUno fork — single-process scrapper with EdgeUno writes

The operator's mental loop:

1. Edit `configuration_options.json` (template:
   `configuration_options_default.json`) to list Proxmox clusters and
   the shared NetBox block. Plaintext credentials live here on disk.
2. Reference that file path from
   `PLUGINS_CONFIG['netbox_proxbox']['filePath']` in NetBox's
   `configuration.py`.
3. To run sync, choose one of three entry points:
   - **Web-triggered v1**: open the **Full Update** Django view; the
     synchronous `proxbox_api/` engine runs inside the gunicorn worker,
     calling Proxmox via `proxmoxer` and NetBox via `pynetbox` (with
     `ssl_verify=False` hardcoded). Long sync = held worker.
   - **Management-command v2**: run
     `python manage.py proxboxscrapper`. `Scrapper.async_run` (see
     `proxbox_api_v2/scrapper.py:88`) builds a `ProxboxSession` per
     cluster, fans out asynchronously, and writes NetBox via Django
     ORM directly.
   - **Container scheduler**: deploy `docker-compose.yaml` with the
     `scanner_scheduler.py` entrypoint. Pick a mode via
     `PROXBOX_MODE` (`off|continuous|interval|cron`); `cron` mode uses
     `croniter` (installed in the Dockerfile but not declared in
     `pyproject.toml` or `setup.py`).
4. The scrapper additionally **writes** EdgeUno-specific business
   data: tenant assignment by regex match on VM name
   (`NETBOX_TENANT_REGEX_VALIDATOR`), parsing of `description`-field
   patterns (`client:`, `email:`, `main ip:`,
   `ip address allocation:`), and role pinning to `"VPS"` for QEMU
   guests / `"LXC"` for LXC containers.
5. Stale records are detected by raw SQL against a `latest_job` UUID
   (no Django ORM equivalent in tree).
6. Logging is `print()`-based.

Loss surface: NetBox is a mirror of Proxmox **plus** an EdgeUno-shaped
view on top of it. The plugin reads Proxmox directly and writes NetBox
directly, so any error has only one process to look at — but also only
one process to operate.

---

## 5. Architecture Diagrams

### 5.1. `netbox-proxbox 0.0.15 + proxbox-api 0.0.11`

```
       Operator (NetBox UI / API / pxb CLI)
              │
              ▼  click "Full Update", schedule job, or Sync Now
   ┌──────────────────────────────────────┐
   │              NetBox 4.5+             │
   │  netbox_proxbox plugin               │
   │  ┌─────────────────────────────┐     │
   │  │ ProxboxSyncJob (RQ default) │     │
   │  └─────────────┬───────────────┘     │
   │  Plugin models: ProxmoxCluster,      │
   │  ProxmoxNode, ProxmoxStorage,        │
   │  VMBackup, VMSnapshot, Replication,  │
   │  BackupRoutine, VMTaskHistory        │
   └────────────────┬─────────────────────┘
                    │ HTTP + SSE  (X-Proxbox-API-Key)
                    ▼
       ┌──────────────────────────────────────┐
       │  proxbox-api (FastAPI, v0.0.11)      │
       │  Encrypted credential store (Fernet) │
       │  /admin/encryption (runtime rotate)  │
       │  /settings (runtime tunables, cached)│
       │  netbox-sdk 0.0.8.post1 + proxmox-sdk│
       └─────┬─────────────────────────┬──────┘
             │                         │
   netbox-sdk│                         │proxmox-sdk
             ▼                         ▼
      ┌────────────┐           ┌──────────────┐
      │  NetBox    │           │  Proxmox VE  │
      └────────────┘           └──────────────┘
```

### 5.2. EdgeUno fork

```
       Operator (CLI / Docker / Django view)
              │
              ▼
   ┌────────────────────────────────────────────────┐
   │              configuration_options.json        │
   │  proxmox: [ { cluster, host, user, token, … } ]│
   │  netbox:  { host, token, ssl_verify=False, … } │
   └────────────────────┬───────────────────────────┘
                        │ filePath read at import time
                        ▼
   ┌──────────────────────────────────────────────────┐
   │              NetBox (3.x / 4.0.7+)               │
   │  netbox_proxbox plugin                           │
   │  ┌────────────────────────────────────────────┐  │
   │  │  proxbox_api_v2/  (active, async)          │  │
   │  │  Scrapper.async_run() ──► per-cluster fan  │  │
   │  │   ▼  ProxboxSession (×N clusters)          │  │
   │  │   ▼  upsert_cluster / upsert_nodes /       │  │
   │  │      upsert_proxbox_item / upsert_netbox_vm│  │
   │  │   ▼  Django ORM writes to                  │  │
   │  │      virtualization.VirtualMachine,        │  │
   │  │      ProxmoxVM (shadow), interfaces, IPs   │  │
   │  └────────────────────────────────────────────┘  │
   │  ┌────────────────────────────────────────────┐  │
   │  │  proxbox_api/  (legacy, sync, web-trig)    │  │
   │  │  ProxmoxFullUpdate view ──► update.all()   │  │
   │  │   ▼  pynetbox(ssl_verify=False) +          │  │
   │  │      proxmoxer                             │  │
   │  └────────────────────────────────────────────┘  │
   │  Plugin models: ProxmoxVM, SyncTask (dormant)    │
   └────────────────────────────────────────────────┬─┘
                                                    │
                              ┌─────────────────────┴─────────────────┐
                              ▼                                       ▼
                     ┌──────────────────┐                  ┌──────────────────┐
                     │     NetBox       │                  │   Proxmox VE     │
                     │  (Django ORM     │                  │  (proxmoxer in   │
                     │   in-process)    │                  │   v1; aiohttp    │
                     │                  │                  │   in v2)         │
                     └──────────────────┘                  └──────────────────┘

(Standalone alternative: docker-compose.yaml runs scanner_scheduler.py
 in a sibling container; it dispatches `python manage.py proxboxscrapper`
 in modes off|continuous|interval|cron via the same NetBox process.)
```

The current pair routes every Proxmox call through `proxbox-api` and
every NetBox write through `netbox-sdk`. The EdgeUno plugin makes those
calls itself, in-process, against pynetbox / Django ORM and proxmoxer
/ aiohttp.

---

## 6. Comprehensive Feature Comparison

This is the main artifact. Rows are grouped by category. ✅ = supported,
❌ = not supported, ⚠️ = partial / caveat, 👁️ = observes/syncs only.

### 6.1. Project shape & distribution

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Is it a NetBox plugin? | ✅ Yes (`PluginConfig`, models, views, templates, REST API) | ✅ Yes (`PluginConfig`, models, views, templates, REST API) |
| Required external service | ✅ `proxbox-api` FastAPI service | ❌ None — sync runs in-process or in a sibling container |
| Installable from PyPI? | ✅ `pip install netbox-proxbox` (also TestPyPI staged) | ⚠️ `setup.py` exists (`name="netbox-proxbox"`) but PyPI presence is operator-managed |
| Build system | `hatchling`; `uv.lock` checked in | Poetry (`pyproject.toml`) **and** legacy `setup.py` (superset of deps); both committed |
| Shipped binary scripts | Plugin only; CLI extras: `pxb` (Typer + aiohttp) | `proxbox_runner.sh`, `scanner-runner.sh`, `docker-compose-single-exec.yml`, `docker-compose.yaml` |
| Repo layout | Single repo per service (plugin / backend) | Single repo with two embedded sync engines (`proxbox_api/` + `proxbox_api_v2/`) |

### 6.2. NetBox integration surface

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Django models | ✅ 13 (`ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `ProxmoxCluster`, `ProxmoxNode`, `ProxmoxStorage`, `ProxmoxStorageVirtualDisk`, `BackupRoutine`, `Replication`, `VMBackup`, `VMSnapshot`, `VMTaskHistory`, `ProxboxPluginSettings`) | ⚠️ 2 (`ProxmoxVM` shadow record, `SyncTask` dormant), both still on `ChangeLoggedModel` |
| Base class | `NetBoxModel` | `ChangeLoggedModel` (predates `NetBoxModel`) |
| Migrations | ✅ Latest `0039_pluginsettings_overwrite_ip_address_dns_name` | ⚠️ 16 total; latest `0016_auto_20220726_2003` (dated 2022-07-26) |
| Custom fields | Reads `proxmox_vm_id`, `proxmox_vm_type`, `proxmox_node` (created by `proxbox-api` sync); writes `IPAddress.dns_name` from Proxmox guest hostnames in 0.0.11 | ⚠️ Operator must pre-create `proxmox_id`, `proxmox_node`, `proxmox_type`, `proxmox_keep_interface` manually — sync raises if missing |
| Custom field choice sets | ❌ Not on `extras.custom_field_choice_sets` | ❌ Same |
| Plugin REST API | ✅ `/api/plugins/proxbox/` — 12 model viewsets + 11 non-model views | ⚠️ `/api/plugins/proxbox/` — single `ProxmoxVM` viewset, no full-coverage REST surface |
| Plugin GraphQL API | ❌ Not currently exposed | ❌ Not exposed |
| NetBox UI integration | ✅ Plugin views, dashboard, ~80 templates, Sync-now buttons via `template_extensions` | ⚠️ `ProxmoxFullUpdate` view + `ProxmoxVM` list/detail; `template_content.py` exists but minimal |
| Branching plugin support | ❌ Not used | ❌ Not used |
| Singleton settings model | ✅ `ProxboxPluginSettings` (singleton via `singleton_key="default"`) | ❌ No singleton — every tunable lives in `default_settings` or the JSON file |

### 6.3. Proxmox integration surface

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Direct Proxmox API calls? | ❌ No — all Proxmox traffic flows through `proxbox-api` | ✅ Yes — v1 uses `proxmoxer`, v2 uses `aiohttp` directly |
| Auth | Token or username/password; stored encrypted in backend Fernet store | Token or username/password; plaintext in `configuration_options.json` |
| SSL verification | Configurable per `ProxmoxEndpoint`; SSRF-protected via `ssrf_protection_enabled`; HTTPS scheme decoupled from cert verification (`use_https` + `verify_ssl`) | Per-cluster JSON key; no SSRF protection; NetBox-side SSL verification in v1 is **unconditionally disabled** |
| QEMU VMs | 👁️ Read-only sync (full coverage of disks, IPs, snapshots, backups) | 👁️ Read-only sync (VM, interfaces, IP) |
| LXC containers | 👁️ Read-only sync | 👁️ Read-only sync (with role pinning to `"LXC"`) |
| Snapshots | 👁️ Read-only sync (`VMSnapshot`) | ❌ Not modeled |
| Backups (vzdump files) | 👁️ Read-only sync (`VMBackup`) | ❌ Not modeled |
| Backup routines (vzdump schedules) | 👁️ Read-only sync (`BackupRoutine`) with full retention/advanced fields | ❌ Not modeled |
| Replication jobs | 👁️ Read-only sync (`Replication`) | ❌ Not modeled |
| Task history (UPIDs) | 👁️ Read-only sync (`VMTaskHistory`) | ❌ Not modeled |
| Storage definitions | 👁️ Read-only sync (`ProxmoxStorage`) with NFS/CIFS/Ceph/PBS fields | ❌ Not modeled |
| Cluster discovery | 👁️ Continuous via `proxbox-api` | 👁️ Continuous via `Scrapper.async_run` |
| QEMU `agent/get-host-name` resolution | ✅ **0.0.11**, with fall-back through the network-interfaces payload | ❌ |
| LXC `VMConfig.hostname` resolution | ✅ **0.0.11** | ❌ |
| Console buttons in UI | ✅ VNC / LXC console links via template extensions | ❌ |
| EdgeUno-specific writes | ❌ N/A | ✅ Tenant regex assignment, `description` parsing (`client:` / `email:` / `main ip:` / `ip address allocation:`), role pinning |

### 6.4. Trigger & execution model

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Primary trigger | Manual UI / scheduled RQ job / Sync Now buttons | `ProxmoxFullUpdate` Django view (v1) **or** `python manage.py proxboxscrapper` (v2) **or** `scanner_scheduler.py` container |
| Webhook listener | ❌ None | ❌ None |
| Background scheduler | ✅ `views/schedule_sync.py` enqueues recurring `ProxboxSyncJob` | ✅ `scanner_scheduler.py` (210 lines) with four modes: `off|continuous|interval|cron` |
| `cron` mode | N/A | Implemented via `croniter` — installed in Dockerfile but not declared in `pyproject.toml` or `setup.py` |
| Idempotency | RQ + `sync_ownership.py` claim prevents concurrent duplicates | None — concurrent `proxboxscrapper` runs can race; v1 page can be opened twice |
| Cancellation | ✅ `views/job_cancel.py` (POST, requires `core.delete_job`) | ❌ Kill the container or interrupt the management command |
| Retry | ⚠️ At HTTP layer (`netbox_max_retries`, `netbox_retry_delay`); not at job level | ❌ |
| Holds gunicorn worker? | ❌ No (RQ decouples) | ⚠️ Yes for v1 `ProxmoxFullUpdate`; ❌ for v2 / scheduler |

### 6.5. Concurrency & queueing

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Queue technology | ✅ NetBox RQ `default` queue | ❌ None — v2 uses raw `asyncio` per-cluster fan-out; v1 is synchronous |
| Long-task handling | RQ job with `job_timeout=7200s` + SSE stream `(5, 3600)s` read timeout | Held gunicorn worker (v1) **or** management-command process (v2) |
| Worker count | Standard NetBox RQ worker count | Not applicable (no worker pool) |
| Concurrency tuning | `proxbox_fetch_max_concurrency`, `netbox_max_concurrent`, `netbox_write_concurrency`, `vm_sync_max_concurrency`, `proxmox_fetch_concurrency` — DB-backed `ProxboxPluginSettings` fields since 0.0.15 | ❌ No DB-backed tunables; v2 uses `asyncio.gather` over the `PROXMOX_SESSIONS_LIST` |
| Per-stage concurrency | ✅ Configurable in `ProxboxPluginSettings` | ❌ |
| Settings cache | 5-minute TTL on `proxbox_api/settings_client.py` | N/A |

### 6.6. Configuration & secrets

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Config medium | Django models (DB), editable in NetBox UI; "DB-first" policy codified in `CLAUDE.md` | External JSON file (`configuration_options.json`) referenced from `PLUGINS_CONFIG['netbox_proxbox']['filePath']` |
| Environment variables | ⚠️ Backend uses env only for **pre-DB infra** (`PROXBOX_BIND_HOST`, `PROXBOX_RATE_LIMIT`, `PROXBOX_ENCRYPTION_KEY`/`*_FILE`, `PROXBOX_STRICT_STARTUP`, `PROXBOX_SKIP_NETBOX_BOOTSTRAP`, `PROXBOX_GENERATED_DIR`, `PROXBOX_CORS_EXTRA_ORIGINS`); plugin uses none | ⚠️ Scheduler container only: `PROXBOX_MODE`, `PROXBOX_INTERVAL_SECONDS`, `PROXBOX_CRON_EXPRESSION`, `PROXBOX_RESTART_DELAY_SECONDS`, `PROXBOX_CONFIG_FILE`, `SCANNER_CONFIG_FILE`, `NETBOX_CONFIGURATION_FILE`, `TIME_ZONE`. Plugin itself reads no env. |
| Tunable resolution order | ✅ **0.0.11**: `runtime_settings.get_int/get_float/get_bool/get_str` resolves env var → `ProxboxPluginSettings` → built-in default (5-min cache) | ❌ Single-source: JSON file only |
| Encryption at rest | ✅ `proxbox-api` Fernet with `PROXBOX_ENCRYPTION_KEY`; runtime rotation via `routes/admin/encryption.py` (no restart) | ❌ Plaintext JSON on disk |
| Encryption-key bootstrap | ✅ Non-blocking startup in 0.0.11 — backend no longer hangs if the key store is empty | N/A |
| Per-endpoint config | One `ProxmoxEndpoint` row per cluster; per-endpoint `overwrite_*` flags (**23 in 0.0.15**) with tri-state inheritance | One JSON object per cluster in the `proxmox: [ … ]` array; no overwrite-flag concept |
| Singleton settings | ✅ `ProxboxPluginSettings` (singleton; runtime tunables + `overwrite_ip_address_dns_name`) | ❌ |
| Settings UI | ✅ `views/settings.py` + form; runtime tunables grouped on the Settings tab | ❌ Edit JSON, restart NetBox |
| Settings REST endpoint | ✅ `/api/plugins/proxbox/settings/` (added in 0.0.15) — backend reads it on every cache miss | ❌ |
| `PLUGINS_CONFIG` keys | ⚠️ `required_settings = []`; everything in DB | ⚠️ `filePath` only — points at the JSON file |
| Multi-cluster support | ✅ Multiple `ProxmoxEndpoint` rows | ✅ Multiple entries in the `proxmox: [ … ]` JSON array |
| Hardcoded example token | ❌ | ⚠️ Yes, in `default_settings` (`tokenID` placeholder) |

### 6.7. Authentication

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| NetBox auth | API token (`NetBoxEndpoint`); v1 (raw) or v2 (`token_key` + `token_secret`) | API token in JSON file |
| Proxmox auth | API token or username/password; encrypted at rest in backend; pushed at sync time | API token or username/password in JSON file (plaintext) |
| Plugin ↔ backend auth | `X-Proxbox-API-Key` header; auto-generated `secrets.token_urlsafe(48)` on first save of `FastAPIEndpoint`; registered via `/auth/register-key` | N/A (no separate backend) |
| Brute-force protection | ✅ At backend (`proxbox-api` lockout) | ❌ |
| Bootstrap thread | ✅ Daemon thread `proxbox-startup-endpoint-push` waits 10 s then pushes endpoint data to backend | ❌ |
| Token rotation at runtime | ✅ FastAPIEndpoint regenerates token on save; backend supports runtime encryption-key rotation | ❌ Edit JSON file, restart |
| NetBox SSL verification | Configurable per endpoint | ❌ Hardcoded `ssl_verify=False` in v1's pynetbox session |

### 6.8. Sync direction & coverage

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Primary direction | Proxmox → NetBox | Proxmox → NetBox |
| Reverse direction | Plugin pushes endpoint config to backend (config flow only, not data) | None |
| Sync coverage stages | 12 ordered: `devices → storage → virtual-machines → vm-disks → vm-backups → vm-snapshots → network-interfaces → vm-interfaces → ip-addresses → backup-routines → replications → task-history` | 5 implicit: `clusters → nodes → vms/lxcs → interfaces → ips` |
| Full-update endpoint | ✅ `full-update/stream` (SSE) | ⚠️ `ProxmoxFullUpdate` synchronous Django view (v1); `proxboxscrapper` management command (v2) |
| Per-object sync | ✅ `views/vm_sync_now.py` and `views/sync_now/{cluster,node,storage,vm}.py` | ❌ Re-run the whole scrapper |
| Stale-record cleanup | ⚠️ Through backend reconcile logic | ⚠️ Raw SQL against `latest_job` UUID; `delete_vm` recovery path |
| Writes beyond mirror | ✅ `IPAddress.dns_name` from Proxmox guest hostname (0.0.11, gated by overwrite flag) | ✅ Tenant from name regex; `description` parsing; role pinning |

### 6.9. UI surface

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Custom NetBox UI | ✅ Home page, Dashboard, resource lists, settings page, schedule page, logs page | ⚠️ `Full Update` page, `ProxmoxVM` list/detail, basic forms |
| Sidebar menu | ✅ Three groups: Proxmox Plugin, Endpoints, Join our community | ⚠️ Single `Proxbox` entry |
| Template extensions | ✅ `template_content.py`: Job, VM, Cluster, Node, Storage, VMBackup, VMSnapshot, VMTaskHistory | ⚠️ Minimal `template_content.py` |
| WebSocket UI | ✅ `views/websocket_test/`, `templates/test/websocket.html` | ❌ |
| Live job log streaming | ✅ `views/job_stream.py` (SSE on Job detail page) | ❌ |
| Live cluster cards | ✅ `views/cards.py`, AJAX-hydrated dashboard cards | ❌ |
| Number of templates | ~80 under `templates/netbox_proxbox/` | A handful |

### 6.10. CLI surface

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| CLI shipped | ✅ `pxb` (Typer + aiohttp + Rich) | ⚠️ Django management command `proxboxscrapper` + shell wrappers (`proxbox_runner.sh`, `scanner-runner.sh`) |
| CLI install | `pip install "netbox-proxbox[cli]"` | Run from inside the NetBox process: `python manage.py proxboxscrapper` |
| Config file | `~/.config/proxbox-cli/config.json` | `configuration_options.json` (shared with the plugin) |
| Targets | `proxbox-api` backend (NOT NetBox directly) | NetBox + Proxmox (in-process) |
| Subcommands | `init`, `config`, `test`, `version`, `info`, `cache`, `clear-cache`, `full-update`, `docs`; sub-apps: `netbox`, `proxmox`, `proxbox`, `dcim`, `virtualization`, `extras` | One management command, no subcommands |
| Output formats | Human (Rich), `--json`, `--yaml` | `print()` text only |

### 6.11. REST API surface

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Plugin REST API | ✅ `/api/plugins/proxbox/` | ⚠️ `/api/plugins/proxbox/` exists but is thin |
| Model viewsets | 12 (one per business model) | 1 (`ProxmoxVM`) |
| Non-model views | 11 (Home, Dashboard, Clusters, Nodes, VMs, LXCs, Interfaces, IPs, Disks, Schedule, Logs) | None |
| Token-write fields | `password`, `token_value` are write-only on serializers | N/A |
| OpenAPI doc page | ✅ `templates/netbox_proxbox/fastapiendpoint_openapi.html` mirrors backend OpenAPI | ❌ |

### 6.12. SSE / WebSocket / streaming

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| SSE (server-sent events) | ✅ Major design pillar — `services/backend_proxy.py` streams from `proxbox-api`'s `*/stream` endpoints | ❌ |
| WebSocket | ⚠️ Optional via `FastAPIEndpoint.use_websocket`; `websocket_client.py` | ❌ |
| Frame schema | `contracts/proxbox_api_sse_schema.json` (pinned wire contract) | N/A |
| Frame validation | Pydantic v2 mirror models in `schemas/backend_proxy.py`; validated by `test_sse_schema_mirror.py` | N/A |

### 6.13. Background jobs

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Job framework | ✅ NetBox `JobRunner` (`netbox.jobs`) | ❌ — `SyncTask` model exists but is dormant (remnant of an abandoned `django_queues` branch) |
| Job class | `ProxboxSyncJob` (`netbox_proxbox/jobs.py`) | None |
| Job timeout | 7200 s (2 hours) | N/A |
| HTTP read timeout | 3600 s between SSE chunks | N/A |
| Scheduling | One-shot or recurring (`views/schedule_sync.py`) | One-shot via `proxboxscrapper` or recurring via `scanner_scheduler.py` |
| Cancellation | ✅ `views/job_cancel.py` | ❌ |
| Re-run completed | ✅ `views/job_run.py` | ❌ |
| `QUEUE_NAME` setting | N/A | ⚠️ Declared in `default_settings` but unused (placeholder from the abandoned django-rq experiment) |

### 6.14. Custom fields, choice sets, tags

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Plugin creates `extras.custom_fields`? | ❌ Backend creates them at sync | ❌ Operator must pre-create `proxmox_id`, `proxmox_node`, `proxmox_type`, `proxmox_keep_interface` |
| Plugin creates `extras.custom_field_choice_sets`? | ❌ | ❌ |
| Plugin creates `extras.tags`? | ⚠️ Backend may create discovery tags | ❌ |
| Plugin creates `extras.event_rules`? | ❌ | ❌ |
| Plugin creates `extras.webhooks`? | ❌ | ❌ |
| Custom-field naming | `proxmox_vm_id` | `proxmox_id` (different from this repo) |

### 6.15. Templating / Jinja2

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Jinja2 in webhooks / playbooks | ❌ | ❌ |
| Django templates | ✅ ~80 templates under `templates/netbox_proxbox/` | ⚠️ A handful |
| Template tags | `templatetags/proxbox_tags.py` (e.g. inline-asset rendering) | `templatetags/plugin_helpers.py` — uses `eval()` (see §13 of `EDGEUNO-NETBOX-PROXMOX.md`) |

### 6.16. Tests

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Test framework | ✅ pytest + heavy mocking via `conftest.py` | ❌ No `tests/` directory |
| Test files | 50 (`tests/test_*.py`) | 0 |
| E2E tests | ✅ `tests/e2e/` with Docker stack tests | ❌ |
| AST contract tests | ✅ `test_version.py`, `test_signals.py`, `test_overwrite_flags_contract.py`, etc. | ❌ |
| Coverage tooling | ✅ `pytest-cov`, `coverage.xml`, branch coverage | ❌ |
| Schema mirror tests | ✅ `test_sse_schema_mirror.py`; `test_overwrite_flags_contract.py` | ❌ |
| Committed test fixtures | N/A | ⚠️ `example.py` test fixture committed alongside production code |

### 6.17. CI/CD

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| GitHub Actions | ✅ Multiple workflows | ❌ No `.github/workflows/` content |
| Lint | ✅ `ruff` (lint + format), `bandit`, `ty` | ⚠️ `bandit`, `black`, `pylint`, `pylint-django`, `pydocstyle`, `yamllint` listed as dev deps but no CI runs them |
| Type check | ✅ `ty` on `proxbox_cli` | ❌ |
| E2E matrix | ✅ `e2e-docker.yml`: `install_source × netbox_image × network_stack`, nightly 02:31 UTC | ❌ |
| Release pipeline | ✅ Staged TestPyPI → PyPI lanes (`publish-testpypi.yml`) | ❌ |
| Docs build | ✅ `docs.yml` deploys to GitHub Pages | ⚠️ MkDocs config exists; no automated deploy in tree |
| Screenshot capture | ✅ `docs-screenshots.yml` + Playwright | ❌ |
| Nightly contract refresh | ✅ `nightly-contracts.yml` | ❌ |

### 6.18. Documentation site

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Theme | MkDocs Material (default + deep-orange accent) | MkDocs Material |
| Pages | 60+ across Install / Backend / Configuration / CLI / Developer / API Reference / Features / Data Model / Release Notes / Roadmap | ⚠️ Every page is a stub; nav has every release-note link pointing at `version-0.0.1.md` |
| `mkdocstrings`? | ✅ Python handler + `griffe_typingdoc` | ❌ |
| CNAME / Pages deployment | ✅ Configured | ⚠️ CNAME committed (`proxbox.netbox.dev.br`) but content is placeholder |
| Inline screenshots | ⚠️ Generated via Playwright | ❌ |

### 6.19. Branching, multi-cluster, security

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Branching plugin support | ❌ Not used | ❌ Not used |
| Multi-cluster | ✅ Multiple `ProxmoxEndpoint` rows in one DB | ✅ Multiple JSON entries in `proxmox: [ … ]` |
| SSRF protection | ✅ `ssrf_protection_enabled` toggle, IP allow/blocklist | ❌ |
| Allow private IPs flag | ✅ `allow_private_ips` | ❌ |
| Encryption at rest | ✅ Backend Fernet (`PROXBOX_ENCRYPTION_KEY`) | ❌ Plaintext JSON |
| Encryption-key rotation at runtime | ✅ **0.0.11** — `routes/admin/encryption.py` | ❌ |
| Token rotation in plugin | ✅ FastAPIEndpoint regenerates token on save | ❌ |
| Endpoint misconfig surfacing | ✅ **0.0.15** — `services/_endpoint_errors.py` translates `400 plain HTTP request was sent to HTTPS port` and `SSLError` into operator-actionable messages | ❌ Errors surface as raw `pynetbox` / `proxmoxer` exceptions |

### 6.20. Observability & logging

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Log file | `backend_log_file_path` setting (default `/var/log/proxbox.log`) | ❌ `print()` to stdout |
| Log rotation | ❌ External | N/A |
| Live log UI | ✅ Backend logs page (`views/logs.py`); per-job SSE stream (`views/job_stream.py`) | ❌ |
| Health probes | ✅ `views/keepalive_status.py` (`/keepalive/fastapi/`, NetBox, Proxmox) | ❌ |
| Status badges | ✅ `templates/proxbox-backend-status.html`, status-badge partial | ❌ |
| Inline-asset rendering | ✅ **0.0.15** — home dashboard logos and JS inlined via `templatetags/proxbox_tags.py` so the page works without `collectstatic` (issue #355) | ❌ |
| Structured logging | ⚠️ Backend writes structured logs to file | ❌ |

### 6.21. Roadmap / known issues

| Aspect | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Known limitations | Most operational verbs not yet exposed; sync is mostly observational. The lone write into NetBox-hosted DCIM/IPAM/virtualization is `IPAddress.dns_name` (0.0.11). See `docs/release-notes/version-0.0.15.md`. | 24 documented quirks/bugs/oddities — see [`EDGEUNO-NETBOX-PROXMOX.md` §13](./EDGEUNO-NETBOX-PROXMOX.md#13-known-issues--quirks). Highlights: version mismatch (`0.0.5` vs `0.1.0`), unused `QUEUE_NAME`, `ProxmoxVMFilterForm.node` IntegerField vs CharField, hardcoded example token, `eval()` in templatetags, `nb_cluster_type` `DoesNotExist` bug, no test suite, `print()`-based logging |
| Stated roadmap | `docs/roadmap.md`; 0.0.16 candidates in release notes | None published |

---

## 7. Code Pattern Comparison

Five concrete patterns where the projects diverge most clearly. Each
sub-section is short on purpose — the goal is to make the divergence
*nameable*.

### 7.1. Endpoint persistence — Django models + Fernet vs JSON file + plaintext

**This repo** stores endpoint configuration in Django models
(`ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`), persisted in
NetBox's PostgreSQL. The plugin pushes a derived shape of those
records to `proxbox-api` at sync time, where credentials are encrypted
at rest with Fernet (`PROXBOX_ENCRYPTION_KEY`). Settings are editable
in the NetBox UI.

```python
class FastAPIEndpoint(EndpointBase):
    token = models.CharField(...)  # secrets.token_urlsafe(48) on save
    use_https = models.BooleanField(default=False)
    use_websocket = models.BooleanField(default=False)
```

**EdgeUno** stores everything in a flat JSON file referenced by
`PLUGINS_CONFIG`:

```json
{
  "proxmox": [
    { "domain": "...", "user": "root@pam", "token": { "name": "...", "value": "..." } }
  ],
  "netbox": { "domain": "...", "token": "...", "ssl": false }
}
```

There is no encryption, no UI, and no `os.environ` substitution inside
the JSON. To rotate a credential, an operator edits the file and
restarts NetBox.

### 7.2. Drift detection — typed SDK + contract mirrors vs `update.all()` and Django ORM

**This repo** delegates NetBox writes to `netbox-sdk`'s typed client
(inside `proxbox-api`); the plugin itself owns no `createOrUpdate`
logic. Wire shapes between plugin and backend are pinned by
`contracts/proxbox_api_sse_schema.json` and validated by Pydantic v2
mirror models in `netbox_proxbox/schemas/backend_proxy.py`.

**EdgeUno v1** uses an `update.all()` orchestration in
`proxbox_api/update.py` plus per-resource diff helpers, talking to
NetBox via `pynetbox` with `ssl_verify=False`. Duplicate-name handling
appends a `" (2)"` suffix.

**EdgeUno v2** writes through Django ORM directly inside the plugin
process; stale-record cleanup is implemented as raw SQL against a
`latest_job` UUID written into every upsert.

Neither EdgeUno engine has a wire schema; both consume `proxmoxer` /
aiohttp dicts and pynetbox / Django ORM objects with no validation
layer between the two.

### 7.3. Credential injection — `X-Proxbox-API-Key` vs JSON-on-disk

**This repo** uses an auto-generated bearer-style header:

```python
# FastAPIEndpoint.save() — first run
self.token = secrets.token_urlsafe(48)
super().save(...)
# fired by signal handler:
register_key_with_backend(self.token)  # POST /auth/register-key
```

Subsequent calls send `X-Proxbox-API-Key: <token>`. Token rotation is
a first-class operation (re-save the endpoint).

**EdgeUno** loads JSON at module import and hands creds straight to
`pynetbox.api(...)`:

```python
nb = pynetbox.api(
    PLUGINS_CONFIG['netbox_proxbox']['netbox']['domain'],
    token=PLUGINS_CONFIG['netbox_proxbox']['netbox']['token'],
)
nb.http_session.verify = False  # hardcoded in v1
```

Module-level singletons connect at *Django startup*. There is no
rotation path; restart NetBox.

### 7.4. Long-running tasks — RQ + SSE vs synchronous view + management command

**This repo** decouples receipt from execution. The HTTP request that
triggers a sync only enqueues a `ProxboxSyncJob`; the actual work runs
in an RQ worker, streams progress as SSE frames from `proxbox-api`,
and is observable via the Job detail page's SSE log stream.
Cancellation is supported (`views/job_cancel.py`).

**EdgeUno v1** runs everything inside the gunicorn worker that
received the request. A full sync of a non-trivial cluster will hold
the worker for the full duration; logging is `print()` to stdout.

**EdgeUno v2** runs from the management command (or scheduler
container). There is no queue, no retry, and no cancellation — the
operator kills the process. Concurrent runs are not protected against.

### 7.5. Wire schemas — Pydantic v2 contract mirrors vs raw dicts

**This repo** maintains Pydantic v2 mirror schemas pinned against a
wire contract:

- `contracts/proxbox_api_sse_schema.json` — sourced from `proxbox-api
  0.0.11`; defines every SSE message type, enum, and payload field.
- `contracts/overwrite_flags.json` — canonical 23-flag list mirrored
  in `proxbox-api/contracts/overwrite_flags.json`. Adding, removing,
  or reordering flags must happen in **both** repos in the same
  release; CI fails otherwise.
- `netbox_proxbox/schemas/backend_proxy.py` — local Pydantic v2 mirror.
- `tests/test_sse_schema_mirror.py` — fails CI if the local mirror
  drifts from the JSON contract.

**EdgeUno** has no schemas. Proxmox responses are raw `proxmoxer` /
aiohttp dicts; NetBox responses are pynetbox `Record` objects (v1) or
Django model instances (v2). Type errors surface only at attribute
access. Description-field parsing (`client:` / `email:` / `main ip:`
/ `ip address allocation:`) is regex-based with no formal contract.

---

## 8. Operational Verb Coverage Matrix

What each project actually *does* to a Proxmox cluster. ✅ = does it,
👁️ = observes / syncs only, ❌ = does not handle.

| Verb | `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11` | EdgeUno fork |
|---|---|---|
| Clone VM from template | ❌ | ❌ |
| Create LXC from OS template | ❌ | ❌ |
| Set vCPU / memory | ❌ | ❌ |
| Start / stop / delete VM or LXC | ❌ | ❌ |
| Add / resize / remove VM disk | ❌ | ❌ |
| Migrate VM between nodes | ❌ | ❌ |
| Take / restore / delete snapshot | ❌ (read 👁️ only) | ❌ |
| Trigger backup (vzdump) | ❌ | ❌ |
| Read backups (`VMBackup`) | 👁️ | ❌ |
| Read backup routines | 👁️ | ❌ |
| Read replication jobs | 👁️ | ❌ |
| Read task history (UPIDs) | 👁️ | ❌ |
| Read storage definitions | 👁️ | ❌ |
| Discover cluster + nodes | 👁️ (continuous via backend) | 👁️ (continuous via `Scrapper.async_run`) |
| Discover VMs / LXCs | 👁️ | 👁️ |
| Reflect VNC console URL in NetBox | 👁️ (template extension) | ❌ |
| Resolve LXC `VMConfig.hostname` | ✅ (0.0.11 backend) | ❌ |
| Resolve QEMU hostname via `qemu-guest-agent` | ✅ (0.0.11 backend; `agent/get-host-name`, network-interfaces fall-back) | ❌ |
| Write IPAM `IPAddress.dns_name` from Proxmox guest hostname | ✅ (gated by `overwrite_ip_address_dns_name`) | ❌ |
| Assign tenant from VM-name regex | ❌ | ✅ (`NETBOX_TENANT_REGEX_VALIDATOR`) |
| Parse VM `description` for `client:` / `email:` / `main ip:` / `ip address allocation:` | ❌ | ✅ |
| Role-pin VMs to `"VPS"` (qemu) / `"LXC"` (lxc) | ❌ | ✅ |
| Append `" (2)"` to colliding VM names | ❌ | ✅ (v1) |
| Update DNS (BIND9) | ❌ | ❌ |

Summary: this repo is a **broader mirror** (more Proxmox object kinds:
backups, snapshots, replications, routines, task history, storage
detail) and writes a single IPAM field (`dns_name`) back into NetBox.
The EdgeUno fork is a **narrower mirror** (clusters, nodes, VMs, IPs)
that does additional EdgeUno-specific writes (tenant assignment,
description parsing, role pinning). Neither is a doer of Proxmox
lifecycle verbs — both rely on operators using Proxmox directly for
authoring.

---

## 9. When to Use Which

- **You need a maintained, NetBox-4.6-certified observer with backups,
  snapshots, replication, IPAM `dns_name` writes, NetBox-UI-editable
  settings, encrypted credentials, a real test suite, and a release
  pipeline →** this repo (`netbox-proxbox 0.0.15` + `proxbox-api
  0.0.11`).

- **You need EdgeUno-specific tenant-regex assignment + `description`-
  field parsing + standalone Docker `scanner_scheduler.py` workflow,
  and you are already running NetBox `4.0.7` (or older), and you accept
  zero tests, `print()`-based logging, and plaintext credentials in a
  JSON file →** the EdgeUno fork.

- **You need a UI in NetBox →** this repo (the EdgeUno fork's UI is
  thin; most useful actions are CLI-driven).

- **You need event-driven side effects from NetBox changes →** neither
  is a fit. See `NETBOX-PROXMOX-AUTOMATION.md` for the upstream Labs
  project that handles that side of the problem.

- **You want both →** not realistically. They share the Python module
  name `netbox_proxbox`, target different NetBox version ranges, and
  overlap on the `ProxmoxVM` shadow-record concept (which only
  EdgeUno has). See §10.

---

## 10. Compatibility & Coexistence

Can both run on the same NetBox instance? **No** — the constraint is
hard. Specific collision points:

| Surface | Risk | Notes |
|---|---|---|
| Python plugin module name | ❌ Hard collision | Both use `netbox_proxbox`. Only one can be in `INSTALLED_APPS`. Confirmed in `setup.py:39` and `__init__.py:8` of each repo. |
| NetBox version range | ❌ Disjoint | `4.5.8 → 4.6.99` (this repo) vs `4.0.7 / 3.5.2 / 3.2.0` (EdgeUno releases). No overlapping range. |
| DB table names | ❌ Hard collision | Both projects own `netbox_proxbox_*` table prefixes, but their schemas are not compatible. Migrating from one to the other requires schema replacement. |
| Migration history | ❌ Disjoint | EdgeUno: 16 migrations through `0016_auto_20220726_2003`. This repo: 39 through `0039_pluginsettings_overwrite_ip_address_dns_name`. Different ancestries. |
| `ProxmoxVM` shadow record | EdgeUno only | This repo writes to canonical `virtualization.VirtualMachine` with custom fields; the EdgeUno `ProxmoxVM` model does not exist here. |
| Custom field names | ⚠️ Slight mismatch | This repo: `proxmox_vm_id`. EdgeUno: `proxmox_id`. Migration would need a rename + data backfill. |
| RQ queues | ✅ No collision | Only this repo uses one (`default`). EdgeUno has no queue. |
| API namespace | ❌ Hard collision | Both use `/api/plugins/proxbox/`, but with different viewsets — same URL, different shapes. |
| `PLUGINS_CONFIG['netbox_proxbox']` keys | ❌ Disjoint | This repo: empty (`required_settings = []`). EdgeUno: `filePath` only. |

**Bottom line: mutually exclusive deployments.** A NetBox instance
runs one or the other, never both. Migrating between them is a manual
schema-replacement operation, not an upgrade path.

---

## 11. Migration & Diverged-Lineage Notes

There is no automated migration path between the two projects. A
deployment that wants to switch from the EdgeUno fork to this repo
needs to:

1. **Upgrade NetBox first** (the EdgeUno fork targets 4.0.7 or older;
   this repo requires 4.5.8+). Follow NetBox's upstream upgrade docs
   for each major hop.
2. **Capture EdgeUno data**. Export every `ProxmoxVM` row,
   `configuration_options.json`, and the value of every custom field
   the operator pre-created (`proxmox_id`, `proxmox_node`,
   `proxmox_type`, `proxmox_keep_interface`).
3. **Uninstall EdgeUno**. Run `python manage.py migrate netbox_proxbox
   zero` to drop the EdgeUno tables, then `pip uninstall
   netbox-proxbox`. Remove `netbox_proxbox` and the `filePath` entry
   from `PLUGINS_CONFIG`.
4. **Install this repo**. `pip install netbox-proxbox`, configure
   `ProxmoxEndpoint`, `NetBoxEndpoint`, and `FastAPIEndpoint` records
   in the NetBox UI, deploy `proxbox-api 0.0.11`, and run the initial
   Full Update sync.
5. **Rename custom fields if needed**. The EdgeUno `proxmox_id` maps
   to this repo's `proxmox_vm_id`. Either rename the EdgeUno custom
   field before sync (then reconcile with the repo's `proxmox_vm_id`
   creation logic in the backend) or accept a fresh import from
   Proxmox.
6. **Discard EdgeUno-specific writes**. This repo does not parse
   `description` for `client:` / `email:` / `main ip:` / `ip address
   allocation:` and does not assign tenants from name-regex matches.
   Any data that depended on those flows must be re-modeled (typically
   via NetBox custom fields plus an external automation layer such as
   `netbox-proxmox-automation`).

For pre-DB-endpoint configuration of this repo (the older `PLUGINS_CONFIG`
shape), see [`../PAST_CONFIG.md`](../PAST_CONFIG.md). It is not the
EdgeUno shape — both differ from the canonical 0.0.15 shape — but
it is the closest in-tree reference for legacy configuration.

---

## 12. Glossary

| Term | Belongs to | Meaning |
|---|---|---|
| `proxbox-api` | this repo | Sibling FastAPI service that does all Proxmox & NetBox work for the plugin. |
| `proxmox-sdk` | this repo | Schema-driven Proxmox client used by `proxbox-api`. |
| `netbox-sdk` | this repo | Typed NetBox API client used by `proxbox-api`. |
| `ProxboxSyncJob` | this repo | RQ JobRunner in `netbox_proxbox/jobs.py`. |
| `ProxboxPluginSettings` | this repo | Singleton Django model holding all runtime tunables. |
| `EndpointBase` | this repo | Abstract model for `ProxmoxEndpoint`/`NetBoxEndpoint`/`FastAPIEndpoint`. |
| `X-Proxbox-API-Key` | this repo | Custom auth header used by the plugin to talk to `proxbox-api`. |
| SSE | this repo | Server-Sent Events; the protocol over which `proxbox-api` streams sync progress. |
| `pxb` | this repo | Optional Typer CLI shipped under `proxbox_cli/`. |
| `use_https` | this repo (0.0.15) | Boolean field on `FastAPIEndpoint` controlling URL scheme; independent of `verify_ssl`. |
| `runtime_settings` | this repo (backend 0.0.11) | `proxbox_api/runtime_settings.py` helpers (`get_int / get_float / get_bool / get_str`); resolves env var → `ProxboxPluginSettings` → built-in default. |
| `OVERWRITE_FIELDS` | this repo | Canonical 23-flag overwrite-flag registry pinned by `contracts/overwrite_flags.json`. |
| `proxbox_api/` | EdgeUno | Synchronous v1 sync engine inside the plugin; web-triggered. |
| `proxbox_api_v2/` | EdgeUno | Asynchronous v2 sync engine inside the plugin; management-command-triggered. |
| `Scrapper` | EdgeUno | Top-level async orchestrator in `proxbox_api_v2/scrapper.py`; entry point is `Scrapper.async_run` (line 88). |
| `ProxboxSession` | EdgeUno | Per-cluster session object holding `aiohttp` client + Proxmox creds + NetBox handle. |
| `PROXMOX_SESSIONS_LIST` | EdgeUno | Module-level list of `ProxboxSession` instances built from `configuration_options.json`. |
| `proxboxscrapper` | EdgeUno | Django management command that calls `Scrapper.async_run`. |
| `latest_job` | EdgeUno | UUID written into every upsert; raw-SQL stale-VM cleanup deletes rows whose `latest_job` does not match the current run. |
| `PROXBOX_MODE` | EdgeUno | Scheduler env var: `off|continuous|interval|cron`. |
| `scanner_scheduler.py` | EdgeUno | 210-line container entrypoint that dispatches `proxboxscrapper` according to `PROXBOX_MODE`. |
| `configuration_options.json` | EdgeUno | External JSON file holding cluster array + shared NetBox block; referenced from `PLUGINS_CONFIG['netbox_proxbox']['filePath']`. |
| `ProxmoxVM` | EdgeUno | Plugin-owned shadow record for a Proxmox guest; this repo has no equivalent. |
| `SyncTask` | EdgeUno | Dormant model from an abandoned `django_queues` branch; not wired into the v2 path. |

---

## 13. Cross-Reference Index

- Companion deep-dive on the EdgeUno fork:
  [`./EDGEUNO-NETBOX-PROXMOX.md`](./EDGEUNO-NETBOX-PROXMOX.md).
- Companion deep-dive on the upstream Labs automation project:
  [`./NETBOX-PROXMOX-AUTOMATION.md`](./NETBOX-PROXMOX-AUTOMATION.md).
- Sibling comparison doc (this repo vs the upstream Labs project):
  [`./PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md).
- This plugin's primary developer guide:
  [`../CLAUDE.md`](../CLAUDE.md).
- Latest plugin release notes:
  [`../docs/release-notes/version-0.0.15.md`](../docs/release-notes/version-0.0.15.md).
- Cross-repo overwrite-flag contract:
  `../contracts/overwrite_flags.json` (23 flags) — must stay in lock-step
  with `proxbox-api/contracts/overwrite_flags.json`.
- Wire contract pinned against `proxbox-api 0.0.11`:
  `../contracts/proxbox_api_sse_schema.json`.
- Sibling project `proxbox-api` (FastAPI backend):
  `/root/nms/proxbox-api/`.
- Sibling project `proxmox-sdk` (Proxmox client used by backend):
  `/root/nms/proxmox-sdk/`.
- EdgeUno fork source:
  `/root/nms/edgeuno/netbox-proxbox/`.

---

*End of comparison.*
