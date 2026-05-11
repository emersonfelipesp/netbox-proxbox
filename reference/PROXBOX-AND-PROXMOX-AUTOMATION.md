# `netbox-proxbox` vs `netbox-proxmox-automation` — Side-by-Side Reference

> Companion doc to
> [`NETBOX-PROXMOX-AUTOMATION.md`](./NETBOX-PROXMOX-AUTOMATION.md), which is
> the standalone deep-dive on the upstream NetBox Labs project. This file
> compares that project to **`netbox-proxbox`** (the plugin in this
> repository) on every axis a contributor or operator might care about.
>
> Source revisions:
> - `netbox-proxbox` `0.0.15` (this repo, `v0.0.15` branch). Paired with
>   sibling backend `proxbox-api` `0.0.11` (`v0.0.11` branch at
>   `/root/nms/proxbox-api/`). The previous `0.0.14` + `0.0.10.post2`
>   pair remains wire-compatible for the new `Use HTTPS` toggle but
>   does not implement IPAM `dns_name` writes from the Proxmox guest
>   hostname.
> - `netbox-proxmox-automation` `2025.11.01` (CalVer; cloned at
>   `/root/nms/netbox-proxmox-automation`). Unchanged from the prior
>   revision of this doc.

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
11. [Glossary](#11-glossary)
12. [Cross-Reference Index](#12-cross-reference-index)

---

## 1. Purpose & Scope

`netbox-proxbox` and `netbox-proxmox-automation` both connect NetBox to
Proxmox VE, but they solve **opposite halves of the same problem**.
Reading either repository's README in isolation does not make this
obvious — the two projects use overlapping vocabulary
("sync", "VM", "node", "cluster", "Proxmox endpoint") to describe
incompatible workflows.

This document is for:

- Contributors to `netbox-proxbox` deciding whether to borrow a pattern
  from the upstream project, deliberately diverge, or call out the
  divergence in plugin docs.
- Operators evaluating which integration fits their environment, or
  whether they should run both side-by-side.
- Reviewers checking that this repo's design choices are intentional and
  well-grounded.

It is **not** a replacement for either project's own docs — it is a
focused comparison.

---

## 2. TL;DR

> **`netbox-proxmox-automation`** is an event-driven *desired-state*
> translator: an operator authors VMs and disks in NetBox, NetBox
> webhooks fire on every change, and either an Ansible AWX job template
> or a small Flask app turns that intent into Proxmox API calls. Its
> direction is **NetBox → Proxmox**.

> **`netbox-proxbox`** is a NetBox plugin with a sibling FastAPI
> backend (`proxbox-api`). It treats Proxmox as the source of operational
> truth and projects that truth into NetBox: clusters, nodes, storage,
> VMs, backups, snapshots, replications, task history. Its direction is
> primarily **Proxmox → NetBox**.

The headline difference: one project lets you **author hypervisor state
in NetBox**, the other lets you **observe hypervisor state from NetBox**.
They are complementary in principle and could coexist on a single NetBox
deployment.

### What changed in `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11`

This is the running delta from the `0.0.14 / 0.0.10.post2` pair the rest
of the doc was originally written against:

- **`Use HTTPS` decoupled from `Verify SSL`** on `FastAPIEndpoint`
  (issue [#352](https://github.com/emersonfelipesp/netbox-proxbox/issues/352)).
  New `use_https` field, migration `0038`, and a one-time data
  backfill so existing rows keep working. `services/_endpoint_errors.py`
  translates the two known nginx-image misconfigurations
  (`plain HTTP request was sent to HTTPS port`, `SSLError`) into
  operator-actionable strings on the endpoint detail page.
- **IPAM `dns_name` is now populated from Proxmox guest hostnames**
  (issue [#354](https://github.com/emersonfelipesp/netbox-proxbox/issues/354)).
  Backend resolves `VMConfig.hostname` for LXC and
  `agent/get-host-name` for QEMU (with a fall-back through the
  network-interfaces payload). Plugin gates the write through a new
  `overwrite_ip_address_dns_name` flag (global on
  `ProxboxPluginSettings`, tri-state per `ProxmoxEndpoint`) — bringing
  the canonical overwrite-flag count to **23**.
- **Runtime tunables migrated to `ProxboxPluginSettings`** (plugin
  migration `0037`; backend `proxbox_api/runtime_settings.py` and
  `settings_client.py`). Concurrency, batching, cache, retry, and
  observability fields are now DB-backed singleton fields editable in
  NetBox UI; backend reads them via
  `runtime_settings.get_int / get_float / get_bool / get_str`, with
  resolution order **env var → `ProxboxPluginSettings` →
  built-in default** and a 5-minute settings cache.
- **Non-blocking startup + runtime encryption-key endpoints** on the
  backend (`routes/admin/encryption.py`). Startup no longer blocks on
  credentials; the encryption key can be rotated through a runtime
  admin endpoint instead of requiring a process restart.
- **`netbox-sdk` bumped to `0.0.8.post1`** in the backend.
- **Inline home dashboard logos + JS** so the plugin's home page
  renders without `python manage.py collectstatic` (issue
  [#355](https://github.com/emersonfelipesp/netbox-proxbox/issues/355)).
- **Release pipeline staged** into TestPyPI → PyPI lanes
  (`publish-testpypi.yml`); new operator-facing docs at
  `docs/developer/{ci-e2e-workflows,release-publishing}.md`.

The mental model in §4, the architecture in §5, and the operational
verb stance ("plugin observes, upstream authors") all still hold.
Section 6 cells, Section 7.5, and Section 8 are the rows that move.

---

## 3. Project Identity at a Glance

| Attribute | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Repository | `netboxlabs/netbox-proxmox-automation` | `emersonfelipesp/netbox-proxbox` |
| Maintainer | Nate Patwardhan (NetBox Labs) | Emerson Felipe |
| License | Apache-2.0 | Apache-2.0 |
| Language | Python 3.12 + Ansible YAML + Jinja2 | Python 3.12 + Django + Pydantic v2 |
| Versioning | CalVer (`2025.11.01`) | SemVer (`0.0.15`; backend `0.0.11`) |
| Project shape | Standalone repo (no NetBox plugin) | NetBox plugin (Django app + Pydantic schemas) |
| Companion service | Optional Flask app + AWX/Tower/AAP | Required FastAPI backend (`proxbox-api 0.0.11`) |
| NetBox compat | ≥ 4.3.7 | 4.5.8 → 4.6.99 (`min_version` / `max_version` in `__init__.py`) |
| Proxmox compat | 8.x (8.4 tested); 9.x untested | 8.x (validated through `proxbox-api` `0.0.11`; QEMU hostname resolution uses `agent/get-host-name`) |
| `netbox-sdk` (backend) | N/A | `0.0.8.post1` |
| Distribution | Git clone, pip install of `setup/`, run scripts | PyPI / TestPyPI (staged release pipeline); `pip install netbox-proxbox` |

---

## 4. Mental Models

### `netbox-proxmox-automation` — desired-state authoring

The operator's mental loop:

1. Open NetBox UI, create a `VirtualMachine` with `status=staged`,
   `proxmox_vm_type=vm`, `proxmox_node=…`, vCPUs, memory.
2. Save → NetBox event rule fires the `proxmox-clone-vm-and-set-resources`
   webhook.
3. Either AWX runs `awx-proxmox-clone-vm-and-set-resources.yml`, or the
   Flask app runs `NetBoxProxmoxHelperVM.proxmox_clone_vm()`.
4. The new Proxmox VM appears, its VMID is written back into NetBox.
5. Operator changes `status` to `active` to start, `offline` to stop,
   flips `proxmox_node` to migrate, deletes the NetBox object to delete
   the VM.

Loss surface: every authoring step happens in NetBox. Proxmox is a
puppet.

### `netbox-proxbox` — operational-truth projection

The operator's mental loop:

1. Configure a `ProxmoxEndpoint`, `NetBoxEndpoint`, and `FastAPIEndpoint`
   in the plugin UI (DB-backed, encrypted credentials).
2. Click **Full Update** (or schedule a recurring sync, or hit a
   per-object **Sync Now** button).
3. The plugin enqueues a `ProxboxSyncJob` on NetBox's RQ `default`
   queue.
4. The job calls `proxbox-api`'s SSE streaming endpoints, frame by
   frame, advancing through 12 ordered stages (devices → storage →
   VMs → vm-disks → backups → snapshots → interfaces → IPs → routines →
   replications → task-history).
5. `proxbox-api` does the actual Proxmox reads and NetBox writes; the
   plugin observes progress, displays results, manages
   plugin-specific Django models (`ProxmoxCluster`, `ProxmoxNode`,
   `ProxmoxStorage`, `VMBackup`, `VMSnapshot`, `Replication`,
   `BackupRoutine`, `VMTaskHistory`).
6. As of `0.0.15` / `0.0.11`, the mirror also pulls Proxmox guest
   **hostnames** into IPAM `IPAddress.dns_name`, gated by the
   `overwrite_ip_address_dns_name` flag. Concurrency / batching /
   cache / retry knobs are no longer environment-only — they live as
   DB-backed fields on the `ProxboxPluginSettings` singleton, editable
   from the NetBox UI and read by the backend through
   `runtime_settings`.

Loss surface: NetBox is a mirror. Proxmox is the truth.

---

## 5. Architecture Diagrams

### 5.1. `netbox-proxmox-automation`

```
       Operator (NetBox UI / API)
              │
              ▼
   ┌──────────────────────────┐
   │       NetBox 4.3+        │
   │  Custom fields, event    │
   │  rules (×17), webhooks   │
   └──────────┬───────────────┘
              │ HTTP POST event payload
   ┌──────────┴───────────────┐
   │ automation_type:         │
   │   flask_application  OR  │
   │   ansible_automation     │
   └──────┬───────────┬───────┘
          │           │
          ▼           ▼
   ┌────────┐   ┌────────────┐
   │ Flask  │   │ AWX/Tower  │
   │ + RESTX│   │ /AAP + EE  │
   └───┬────┘   └─────┬──────┘
       │ proxmoxer    │ community.proxmox
       └──────┬───────┘
              ▼
       ┌──────────────┐
       │ Proxmox 8.x  │
       └──────────────┘

(One-shot, manual: setup/netbox-discover-*.py walks Proxmox via
 SSH + dmidecode + ethtool + Proxmox API, writes inventory back
 into NetBox. Not webhook-driven.)
```

### 5.2. `netbox-proxbox`

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
       │  Encrypted credential store          │
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

The plugin **never** talks to Proxmox directly. All Proxmox calls go
through `proxbox-api`. The plugin pushes credential records to
`proxbox-api` before each sync (so credentials live in NetBox DB, but
flow to the backend on demand).

---

## 6. Comprehensive Feature Comparison

This is the main artifact. Rows are grouped by category. ✅ = supported,
❌ = not supported, ⚠️ = partial / caveat.

### 6.1. Project shape & distribution

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Is it a NetBox plugin? | ❌ No (no Django app, no migrations) | ✅ Yes (`PluginConfig`, models, views, templates, REST API) |
| Installable from PyPI? | ❌ Git clone only | ✅ `pip install netbox-proxbox` (also TestPyPI) |
| Required external service | ⚠️ One of: Flask app **or** AWX | ✅ Required: `proxbox-api` FastAPI service |
| Optional external service | NetBox Branching plugin (setup-time only) | NetBox Branching plugin (not used at runtime) |
| Shipped binary scripts | `setup/*.py`, Flask `app.py` | Plugin only; CLI extras: `pxb` (Typer + aiohttp) |
| Build system | (no build; scripts) | `hatchling`; `uv.lock` checked in |

### 6.2. NetBox integration surface

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Django models | ❌ None | ✅ 13 (`ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `ProxmoxCluster`, `ProxmoxNode`, `ProxmoxStorage`, `ProxmoxStorageVirtualDisk`, `BackupRoutine`, `Replication`, `VMBackup`, `VMSnapshot`, `VMTaskHistory`, `ProxboxPluginSettings`). 0.0.15 adds new fields, no new models: `FastAPIEndpoint.use_https`, `ProxboxPluginSettings.overwrite_ip_address_dns_name`, `ProxmoxEndpoint.overwrite_ip_address_dns_name` (tri-state), and the runtime-tunable singleton fields from migration `0037`. |
| Migrations | ❌ None | ✅ Yes (latest: `0039_pluginsettings_overwrite_ip_address_dns_name`) |
| Custom fields | ✅ 8 declared (`proxmox_node`, `proxmox_vm_type`, `proxmox_vmid`, `proxmox_vm_storage`, `proxmox_public_ssh_key`, `proxmox_vm_templates`, `proxmox_disk_storage_volume`, `proxmox_lxc_templates`) | ⚠️ Reads `proxmox_vm_id`, `proxmox_vm_type`, `proxmox_node` (created by `proxbox-api` sync, not by the plugin itself); `IPAddress.dns_name` is now **written** from Proxmox guest hostnames via `proxbox-api 0.0.11` |
| Custom field choice sets | ✅ 5 (`proxmox-vm-templates`, `-vm-storage`, `-lxc-templates`, `-cluster-nodes`, `-vm-type`) | ❌ Not on `extras.custom_field_choice_sets`; uses Django form `ChoiceSet` only |
| Tags created | ✅ 2 (`proxmox-vm-discovered`, `proxmox-lxc-discovered`) | ⚠️ Indirect via `proxbox-api` sync |
| Event rules | ✅ 17 declared by setup script | ❌ None |
| Webhooks | ✅ One per AWX template, or one for Flask | ❌ None |
| NetBox UI integration | ❌ None — operator works in stock NetBox UI | ✅ Plugin views, dashboard, ~80 templates, Sync-now buttons via `template_extensions` |
| Plugin REST API | ❌ N/A | ✅ `/api/plugins/proxbox/` — 12 model viewsets + 11 non-model views |
| Plugin GraphQL API | ❌ N/A | ❌ Not currently exposed |
| Branching plugin support | ✅ Setup-time (X-NetBox-Branch header) | ❌ Not used |

### 6.3. Proxmox integration surface

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Direct Proxmox API calls? | ✅ Yes — `proxmoxer` (Flask) and `community.proxmox` Ansible (AWX) | ❌ No — all Proxmox traffic flows through `proxbox-api` |
| Auth | Token only (`api_user@pve` + token id + token secret) | Token or username/password; stored encrypted; pushed to backend at sync time |
| SSL verification | Configurable (but `verify_ssl=False` is hardcoded for Proxmox in the Flask helper — known divergence) | Configurable per `ProxmoxEndpoint`; SSRF-protected via `ssrf_protection_enabled` setting |
| HTTPS scheme vs cert verification | Coupled (one flag) | ✅ **Decoupled in 0.0.15** — `FastAPIEndpoint.use_https` controls scheme, `verify_ssl` controls cert strictness; required for the proxbox-api `*-nginx` image bundled with mkcert |
| QEMU VMs | ✅ Full lifecycle | ⚠️ Read-only sync; no lifecycle actions |
| LXC containers | ✅ Full lifecycle | ⚠️ Read-only sync |
| Cloud-init `ipconfig0` | ✅ Sets cloud-init IP + derived gateway | ❌ N/A |
| SSH public key injection | ✅ Sets `sshkeys` via cloud-init | ❌ N/A |
| Node migration | ✅ VM only (LXC unsupported by Proxmox) | ❌ Not exposed as a verb |
| Snapshots | ❌ | ✅ Read-only sync (`VMSnapshot`) |
| Backups (vzdump files) | ❌ | ✅ Read-only sync (`VMBackup`) |
| Backup routines (vzdump schedules) | ❌ | ✅ Read-only sync (`BackupRoutine`) with full retention/advanced fields |
| Replication jobs | ❌ | ✅ Read-only sync (`Replication`) |
| Task history (UPIDs) | ❌ | ✅ Read-only sync (`VMTaskHistory`) |
| Storage definitions | ❌ | ✅ Read-only sync (`ProxmoxStorage`) with NFS/CIFS/Ceph/PBS detail fields |
| Cluster discovery | ✅ One-shot via SSH + `dmidecode` + `ethtool` + Proxmox API | ✅ Continuous via `proxbox-api` |
| QEMU `agent/get-host-name` resolution | ❌ | ✅ **0.0.11**, with fall-back through the network-interfaces payload |
| LXC `VMConfig.hostname` resolution | ❌ | ✅ **0.0.11** |
| Console buttons in UI | ❌ | ✅ VNC / LXC console links injected via template extensions |

### 6.4. Trigger & execution model

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Primary trigger | NetBox event rules → webhook POST | Manual UI / scheduled RQ job / Sync Now buttons |
| Webhook listener | ✅ Flask `/<webhook_name>/` or AWX job template | ❌ None |
| Polling | ❌ | ❌ (RQ schedule is push-based) |
| Background scheduler | ❌ | ✅ `views/schedule_sync.py` enqueues recurring `ProxboxSyncJob` |
| Idempotency | None (duplicate webhook → duplicate operation) | RQ + `sync_ownership.py` claim prevents concurrent duplicates |
| Cancellation | ❌ | ✅ `views/job_cancel.py` (POST, requires `core.delete_job`) |
| Retry | ❌ | ⚠️ At HTTP layer (`netbox_max_retries`, `netbox_retry_delay`); not at job level |

### 6.5. Concurrency & queueing

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Queue technology | ❌ None — synchronous in gunicorn worker | ✅ NetBox RQ `default` queue |
| Long-task handling | Polling Proxmox `tasks/<upid>/status` inside the HTTP request | RQ job with `job_timeout=7200s` + SSE stream `(5, 3600)s` read timeout |
| Worker count | gunicorn `-w 4` | Standard NetBox RQ worker count |
| Concurrency tuning | None | `proxbox_fetch_max_concurrency`, `netbox_max_concurrent`, `netbox_write_concurrency`, `vm_sync_max_concurrency`, `proxmox_fetch_concurrency` — all are **DB-backed `ProxboxPluginSettings` fields** since 0.0.15 (migration `0037`); backend reads them via `runtime_settings.get_int / get_float / get_bool / get_str` |
| Per-stage concurrency | N/A | ✅ Configurable in `ProxboxPluginSettings` |
| Settings cache | N/A | 5-minute TTL on `proxbox_api/settings_client.py` |

### 6.6. Configuration & secrets

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Config medium | YAML files on disk (`conf.d/netbox_setup_objects.yml`, Flask `app_config.yml`) | Django models (DB), editable in NetBox UI; **0.0.15 codifies a "DB-first" policy** in `CLAUDE.md` |
| Environment variables | ❌ None used | ⚠️ Backend uses env vars only for **pre-DB infra**: `PROXBOX_BIND_HOST`, `PROXBOX_RATE_LIMIT`, `PROXBOX_ENCRYPTION_KEY` / `PROXBOX_ENCRYPTION_KEY_FILE`, `PROXBOX_STRICT_STARTUP`, `PROXBOX_SKIP_NETBOX_BOOTSTRAP`, `PROXBOX_GENERATED_DIR`, `PROXBOX_CORS_EXTRA_ORIGINS`. All sync/concurrency/cache/feature-toggle tunables live in `ProxboxPluginSettings` since 0.0.15. Plugin still uses none. |
| Tunable resolution order (backend) | N/A | ✅ **0.0.11**: `runtime_settings.get_int/get_float/get_bool/get_str` resolves **env var → `ProxboxPluginSettings` → built-in default** with a 5-minute settings cache |
| Encryption at rest | ❌ Plaintext YAML | ✅ `proxbox-api` Fernet encryption with `PROXBOX_ENCRYPTION_KEY`; **0.0.11 adds runtime rotation** via `routes/admin/encryption.py` (no process restart required) |
| Encryption-key bootstrap | N/A | ✅ Non-blocking startup in 0.0.11 (`feat(credentials): non-blocking startup + runtime encryption key endpoints`) — backend no longer hangs at startup if the key store is empty |
| Per-endpoint config | One YAML file per cluster | One `ProxmoxEndpoint` row per cluster; per-endpoint `overwrite_*` flags **(23 in 0.0.15)** with tri-state inheritance from the global `ProxboxPluginSettings` row |
| Singleton settings | ❌ | ✅ `ProxboxPluginSettings` (singleton enforced via `singleton_key="default"`); now exposes runtime tunables + `overwrite_ip_address_dns_name` |
| Settings UI | ❌ | ✅ `views/settings.py` + form; runtime tunables grouped on the Settings tab |
| Settings REST endpoint | ❌ | ✅ `/api/plugins/proxbox/settings/` (added by `fix(api): expose runtime settings endpoint` in 0.0.15) — backend reads it on every cache miss |
| `PLUGINS_CONFIG` keys | N/A | ⚠️ `required_settings = []`; everything in DB |
| Multi-cluster support | ✅ One YAML per cluster, separate runs | ✅ Multiple `ProxmoxEndpoint` rows, one cluster per row |

### 6.7. Authentication

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| NetBox auth | API token in YAML | API token (`NetBoxEndpoint`); v1 (raw) or v2 (`token_key` + `token_secret`) |
| Proxmox auth | API token only | API token or username/password |
| Plugin ↔ backend auth | N/A | `X-Proxbox-API-Key` header; auto-generated `secrets.token_urlsafe(48)` on first save of `FastAPIEndpoint`, registered with `/auth/register-key` |
| Brute-force protection | ❌ | ✅ At backend (`proxbox-api` lockout) |
| Bootstrap thread | N/A | ✅ Daemon thread `proxbox-startup-endpoint-push` waits 10 s then pushes endpoint data to backend |

### 6.8. Sync direction & coverage

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Primary direction | NetBox → Proxmox | Proxmox → NetBox |
| Reverse direction | One-shot discovery scripts | Plugin pushes endpoint config to backend (config flow only, not data) |
| Sync coverage stages | Only what event rules trigger; discovery scripts cover devices/VMs/LXCs | 12 ordered stages: `devices → storage → virtual-machines → vm-disks → vm-backups → vm-snapshots → network-interfaces → vm-interfaces → ip-addresses → backup-routines → replications → task-history` |
| Full-update endpoint | ❌ | ✅ `full-update/stream` (SSE) |
| Per-object sync | Manual re-issue | ✅ `views/vm_sync_now.py` and `views/sync_now/{cluster,node,storage,vm}.py` |

### 6.9. UI surface

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Custom NetBox UI | ❌ | ✅ Home page, Dashboard, resource lists, settings page, schedule page, logs page |
| Sidebar menu | ❌ | ✅ Three groups: Proxmox Plugin, Endpoints, Join our community |
| Template extensions | ❌ | ✅ `template_content.py`: Job, VM, Cluster, Node, Storage, VMBackup, VMSnapshot, VMTaskHistory |
| WebSocket UI | ❌ | ✅ `views/websocket_test/`, `templates/test/websocket.html` (browser-side updates) |
| Live job log streaming | ❌ | ✅ `views/job_stream.py` (SSE on Job detail page) |
| Live cluster cards | ❌ | ✅ `views/cards.py`, AJAX-hydrated dashboard cards |

### 6.10. CLI surface

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| CLI shipped | ❌ (only Python convenience scripts) | ✅ `pxb` (Typer + aiohttp + Rich) |
| CLI install | N/A | `pip install "netbox-proxbox[cli]"` |
| Config file | N/A | `~/.config/proxbox-cli/config.json` |
| Targets | N/A | `proxbox-api` backend (NOT NetBox directly) |
| Subcommands | N/A | `init`, `config`, `test`, `version`, `info`, `cache`, `clear-cache`, `full-update`, `docs`; sub-apps: `netbox`, `proxmox`, `proxbox`, `dcim`, `virtualization`, `extras` |
| Output formats | N/A | Human (Rich), `--json`, `--yaml` |

### 6.11. REST API surface

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Plugin REST API | ❌ Plugin doesn't exist | ✅ `/api/plugins/proxbox/` |
| Model viewsets | N/A | 12 (one per business model) |
| Non-model views | N/A | 11 (Home, Dashboard, Clusters, Nodes, VMs, LXCs, Interfaces, IPs, Disks, Schedule, Logs) |
| Token-write fields | N/A | `password`, `token_value` are write-only on serializers |
| OpenAPI doc page | N/A | `templates/netbox_proxbox/fastapiendpoint_openapi.html` mirrors backend OpenAPI |

### 6.12. SSE / WebSocket / streaming

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| SSE (server-sent events) | ❌ | ✅ Major design pillar — `services/backend_proxy.py` streams from `proxbox-api`'s `*/stream` endpoints |
| WebSocket | ❌ | ⚠️ Optional via `FastAPIEndpoint.use_websocket`; `websocket_client.py` |
| Frame schema | N/A | `contracts/proxbox_api_sse_schema.json` (pinned wire contract) |
| Frame validation | N/A | Pydantic v2 mirror models in `schemas/backend_proxy.py`; validated by `test_sse_schema_mirror.py` |

### 6.13. Background jobs

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Job framework | ❌ | ✅ NetBox `JobRunner` (`netbox.jobs`) |
| Job class | N/A | `ProxboxSyncJob` (`netbox_proxbox/jobs.py`) |
| Job timeout | N/A | 7200 s (2 hours) |
| HTTP read timeout | N/A | 3600 s between SSE chunks |
| Scheduling | N/A | One-shot or recurring (`views/schedule_sync.py`) |
| Cancellation | ❌ | ✅ `views/job_cancel.py` |
| Re-run completed | ❌ | ✅ `views/job_run.py` |

### 6.14. Custom fields, choice sets, tags

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Plugin creates `extras.custom_fields`? | ✅ Setup script | ❌ Backend creates them at sync |
| Plugin creates `extras.custom_field_choice_sets`? | ✅ 5 sets | ❌ |
| Plugin creates `extras.tags`? | ✅ 2 tags | ⚠️ Backend may create discovery tags |
| Plugin creates `extras.event_rules`? | ✅ 17 | ❌ |
| Plugin creates `extras.webhooks`? | ✅ | ❌ |

### 6.15. Templating / Jinja2

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Jinja2 in webhooks | ✅ AWX webhook body templates map NetBox payload → `vm_config` | ❌ |
| Jinja2 in playbooks | ✅ Heavy use of `{{ proxmox_env_info.* }}`, `{{ vm_config.* }}` | ❌ |
| BIND9 zone Jinja2 | ✅ `templates/bind9/zone-template.j2` (roadmap) | ❌ |
| Django templates | ❌ | ✅ ~80 templates under `templates/netbox_proxbox/` |

### 6.16. Tests

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Test framework | ❌ No `tests/` directory | ✅ pytest + heavy mocking via `conftest.py` |
| Test files | 0 | 50 (`find tests -name 'test_*.py' \| wc -l`); 0.0.15 adds `test_endpoint_errors`, `test_settings_view_encryption`, `test_templatetags`, `test_utils` |
| E2E tests | ❌ | ✅ `tests/e2e/` with Docker stack tests |
| AST contract tests | ❌ | ✅ `test_version.py`, `test_signals.py`, `test_overwrite_flags_contract.py`, etc. |
| Coverage tooling | ❌ | ✅ `pytest-cov`, `coverage.xml`, branch coverage |
| Schema mirror tests | ❌ | ✅ `test_sse_schema_mirror.py` validates against `contracts/proxbox_api_sse_schema.json`; `test_overwrite_flags_contract.py` pins the canonical 23-flag list against `contracts/overwrite_flags.json` (mirrored in `proxbox-api`) |

### 6.17. CI/CD

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| GitHub Actions | ⚠️ Minimal (docs only) | ✅ Multiple workflows |
| Lint | ❌ | ✅ `ruff` (lint + format), `bandit`, `ty` |
| Type check | ❌ | ✅ `ty` on `proxbox_cli` |
| E2E matrix | ❌ | ✅ `e2e-docker.yml`: `install_source × netbox_image × network_stack`, nightly 02:31 UTC |
| Release pipeline | ❌ | ✅ Staged TestPyPI → PyPI lanes (`publish-testpypi.yml`); 0.0.15 adds `prepare-release`, `validate-testpypi`, `e2e-docker-testpypi`, `validate-pypi-candidate`, `e2e-docker-pypi-candidate`, `publish-pypi`, `validate-pypi`, `e2e-docker-pypi` jobs and `docs/developer/release-publishing.md` to document them |
| Docs build | ✅ MkDocs (manual) | ✅ `docs.yml` deploys to GitHub Pages |
| Screenshot capture | ❌ | ✅ `docs-screenshots.yml` + Playwright |
| Nightly contract refresh | ❌ | ✅ `nightly-contracts.yml` |

### 6.18. Documentation site

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Theme | MkDocs Material | MkDocs Material |
| Color scheme | NetBox Labs (`nbl-light` / `nbl-dark`) | Default Material + deep-orange accent |
| Pages | 15 markdown pages | 60+ across Install / Backend / Configuration / CLI / Developer / API Reference / Features / Data Model / Release Notes / Roadmap; 0.0.15 adds `docs/release-notes/version-0.0.15.md` and `docs/developer/{ci-e2e-workflows,release-publishing}.md` |
| `mkdocstrings`? | ❌ | ✅ Python handler + `griffe_typingdoc` |
| Inline screenshots | ✅ 50+ PNGs in `docs/images/` | ⚠️ Generated via Playwright |

### 6.19. Branching, multi-cluster, security

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Branching plugin support | ✅ Setup-time only (`helpers/netbox_branches.py`) | ❌ Not used |
| Multi-cluster | ✅ One config per cluster, separate runs | ✅ Multiple `ProxmoxEndpoint` rows in one DB |
| SSRF protection | ❌ | ✅ `ssrf_protection_enabled` toggle, IP allow/blocklist |
| Allow private IPs flag | ❌ | ✅ `allow_private_ips` |
| Encryption at rest | ❌ | ✅ Backend Fernet (`PROXBOX_ENCRYPTION_KEY`) |
| Encryption-key rotation at runtime | ❌ | ✅ **0.0.11** — `routes/admin/encryption.py` (no process restart) |
| Token rotation in plugin | N/A | ✅ FastAPIEndpoint regenerates token on save |
| Endpoint misconfig surfacing | ❌ | ✅ **0.0.15** — `services/_endpoint_errors.py` translates `400 plain HTTP request was sent to HTTPS port` (nginx image with mkcert) and `SSLError` into a one-sentence operator-actionable message on the FastAPI endpoint detail page |

### 6.20. Observability & logging

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Log file | `netbox-proxmox-webhook-listener.log` (CWD) | `backend_log_file_path` setting (default `/var/log/proxbox.log`) |
| Log rotation | ❌ External (`logrotate`) | ❌ External |
| Live log UI | ❌ | ✅ Backend logs page (`views/logs.py`); per-job SSE stream (`views/job_stream.py`) |
| Health probes | ❌ | ✅ `views/keepalive_status.py` (`/keepalive/fastapi/`, NetBox, Proxmox) |
| Status badges | ⚠️ Flask `/status/` endpoint | ✅ `templates/proxbox-backend-status.html`, status-badge partial |
| Inline-asset rendering | N/A | ✅ **0.0.15** — home dashboard logos and JS are inlined via `templatetags/proxbox_tags.py` and `static/netbox_proxbox/js/home_inline.js`; the home page now renders correctly on installs that skipped `python manage.py collectstatic` (issue #355) |

### 6.21. Roadmap / known issues

| Aspect | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Known limitations | Proxmox 9.x untested; LXC migration unsupported; SCSI disks only; tags not synced; `verify_ssl=False` hardcoded in Flask helper; MB÷1000 vs ÷1024 unit divergence | Most operational verbs not yet exposed; sync is mostly observational (the lone write into NetBox-hosted DCIM/IPAM/virtualization is the `IPAddress.dns_name` propagation added in 0.0.11). Backend nginx image required `Use HTTPS` + `Verify SSL`-off coupling — now decoupled in 0.0.15 |
| Stated roadmap | NetBox Custom Objects (>4.4); DNS via gss-tsig; NetBox Discovery/Assurance | See `docs/roadmap.md` in this repo and `docs/release-notes/version-0.0.15.md` for the latest delta |

---

## 7. Code Pattern Comparison

Five concrete patterns where the projects diverge most clearly. Each
sub-section is short on purpose — the goal is to make the divergence
*nameable*.

### 7.1. Endpoint persistence — YAML vs Django models

**`netbox-proxmox-automation`** stores credentials in flat YAML on disk.
The Flask app reads `app_config.yml` at import time; setup scripts read
`conf.d/netbox_setup_objects.yml` per `--config` flag. There is no
encryption, no UI, and no `os.environ` integration.

```yaml
# Plaintext, world-readable unless the operator chmod's it.
proxmox_api_config:
  api_token_secret: <secret>
```

**`netbox-proxbox`** stores credentials in Django models
(`ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`), persisted in
NetBox's PostgreSQL. The plugin then *pushes* a derived shape of those
records to the `proxbox-api` backend at sync time, where they are
encrypted at rest with Fernet (`PROXBOX_ENCRYPTION_KEY`). The plugin
itself sees plaintext — the encryption boundary is at the backend's DB.

```python
class FastAPIEndpoint(EndpointBase):
    token = models.CharField(...)  # secrets.token_urlsafe(48) on save
    use_https = models.BooleanField(default=False)
    use_websocket = models.BooleanField(default=False)
```

### 7.2. Drift detection — `createOrUpdate` vs Django ORM

**`netbox-proxmox-automation`** uses a hand-rolled
`NetBox.createOrUpdate()` in `helpers/netbox_objects.py`. Every typed
subclass (`NetBoxDevices`, `NetBoxVirtualMachines`, …) sets
`required_fields`, calls `findBy(...)`, and then walks each declared
field to PATCH only on real diffs. The pattern is reusable and explicit,
but it lives outside any framework.

**`netbox-proxbox`** delegates persistence to standard Django ORM via
`NetBoxModel`. Drift is detected by Django's `save()` + form validation;
NetBox's `restrict()` queryset method handles object-level permissions.
There is no equivalent of `createOrUpdate()` because the plugin doesn't
write to NetBox itself — `proxbox-api` does, using `netbox-sdk`'s
typed client.

### 7.3. Credential injection — AWX injectors vs `X-Proxbox-API-Key`

**`netbox-proxmox-automation`** namespaces the dual credential bag
(NetBox + Proxmox) using AWX's credential-type *Injectors* schema, which
materializes them as `extra_vars`:

```yaml
extra_vars:
  proxmox_env_info:
    api_host:         '{{ proxmox_api_host }}'
    api_token_secret: '{{ proxmox_api_token_secret }}'
  netbox_env_info:
    api_proto: '{{ netbox_api_proto }}'
    api_token: '{{ netbox_api_token }}'
```

Each playbook reads `proxmox_env_info.*` and `netbox_env_info.*` rather
than top-level vars. Clean, framework-supported, but tied to AWX.

**`netbox-proxbox`** uses an auto-generated bearer-style header:

```python
# FastAPIEndpoint.save() — first run
self.token = secrets.token_urlsafe(48)
super().save(...)
# fired by signal handler:
register_key_with_backend(self.token)  # POST /auth/register-key
```

Subsequent calls send `X-Proxbox-API-Key: <token>`. Token rotation is a
first-class operation (re-save the endpoint).

### 7.4. Long-running tasks — sync gunicorn vs RQ + SSE

**`netbox-proxmox-automation`** runs everything inside the gunicorn
worker that received the webhook. A clone-and-resize sequence might
take 30+ seconds; the worker is held the entire time. Polling on
`tasks/<upid>/status` is a `while True` loop in-process.

```python
while True:
    status = proxmox.nodes(node).tasks(upid).status.get()
    if status['status'] == 'stopped':
        break
    time.sleep(1)
```

**`netbox-proxbox`** decouples receipt from execution. The HTTP request
that triggers a sync only enqueues a `ProxboxSyncJob`; the actual work
runs in an RQ worker, streams progress as SSE frames from `proxbox-api`,
and is observable via the Job detail page's SSE log stream. Cancellation
is supported (`views/job_cancel.py`). The frontend polls/streams; the
worker isn't blocked.

### 7.5. Wire schemas — none vs Pydantic v2 contract mirrors

**`netbox-proxmox-automation`** has no schemas. The Flask app parses the
NetBox webhook payload as a raw dict (`json_in['data']['custom_fields']
['proxmox_node']`).

**`netbox-proxbox`** maintains Pydantic v2 mirror schemas and pins them
against a wire contract:

- `contracts/proxbox_api_sse_schema.json` — sourced from `proxbox-api`
  release `0.0.11`; defines every SSE message type, enum, and
  payload field.
- `contracts/overwrite_flags.json` — canonical 23-flag list (was 22 in
  0.0.14; the new entry is `overwrite_ip_address_dns_name`); mirrored
  in `proxbox-api/contracts/overwrite_flags.json`. Adding, removing,
  or reordering flags must happen in **both** repos in the same
  release; CI fails otherwise.
- `netbox_proxbox/schemas/backend_proxy.py` — local Pydantic v2 mirror.
- `tests/test_sse_schema_mirror.py` — fails CI if the local mirror
  drifts from the JSON contract.
- `tests/test_overwrite_flags_contract.py` — pins the canonical
  flag set across both repos.

This is the same boundary discipline used in sibling plugin
`netbox-gpon` and is a load-bearing assumption of the SSE flow: every
frame is parsed before dispatch.

---

## 8. Operational Verb Coverage Matrix

What each project actually *does* to a Proxmox cluster. ✅ = does it,
👁️ = observes/syncs only, ❌ = does not handle.

| Verb | `netbox-proxmox-automation` | `netbox-proxbox` |
|---|---|---|
| Clone VM from template | ✅ | ❌ |
| Create LXC from OS template | ✅ | ❌ |
| Set vCPU / memory | ✅ | ❌ |
| Set cloud-init `ipconfig0` | ✅ | ❌ |
| Set cloud-init SSH public key | ✅ | ❌ |
| Set LXC `net0` (bridge / IP / firewall) | ✅ | ❌ |
| Start VM / LXC | ✅ | ❌ |
| Stop VM / LXC | ✅ | ❌ |
| Delete VM / LXC | ✅ | ❌ |
| Add VM disk | ✅ (SCSI only) | ❌ |
| Resize VM disk | ✅ | ❌ |
| Resize LXC `rootfs` | ✅ | ❌ |
| Remove VM disk | ✅ | ❌ |
| Migrate VM between nodes | ✅ | ❌ |
| Migrate LXC | ❌ (Proxmox limitation) | ❌ |
| Take snapshot | ❌ | 👁️ (sync only) |
| Restore snapshot | ❌ | ❌ |
| Delete snapshot | ❌ | ❌ |
| Trigger backup (vzdump) | ❌ | ❌ |
| Read backups (`VMBackup`) | ❌ | 👁️ |
| Read backup routines | ❌ | 👁️ |
| Read replication jobs | ❌ | 👁️ |
| Read task history (UPIDs) | ❌ | 👁️ |
| Discover cluster + nodes | ✅ (one-shot, SSH+API) | 👁️ (continuous via backend) |
| Discover VMs | ✅ (one-shot) | 👁️ |
| Discover storage | ❌ (only via plugin's setup script for choice set) | 👁️ |
| Reflect VNC console URL in NetBox | ❌ | 👁️ (template extension) |
| Resolve LXC `VMConfig.hostname` | ❌ | ✅ (0.0.11 backend) |
| Resolve QEMU hostname via `qemu-guest-agent` | ❌ | ✅ (0.0.11 backend; `agent/get-host-name`, fall-back via network-interfaces payload) |
| Write IPAM `IPAddress.dns_name` from Proxmox guest hostname | ❌ | ✅ (0.0.11 backend, gated by `overwrite_ip_address_dns_name`) |
| Update DNS (BIND9) | ⚠️ Roadmap (Jinja2 template exists, no write step) | ❌ |

Summary: `netbox-proxmox-automation` is a **doer** for VM/LXC
lifecycles but a thin observer; `netbox-proxbox` is a **mirror** that
covers more Proxmox object kinds. As of `0.0.11`, the mirror also
**writes** Proxmox guest hostnames into NetBox IPAM `dns_name` — a
narrow but real exception to the otherwise read-only stance.

---

## 9. When to Use Which

- **You're building a new lab and want NetBox to be the source of truth
  for everything (network, IPAM, virtualization desired state) →**
  `netbox-proxmox-automation`. Author VMs in NetBox, let event rules
  do the rest.

- **You have an existing Proxmox cluster and need NetBox to reflect its
  reality (DCIM, IPAM, VM inventory, backup history) →** `netbox-proxbox`.
  Stand up `proxbox-api`, wire endpoints, hit Full Update.

- **You need both authoring and observability →** Run both. They don't
  collide on object types, but be aware of the custom field name
  collisions (Section 10).

- **You can only run one and you need rich UI in NetBox →**
  `netbox-proxbox` (the upstream project intentionally has no UI).

- **You can only run one and you need event-driven side effects from
  NetBox changes →** `netbox-proxmox-automation` (the plugin doesn't
  do this).

---

## 10. Compatibility & Coexistence

Can both run on the same NetBox instance? **Yes, technically**, but
watch for these collision points:

| Surface | Risk | Notes |
|---|---|---|
| Custom field names `proxmox_node`, `proxmox_vmid`, `proxmox_vm_type` | ⚠️ Both projects use these names | If `netbox-proxmox-automation`'s setup script runs after `proxbox-api`'s sync, choice sets may differ but field names should match. Test in staging before mixing. |
| Custom field choice sets | ⚠️ Only the upstream project creates `extras.custom_field_choice_sets` rows | The plugin doesn't, so no collision. |
| Event rules / webhooks | ✅ No collision | The plugin doesn't create any. |
| Tag namespace | ⚠️ Watch for `proxmox-vm-discovered` clash if the plugin's backend also tags discovered VMs | Inspect backend behavior. |
| RQ queues | ✅ No collision | Plugin uses `default`; the upstream project uses no queue. |
| API namespace | ✅ No collision | Plugin uses `/api/plugins/proxbox/`; the upstream project doesn't expose any plugin REST API. |
| `extras.webhooks` | ✅ No collision | Plugin creates none. |
| Custom field group names (`Proxmox (common)`, etc.) | ⚠️ Only the upstream project creates these | Plugin doesn't, so no collision. |

The safest coexistence pattern is:

1. Provision `netbox-proxmox-automation`'s NetBox-side objects first
   (custom fields, choice sets, event rules).
2. Install and configure `netbox-proxbox` second, pointing it at the
   *same* NetBox instance.
3. Verify that backend sync doesn't overwrite custom fields the
   upstream project owns.

---

## 11. Glossary

| Term | Belongs to | Meaning |
|---|---|---|
| AWX / Tower / AAP | upstream | Ansible Automation Platform variants — the executor for the upstream project's webhook path. |
| `app_config.yml` | upstream | Flask app's runtime config; not the same as `conf.d/netbox_setup_objects.yml`. |
| `community.proxmox` | upstream | Ansible collection providing `proxmox_*` modules. |
| Credential Type | upstream / AWX | Schema declaring inputs + injectors; namespaces NetBox+Proxmox creds. |
| Cloud-init `ipconfig0` | upstream | Proxmox cloud-init field set by `awx-proxmox-set-ipconfig0.yml`. |
| `createOrUpdate` | upstream | Drift-detecting NetBox writer pattern in `helpers/netbox_objects.py`. |
| Event rule | upstream | NetBox object that fires a webhook on model events. |
| EE (Execution Environment) | upstream / AWX | Container image bundling Python + Ansible collections. |
| Flask app | upstream | Bundled webhook receiver in `netbox-event-driven-automation-flask-app/`. |
| `proxmoxer` | upstream | Python Proxmox API client (used in Flask helper). |
| UPID | both | Unique Proxmox task ID; used to poll task status. |
| `vzdump` | both | Proxmox backup tool; output formats are `.zst` / `.tzst` / PBS chunks. |
| Branching plugin | both | Optional NetBox plugin enabling change branches; upstream uses it at setup time only. |
| `proxbox-api` | this repo | Sibling FastAPI service that does all Proxmox & NetBox work for the plugin. |
| `proxmox-sdk` | this repo | Schema-driven Proxmox client used by `proxbox-api`. |
| `netbox-sdk` | this repo | Typed NetBox API client used by `proxbox-api`. |
| `ProxboxSyncJob` | this repo | RQ JobRunner in `netbox_proxbox/jobs.py`. |
| `ProxboxPluginSettings` | this repo | Singleton Django model holding all runtime tunables. |
| `EndpointBase` | this repo | Abstract model for `ProxmoxEndpoint`/`NetBoxEndpoint`/`FastAPIEndpoint`. |
| `X-Proxbox-API-Key` | this repo | Custom auth header used by the plugin to talk to `proxbox-api`. |
| SSE | this repo | Server-Sent Events; the protocol over which `proxbox-api` streams sync progress. |
| `pxb` | this repo | Optional Typer CLI shipped under `proxbox_cli/`. |
| `use_https` | this repo (0.0.15) | New boolean field on `FastAPIEndpoint` controlling URL scheme (`http://` vs `https://`); independent of `verify_ssl`. |
| `runtime_settings` | this repo (backend 0.0.11) | `proxbox_api/runtime_settings.py` helpers (`get_int / get_float / get_bool / get_str`) that resolve env var → `ProxboxPluginSettings` → built-in default with a 5-minute cache. |
| `OVERWRITE_FIELDS` / `OVERWRITE_FIELD_GROUPS` | this repo | Canonical, ordered registry of overwrite flags shared between the plugin Settings UI and `SyncOverwriteFlags.model_fields`; pinned by `contracts/overwrite_flags.json` (23 entries in 0.0.15). |
| `_endpoint_errors` | this repo (0.0.15) | `services/_endpoint_errors.py` — translates `400 plain HTTP request was sent to HTTPS port` and `SSLError` into operator-actionable strings on the FastAPI endpoint detail page. |
| `routes/admin/encryption.py` | this repo (backend 0.0.11) | Runtime endpoints to fetch and rotate `PROXBOX_ENCRYPTION_KEY` without restarting the FastAPI process. |

---

## 12. Cross-Reference Index

- Companion deep-dive on the upstream project:
  [`./NETBOX-PROXMOX-AUTOMATION.md`](./NETBOX-PROXMOX-AUTOMATION.md).
- This plugin's primary developer guide:
  [`../CLAUDE.md`](../CLAUDE.md).
- This plugin's contributor & dev environment guide:
  [`../CONTRIBUTING.md`](../CONTRIBUTING.md),
  [`../DEVELOP.md`](../DEVELOP.md).
- Legacy `PLUGINS_CONFIG` reference (pre-DB endpoints):
  [`../PAST_CONFIG.md`](../PAST_CONFIG.md).
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
- Upstream project source:
  `/root/nms/netbox-proxmox-automation/`.

---

*End of comparison.*
