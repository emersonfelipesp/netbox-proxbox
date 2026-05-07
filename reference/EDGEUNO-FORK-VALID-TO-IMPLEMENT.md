# EdgeUno Fork — Features Valid to Implement Upstream

This document is an **action list**. It distils
[`EDGEUNO-NETBOX-PROXMOX.md`](./EDGEUNO-NETBOX-PROXMOX.md) (the
standalone deep-dive on the EdgeUno fork at
`/root/nms/edgeuno/netbox-proxbox`) and
[`PROXBOX-FORK-EDGEUNO.md`](./PROXBOX-FORK-EDGEUNO.md) (the side-by-side
comparison against current `netbox-proxbox 0.0.15` + `proxbox-api
0.0.11`) into a single inventory of capabilities from the EdgeUno fork
that are worth porting upstream and are not yet present.

Read those two documents first if you need the *why* behind any cell in
this one. This file does not re-explain either project; it only answers
the question **"what should we steal from EdgeUno, where does it land,
and in what order?"**.

---

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [TL;DR](#2-tldr)
3. [Methodology](#3-methodology)
4. [Recommended Imports](#4-recommended-imports)
   - 4.1 [Tenant assignment by VM-name regex](#41-tenant-assignment-by-vm-name-regex)
   - 4.2 [`description`-field parsing](#42-description-field-parsing-for-client--email--main-ip--ip-address-allocation)
   - 4.3 [Role pinning by VM type](#43-role-pinning-by-vm-type-vps-for-qemu-lxc-for-lxc)
   - 4.4 [Django management command for sync trigger](#44-django-management-command-for-sync-trigger)
   - 4.5 [Standalone container scheduler with four `PROXBOX_MODE` branches](#45-standalone-container-scheduler-with-four-proxbox_mode-branches)
   - 4.6 [One-shot `docker-compose-single-exec.yml` pattern](#46-one-shot-docker-compose-single-execyml-pattern)
   - 4.7 [`proxbox_runner.sh`-style auto-`manage.py`-locating CLI subcommand](#47-proxbox_runnersh-style-auto-managepy-locating-cli-subcommand)
   - 4.8 [Duplicate-VM-name `" (2)"` suffix collision handling](#48-duplicate-vm-name--2-suffix-collision-handling)
   - 4.9 [`latest_job` UUID stamp + stale-record cleanup pass](#49-latest_job-uuid-stamp--stale-record-cleanup-pass)
   - 4.10 [`ProxboxSession`-style per-cluster session model](#410-proxboxsession-style-per-cluster-session-model-in-proxbox-api)
5. [Explicit Non-Imports](#5-explicit-non-imports)
6. [Implementation Sequencing](#6-implementation-sequencing)
7. [Cross-References](#7-cross-references)

---

## 1. Purpose & Scope

`netbox-proxbox 0.0.15` and `proxbox-api 0.0.11` were certified together
on 2026-05-07. They are a two-service stack: a NetBox plugin observes
Proxmox state, and a separate FastAPI backend executes the actual
Proxmox-to-NetBox transformation, streaming results back over SSE. The
EdgeUno fork at `/root/nms/edgeuno/netbox-proxbox` diverged from a much
earlier point of the same `netdevopsbr/netbox-proxbox` lineage. It is a
single-process plugin: every line of sync logic — including the v2
async pipeline at `proxbox_api_v2/scrapper.py:88` (`Scrapper.async_run`)
— runs inside NetBox's gunicorn workers or its `proxboxscrapper`
management command.

That structural difference is why most of the EdgeUno-specific code
**cannot** be lifted as-is. Anything that depends on
`PROXMOX_SESSIONS_LIST` being a module-global list of `ProxboxSession`
instances, or on `configuration_options.json` being readable from the
plugin process, or on writes happening inside the Django request /
worker that triggered the sync, has no analog upstream and must be
re-modelled around the existing RQ → SSE → reconcile pipeline.

But several capabilities the EdgeUno operator added on top of that
older code base **are** valid here, are not yet present, and slot
naturally into the upstream patterns. This document catalogues them.
Section 4 is the *yes* list, with a fixed seven-field template for
each entry. Section 5 is the *no* list, with the policy citation for
each.

This document does not propose a release; it does not write code; it
does not assign owners. Treat it as the input to a roadmap planning
session, paired with [`docs/roadmap.md`](../docs/roadmap.md).

---

## 2. TL;DR

Ten import candidates, three priority tiers:

| Tier | Item | Lands |
|------|------|-------|
| High | 4.1 Tenant assignment by VM-name regex | New `tenant_regex` on `ProxmoxEndpoint` + backend hook |
| High | 4.2 `description`-field parsing | Four new opt-in overwrite flags |
| Medium | 4.3 Role pinning by VM type | Two `ProxboxPluginSettings` fields |
| High | 4.4 Django management command for sync trigger | `netbox_proxbox/management/commands/proxbox_sync.py` |
| Medium | 4.5 Standalone scheduler container (`off`/`continuous`/`interval`/`cron`) | Sibling Docker image only |
| Medium | 4.6 One-shot `docker-compose-single-exec.yml` | `docs/installation/` |
| Low | 4.7 Auto-`manage.py`-locating wrapper | `pxb sync run --enqueue` subcommand |
| Medium | 4.8 Duplicate-VM-name `" (2)"` suffix collision handling | `proxbox-api` reconciler + new SSE frame |
| High | 4.9 `latest_job` UUID stamp + stale-record cleanup | New custom field + new `delete_orphans` flag |
| Low | 4.10 `ProxboxSession`-style per-cluster session model | Optional `proxbox-api` refactor |

Ten explicit *non*-imports rooted in
[`CLAUDE.md`](../CLAUDE.md) policy: JSON-on-disk credentials,
`ssl_verify=False`, `print()`-based logging, `eval()` in templatetags,
`ChangeLoggedModel` base, web-triggered synchronous sync, hardcoded
example tokens, `nb_cluster_type.DoesNotExist` swallow-and-continue,
duplicate v1+v2 sync engines, and the version mismatch between
`setup.py`/`pyproject.toml` and `PluginConfig.version`. See §5 for the
justification for each.

---

## 3. Methodology

### 3.1 Inclusion criteria

A capability qualifies as a recommended import if and only if all four
hold:

1. **It is present in the EdgeUno fork.** Either as runtime behaviour or
   as a deployable artefact (compose file, scheduler script, management
   command).
2. **It is absent in `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11`.**
   Confirmed via the §6 comparison matrix in
   [`PROXBOX-FORK-EDGEUNO.md`](./PROXBOX-FORK-EDGEUNO.md).
3. **It is compatible with the two-service architecture.** Plugin-side
   work can read `ProxboxPluginSettings` and call the backend over
   HTTP/SSE; backend-side work runs inside `proxbox-api` and may stream
   SSE frames. Anything that requires Proxmox or NetBox writes from
   inside the plugin process is rejected (it would re-introduce the
   "held gunicorn worker" anti-pattern).
4. **It does not conflict with [`CLAUDE.md`](../CLAUDE.md) policy.** The
   pre-commit checklist (`compileall`, `rtk ruff check`, `rtk pytest`,
   `rtk ty check`), the framework stack preference (NetBox plugin →
   NetBox core → Django → 3rd-party), the DB-first config policy
   citing migration `0037_pluginsettings_runtime_tunables.py`, and the
   security model around `ObjectPermissionRequiredMixin` /
   `ConditionalLoginRequiredMixin` /
   `ContentTypePermissionRequiredMixin` are all binding.

### 3.2 Exclusion criteria

A capability is rejected, regardless of its operator value, if porting
it would require any of the following:

- Demoting any model from `NetBoxModel` to `ChangeLoggedModel`.
- Removing the `PROXBOX_ENCRYPTION_KEY` Fernet store on the backend
  side, or moving credentials back to a JSON file on disk.
- Removing or weakening the Pydantic v2 contract mirrors at
  `netbox_proxbox/schemas/backend_proxy.py` and the SSE schema mirror
  test at `tests/test_sse_schema_mirror.py`.
- Removing or weakening the 23-flag overwrite contract pinned by
  `contracts/overwrite_flags.json` and validated by
  `tests/test_overwrite_flags_contract.py`.
- Introducing `print()`-based logging or `eval()` anywhere in the
  plugin or backend.
- Bypassing the RQ + SSE pipeline. Long-running work belongs on the
  `default` queue with `job_timeout=PROXBOX_SYNC_JOB_TIMEOUT` (7200s),
  paired with the SSE between-chunk read timeout (3600s) inside
  `run_sync_stream`.

### 3.3 Mapping

Every entry in §4 specifies a concrete destination — file paths in
`/root/nms/netbox-proxbox/` and/or `/root/nms/proxbox-api/`,
which side of the two-service boundary each piece sits on, and which
existing pattern it should imitate (an existing model, migration,
overwrite flag, view, or service, cited by path and line). The
canonical reference pattern is the `0.0.15` release that introduced
`overwrite_ip_address_dns_name`, `use_https`, the `_endpoint_errors`
helper, and migrations `0038` / `0039`. See
[`docs/release-notes/version-0.0.15.md`](../docs/release-notes/version-0.0.15.md)
for the full inventory of what a "new opt-in flag" change touches:
model field → migration with `IF NOT EXISTS` → form / serializer /
table surface → `_build_base_query_params` query-string forwarding →
backend handler → AST contract test.

`OVERWRITE_FIELDS` and `OVERWRITE_FIELD_GROUPS` live at
`netbox_proxbox/constants.py:5,64`; every new flag must update both,
plus the JSON manifest at `contracts/overwrite_flags.json`, plus the
sibling manifest in the `proxbox-api` repo. The drift detector test at
`tests/test_overwrite_flags_contract.py` will fail loudly otherwise —
that is the intended canary.

---

## 4. Recommended Imports

Each entry below uses the same seven-field template. Read vertically
within an entry; read horizontally across entries to compare priority
and scope. All EdgeUno source paths are rooted at
`/root/nms/edgeuno/netbox-proxbox/` unless qualified otherwise. All
upstream paths are rooted at `/root/nms/netbox-proxbox/` (plugin) or
`/root/nms/proxbox-api/` (backend).

---

### 4.1 Tenant assignment by VM-name regex

**Priority.** High.

**EdgeUno source.** `proxbox_api_v2/scrapper.py` and
`proxbox_api_v2/configuration.py`. The fork's
`NETBOX_TENANT_REGEX_VALIDATOR` field is read out of
`configuration_options.json` and applied during VM upsert: when a VM
name matches the regex, its first capture group is treated as a tenant
slug and the matching `tenancy.Tenant` record is assigned to the
`virtualization.VirtualMachine.tenant` FK. EdgeUno also documents the
regex shape in `EDGEUNO-NETBOX-PROXMOX.md` §6.

**Why it is worth importing.** Multi-tenant ISPs and hosting providers
encode the tenant in the VM name itself (e.g. `acme-web-01`,
`globex-db-02`). Without a regex hook, every synced VM lands
tenant-less and an operator has to walk the IPAM list and assign
tenants manually after every full sync. The same workflow is what
makes NetBox's IPAM tenant assignment useful in the first place; the
synchronisation step should not drop the signal Proxmox already
carries.

**Why it has not landed yet.** The upstream observer pattern is
deliberately tenant-agnostic: it mirrors what Proxmox knows and lets
NetBox enrich it. EdgeUno added this because they had to — they had
hundreds of VMs and no other tenant signal — and the hook ended up in
the same JSON file that holds credentials, which made it impossible to
import without the rest of `configuration_options.json`. With the
DB-first config policy in place (migration `0037`), this is now a clean
single-field migration.

**Target landing site in this repo.**

- **Plugin model.** New field on `ProxmoxEndpoint`, not on
  `ProxboxPluginSettings`. Different Proxmox clusters have different
  tenant naming conventions, and the per-endpoint override pattern
  introduced by `overwrite_ip_address_dns_name` (migration `0039`,
  nullable tri-state) is the right fit.
  - File: `netbox_proxbox/models/proxmox_endpoint.py`.
  - Field: `tenant_regex = models.CharField(max_length=255, blank=True)`.
- **Migration.** New file
  `netbox_proxbox/migrations/0040_proxmoxendpoint_tenant_regex.py`,
  using `SeparateDatabaseAndState` with `ALTER TABLE … ADD COLUMN
  IF NOT EXISTS`, mirroring `0037` and `0039`.
- **Form / serializer / table.** Add the field everywhere the sibling
  per-endpoint flags appear:
  `netbox_proxbox/forms/proxmox.py`,
  `netbox_proxbox/api/serializers/endpoints.py`,
  `netbox_proxbox/tables/` (for the Proxmox endpoints list).
- **Query string forwarding.** New key in
  `netbox_proxbox/sync_params.py::_build_base_query_params`.
- **Backend.** New parameter on the per-endpoint sync entry point
  in `proxbox-api/proxbox_api/proxmox_to_netbox/`. Compile the regex
  once per run; assign tenant by `slug` lookup or fall back to `name`
  lookup; never auto-create tenants.
- **Test.** Pin field name and migration shape with an AST source-
  contract test mirroring `tests/test_form_and_helper_source_contracts.py`.

**Migration sketch.**

1. Add the column on `ProxmoxEndpoint`. Migration is additive, default
   blank, nullable not required.
2. Surface in form, serializer, table, detail page.
3. Forward as a flat query-string key from
   `_build_base_query_params`.
4. On the backend, accept the parameter, compile the regex once per
   run, and apply during VM upsert. Tenants are looked up — never
   created — to keep the observer pattern intact.
5. Add an AST contract test asserting the field is wired to all five
   surfaces (model, migration, form, serializer, table).

**Risks & open questions.** Should the tenant be looked up by `slug`
or `name`? Slug is safer (slugs are unique by definition) but operators
may expect human-readable names to work. Should an unmatched regex
clear an existing tenant assignment, or leave it alone? Default to
"leave it alone" to avoid clobbering manual edits; gate the destructive
behaviour behind a future `clear_unmatched_tenant` flag.

---

### 4.2 `description`-field parsing for `client:` / `email:` / `main ip:` / `ip address allocation:`

**Priority.** High.

**EdgeUno source.** `proxbox_api_v2/scrapper.py` parses the Proxmox
`description` field line-by-line for four key-value markers — `client:`,
`email:`, `main ip:`, `ip address allocation:` — and writes the parsed
values into `Tenant`, `Contact`, and `IPAddress` records. See
`EDGEUNO-NETBOX-PROXMOX.md` §6 for the full grammar.

**Why it is worth importing.** The Proxmox `description` field is the
*only* freeform metadata channel Proxmox exposes per-VM. ISPs and
hosting providers already use it to record the customer, the contact
email, and the public IP allocation, because there is nowhere else to
put that data. If `netbox-proxbox` does not parse it, every operator
ends up either copying that data twice (Proxmox + NetBox) or scripting
the parse themselves outside the sync loop. The 0.0.15 release already
established that one-off enrichment writes (`dns_name`) belong inside
the sync, gated by an opt-in flag.

**Why it has not landed yet.** The upstream observer is intentionally
schema-driven: it writes only what Proxmox has typed fields for. Free-
text parsing introduces failure modes (typos, regex drift, partial
matches) that the observer was built to avoid. The fix is the same
pattern 0.0.15 used for `dns_name`: opt-in flags, default *off* for the
parts that touch user-editable NetBox fields, and *on* only for the
parts that mirror what Proxmox already says.

**Target landing site in this repo.**

- **Four new overwrite flags** on `ProxboxPluginSettings` (global) +
  `ProxmoxEndpoint` (per-endpoint tri-state override), modelled exactly
  on `overwrite_ip_address_dns_name`:
  - `overwrite_tenant_from_description` — feeds VM `tenant` FK.
  - `overwrite_contact_from_description` — feeds `tenancy.Contact`
    creation/lookup.
  - `overwrite_main_ip_from_description` — feeds VM `primary_ip4` /
    `primary_ip6`.
  - `overwrite_ip_allocation_from_description` — feeds
    `ipam.IPAddress` records on the VM's primary interface.
- **Constants.** Add four entries to `OVERWRITE_FIELDS` at
  `netbox_proxbox/constants.py:64` and to the appropriate group in
  `OVERWRITE_FIELD_GROUPS` at
  `netbox_proxbox/constants.py:5`. Two go in the IP Address group;
  two go in a new Tenancy group.
- **Migration.** Single migration adding all four columns to both
  models, mirroring `0039`. Use `SeparateDatabaseAndState` +
  `ALTER TABLE … IF NOT EXISTS`.
- **Contract.** Update `contracts/overwrite_flags.json` and the
  sibling manifest in `proxbox-api`. The drift detector at
  `tests/test_overwrite_flags_contract.py` will enforce both sides.
- **Backend parser.** New helper in
  `proxbox-api/proxbox_api/services/description_parser.py`. Strict
  parser: line-prefix match only, case-insensitive, trim whitespace,
  reject malformed values silently (no crash on operator typos).

**Migration sketch.**

1. Add four flags to `OVERWRITE_FIELDS` and groups; update both
   manifests; let the drift test fail; commit the manifest fix.
2. Add migration on both models; surface in form / serializer / table.
3. Forward all four as flat query-string keys.
4. Implement the backend parser; cover with unit tests.
5. Wire each parsed field into the existing reconcile path
   (tenant/contact/IP address) under its flag.
6. Document the four flags in the next release notes file with the
   same shape as `version-0.0.15.md`'s `dns_name` section.

**Risks & open questions.** What encoding convention wins when the
description says `email: foo@bar.com` and a contact already exists with
a different email? Default: per-flag, never overwrite an existing value
unless the corresponding `overwrite_*` flag is `True`. Should the
parser be regex-configurable per endpoint? Probably not in v1 —
hard-coded prefixes match the EdgeUno grammar and avoid a regex-of-
regexes UX. Revisit if operators ask for it.

---

### 4.3 Role pinning by VM type (`VPS` for qemu, `LXC` for lxc)

**Priority.** Medium.

**EdgeUno source.** `proxbox_api_v2/scrapper.py` pins
`virtualization.VirtualMachine.role` to a NetBox `DeviceRole` named
`"VPS"` for QEMU guests and `"LXC"` for LXC containers, hardcoded.
EdgeUno's `EDGEUNO-NETBOX-PROXMOX.md` §13 also notes the
`nb_cluster_type.DoesNotExist` style of "look up by name; if missing,
crash" that the original code paired this with — which is *not* what
we want here.

**Why it is worth importing.** Without role pinning, Proxmox VMs land
with a blank `role` and operators have to set them in bulk afterwards.
NetBox's IPAM and DCIM filters lean on `role` heavily, so this is
operator quality-of-life. The "by VM type" split (qemu vs lxc) is a
clean signal Proxmox already provides.

**Why it has not landed yet.** Hardcoded role names are an EdgeUno-
specific assumption; a different operator may want `"Virtual Machine"`
and `"Container"` instead. Upstream needs the value to be operator-
configurable, and the canonical configuration medium since 0.0.13 has
been `ProxboxPluginSettings`.

**Target landing site in this repo.**

- **Plugin model.** Two new fields on `ProxboxPluginSettings`,
  defaulting to **blank** (i.e. the new behaviour is opt-in and
  preserves current behaviour for existing installs):
  - `default_role_qemu` — text field, looked up against
    `dcim.DeviceRole.name`. Blank → no role assigned.
  - `default_role_lxc` — same.
  - File: `netbox_proxbox/models/plugin_settings.py`.
- **Migration.** New file mirroring
  `0037_pluginsettings_runtime_tunables.py`. Two columns, both
  `CharField(max_length=100, blank=True, default="")`.
- **Settings form / serializer / template.** Surface in the existing
  Settings tab. `runtime_settings.get_str()` on the backend resolves
  env → DB → default with the 5-minute cache.
- **Backend.** Resolve the two `DeviceRole` IDs once at sync start
  (single `GET /api/dcim/device-roles/?name=...` per pair); reuse on
  every VM upsert. **Crucially**: if the role does not exist, log a
  one-line warning at the start of the sync and skip role assignment
  for that VM type for the rest of the run. Never crash — see §5 for
  the EdgeUno antipattern this replaces.

**Migration sketch.**

1. Add two `CharField` columns to `ProxboxPluginSettings` with a
   migration following `0037`'s shape.
2. Surface in the settings form / serializer / template under a new
   "Roles" group.
3. On the backend, look up the two roles once at sync start and pass
   resolved IDs through the per-VM reconcile path.
4. Add a unit test pinning the "missing role → log + skip, do not
   crash" behaviour.

**Risks & open questions.** Should this also apply to existing VMs
that already have a role set? Default: no — only fill in blank
`role`s, never overwrite. If operators want overwrite behaviour, gate
it behind a future `overwrite_role` flag that follows the §4.2
pattern. What happens if both a regex and a description-parsed value
target the same field? The description parser wins, then the role
pin, then nothing — i.e. most-specific-source-first.

---

### 4.4 Django management command for sync trigger

**Priority.** High.

**EdgeUno source.** `proxbox_api_v2/management/commands/proxboxscrapper.py`.
The fork's command instantiates `Scrapper`, calls `async_run`, and
**executes** the sync inside the management-command process. EdgeUno's
`EDGEUNO-NETBOX-PROXMOX.md` §5.2 documents this as the v2 entry point.

**Why it is worth importing.** Operations teams use cron, systemd
timers, Kubernetes `CronJob`s, and Ansible playbooks. None of those
talk HTTP comfortably. Today, the only way to kick a sync upstream is a
POST to `/views/job_run.py`, which means every operator has to script
an authenticated HTTP call against NetBox. A management command makes
this a one-liner: `python manage.py proxbox_sync` inside the NetBox
container.

**Why it has not landed yet.** The plugin grew up around the dashboard
button + RQ pipeline. There has not been a clean reason to add another
trigger surface, and EdgeUno's example does the *wrong* thing — it
runs the sync synchronously inside the command, which prevents any
cancel / progress / log inspection. The right shape is "enqueue, then
exit", which is a 30-line command bridging to existing
`ProxboxSyncJob.enqueue`.

**Target landing site in this repo.**

- **New command.**
  `netbox_proxbox/management/commands/proxbox_sync.py`. Mirrors the
  shape of the existing `proxbox_fix_tokens.py` command. Reads the
  same `ProxmoxEndpoint` queryset the dashboard does; calls
  `ProxboxSyncJob.enqueue(...)` for each (or for the operator-
  selected subset via `--endpoint <name>`).
- **Documentation home.** A `netbox_proxbox/management/CLAUDE.md`
  already exists in the repo's CLAUDE index, so the new command drops
  into a documented location.
- **Flags.**
  - `--endpoint <name>` — filter to one endpoint (repeatable).
  - `--wait` — block until terminal; tail the `Job.log` field once a
    second; exit non-zero if the job ends in `errored` / `failed`.
    Default: enqueue and return 0 immediately.
  - `--timeout <seconds>` — hard cap on `--wait` polling.
  - `--queue <name>` — override the default RQ queue for parity with
    `ProxboxSyncJob.enqueue(queue=...)`.
- **Tests.** AST source-contract test pinning the command name, the
  flag list, and the `enqueue` import — mirroring
  `tests/test_form_and_helper_source_contracts.py` and
  `tests/test_cli_contracts.py`.

**Migration sketch.**

1. Drop the new file at
   `netbox_proxbox/management/commands/proxbox_sync.py`. No DB
   migration; no model change; no contract update.
2. Implement `--endpoint`, `--wait`, `--timeout`, `--queue`.
3. Cover with one AST contract test and one functional test that
   patches `ProxboxSyncJob.enqueue` and asserts it was called once
   per filtered endpoint.
4. Document under `docs/usage/` with two examples (cron + Kubernetes
   `CronJob`).

**Risks & open questions.** What does `--wait` do if the worker is
not running? Default: print a one-line warning after 30s and continue
polling; that matches the dashboard behaviour. Should `--wait`
stream the SSE log in real time? Out of scope for v1 — the
management command should stay a thin shim. Streaming SSE belongs in
the dedicated `pxb` CLI subcommand (§4.7).

---

### 4.5 Standalone container scheduler with four `PROXBOX_MODE` branches

**Priority.** Medium.

**EdgeUno source.** `scanner_scheduler.py` (210 lines) wired in via
`docker-compose.yaml`. Four modes selected by the `PROXBOX_MODE`
environment variable: `off`, `continuous`, `interval`, `cron` (the
last via the `croniter` package, installed only in EdgeUno's
`Dockerfile` — not in `pyproject.toml` or `setup.py`).
`EDGEUNO-NETBOX-PROXMOX.md` §7 documents the loop shape.

**Why it is worth importing.** Operators who do not own the NetBox
container (managed-NetBox tenants, hosted deployments) cannot install
a system cron, but they can ship a sidecar container. EdgeUno's design
— a tiny long-lived scheduler that calls a one-shot sync endpoint on
a cadence — is exactly the pattern a sidecar wants. With §4.4 in
place, the sidecar's job is reduced to "pick a moment, then `kubectl
exec netbox -- python manage.py proxbox_sync` (or its docker equivalent)".

**Why it has not landed yet.** The plugin's RQ scheduler covers the
common case, and adding a Python loop inside the plugin process would
duplicate that. The fix is to ship the scheduler as a *separate*
container that owns nothing — no DB, no NetBox model, no plugin
config — and just wraps §4.4's command on a cadence.

**Target landing site in this repo.**

- **New Docker image.** A new directory at
  `docker/scheduler/` containing a minimal `Dockerfile` (Python
  slim base + `croniter` + a thin Python entry script) and a single
  `entrypoint.py` modelled on EdgeUno's `scanner_scheduler.py` but
  stripped of the `Scrapper` import path; instead of running sync
  in-process it `subprocess.run`s `python manage.py proxbox_sync`
  inside whichever container is pointed at by the
  `NETBOX_CONTAINER_EXEC` env var (or, in Kubernetes, it just exits
  and lets a CronJob handle scheduling).
- **Optional dependency, not core.** Add `croniter` only as an
  optional extra in `pyproject.toml` under
  `[project.optional-dependencies]`, e.g. `scheduler = ["croniter"]`.
  The plugin install footprint **must not** grow.
- **CI.** Add a tiny build-only step to `.github/workflows/` that
  builds the new image but does not run end-to-end tests against it
  (the e2e matrix is already saturated).

**Migration sketch.**

1. Land §4.4 first.
2. Add `docker/scheduler/Dockerfile`, `entrypoint.py`, and a
   minimal `README.md`.
3. Add the `scheduler` optional extra to `pyproject.toml`.
4. Add a build-only CI step; do not attempt to wire it into the
   existing `e2e-docker.yml` matrix.
5. Document under `docs/installation/` next to the existing compose
   files.

**Risks & open questions.** Should we ship a pre-built image to Docker
Hub? Probably yes, paired with the existing release pipeline, but
gated behind an explicit `publish_scheduler_image` workflow input.
Should the scheduler share the `proxbox-api` release cadence or the
plugin's? The plugin's, since that is where the management command
lives.

---

### 4.6 One-shot `docker-compose-single-exec.yml` pattern

**Priority.** Medium.

**EdgeUno source.** `docker-compose-single-exec.yml`. A two-service
compose that builds the plugin image, runs the management command
once, and exits. Used in CI and for ad-hoc backfills.

**Why it is worth importing.** Useful for two scenarios upstream
operators already hit: (a) one-shot post-upgrade reconciles where a
full sync needs to be triggered out-of-band, and (b) CI smoke tests
that want to run a sync end-to-end without keeping a long-running
NetBox process around.

**Why it has not landed yet.** The shipped compose files target the
production "long-running container with a worker" shape. EdgeUno's
single-exec compose is a minor variant of that, not a different
architecture.

**Target landing site in this repo.**

- **New compose file.**
  `docs/installation/docker-compose-single-exec.yml` (kept under
  `docs/` so it is documentation, not bundled runtime). It
  `command: python manage.py proxbox_sync --wait`s and exits, with
  `restart: "no"`.
- **Documentation.** New section in
  `docs/installation/3-installing-plugin-docker.md` (or sibling
  page) explaining when to use it.

**Migration sketch.**

1. Land §4.4 first; this file depends on the new command.
2. Drop the compose file under `docs/installation/`.
3. Add a 200-word section to the installation doc with two example
   invocations (CI gate + post-upgrade backfill).

**Risks & open questions.** None worth listing; this is documentation.

---

### 4.7 `proxbox_runner.sh`-style auto-`manage.py`-locating CLI subcommand

**Priority.** Low.

**EdgeUno source.** `proxbox_runner.sh`, a bash script that walks up
the filesystem looking for `manage.py` and runs the management
command from wherever it finds it. Useful when an operator is
shelled into the NetBox container at an arbitrary working directory.

**Why it is worth importing.** Quality-of-life. Operators new to the
plugin do not always know that `manage.py` lives at the NetBox root
and not the plugin root.

**Why it has not landed yet.** A bash script in the plugin repo is
not idiomatic; the existing `pxb` CLI already covers the "thin
wrapper around plugin operations" concern.

**Target landing site in this repo.**

- **New `pxb` subcommand.**
  `proxbox_cli/commands/sync.py`, registered in the existing
  `proxbox_cli/__init__.py` Typer app. Subcommand:
  `pxb sync run --enqueue [--endpoint NAME] [--wait]`. Internally it
  locates `manage.py` (env var `NETBOX_ROOT`, then walk-up, then
  `/opt/netbox/netbox/manage.py`) and `subprocess.run`s the §4.4
  command.
- **Tests.** Mirror `tests/test_cli_contracts.py`.

**Migration sketch.**

1. Land §4.4 first.
2. Add the `pxb sync run` subcommand wiring.
3. AST contract test + one functional test that patches
   `subprocess.run`.

**Risks & open questions.** Should `pxb sync run` work without
`--enqueue`, i.e. trigger the sync via the HTTP API instead of the
management command? Probably yes as a follow-up — the HTTP path is
the only one available to operators outside the container. Out of
scope for v1.

---

### 4.8 Duplicate-VM-name `" (2)"` suffix collision handling

**Priority.** Medium.

**EdgeUno source.** `proxbox_api_v2/scrapper.py` upserts VMs by
matching on `(cluster, name)`; on collision (two Proxmox VMs with the
same name across nodes in a cluster, or a NetBox VM with the same
name on a different cluster), it appends `" (2)"` to disambiguate.
`EDGEUNO-NETBOX-PROXMOX.md` §6 documents this.

**Why it is worth importing.** Today, an upstream sync will fail or
produce ambiguous records when two VMs share a name. The EdgeUno
suffix is ugly but unambiguous, and operators can rename later;
crashing or silently merging is worse.

**Why it has not landed yet.** Upstream prefers the per-VM
`vm_id` custom field as the disambiguator, and that *does* work for
Proxmox→NetBox identification. The remaining gap is the human-facing
`name` field, which still has a unique constraint and still collides.
The EdgeUno suffix idea is the right fallback when two Proxmox
clusters genuinely both have a VM named `web-01`.

**Target landing site in this repo.**

- **Backend.** New helper in
  `proxbox-api/proxbox_api/proxmox_to_netbox/`:
  `resolve_unique_name(cluster, candidate, existing_pk=None)`. On
  collision, append `" (2)"`, `" (3)"`, etc. Idempotent.
- **SSE frame.** New event kind `duplicate_name_resolved` in the
  existing SSE schema, validated by
  `tests/test_sse_schema_mirror.py` and
  `contracts/proxbox_api_sse_schema.json`. The dashboard's live-log
  pane already renders unknown frames; surfacing this as a typed
  frame lets us highlight it as a warning instead.
- **Tests.** Update both the backend SSE schema mirror and the
  plugin's Pydantic mirror at
  `netbox_proxbox/schemas/backend_proxy.py`.

**Migration sketch.**

1. Add the helper on the backend.
2. Add the new SSE frame variant on both sides; the schema mirror
   test is the canary.
3. Surface the warning in the live-log UI's frame renderer.
4. Add a backend unit test pinning the suffix sequence.

**Risks & open questions.** Should the plugin offer to *merge* two
VMs that share a name and the same `vm_id`? No — that would silently
mutate operator data. The suffix path is safer; merges should be
manual.

---

### 4.9 `latest_job` UUID stamp + stale-record cleanup pass

**Priority.** High.

**EdgeUno source.** `proxbox_api_v2/scrapper.py` stamps every upserted
record with the current job UUID (`latest_job`) and, at the end of a
run, deletes any plugin-owned record whose `latest_job` no longer
matches the active run UUID. EdgeUno also documents
this in §13 of its standalone doc as the "raw-SQL stale-record
cleanup" — the implementation uses a raw SQL `DELETE` statement, but
the *idea* (run-stamp + sweep) is sound; only the `eval`-flavoured
implementation is not.

**Why it is worth importing.** Today, when a Proxmox VM is deleted
from Proxmox, the corresponding NetBox VM record is **not** removed
by an upstream sync; it lingers until an operator notices and
manually deletes it. For drift detection to be useful, deletions on
the source side must propagate. The EdgeUno run-stamp pattern is the
cleanest, most auditable way to express this.

**Why it has not landed yet.** Deletion is destructive, and upstream
took the conservative default of "never delete what we did not
create in *this* run". Adding deletion behind an opt-in flag is the
canonical 0.0.15 shape and the right next step.

**Target landing site in this repo.**

- **Backend.** Each upsert path in
  `proxbox-api/proxbox_api/proxmox_to_netbox/` writes a custom field
  `proxbox_last_run_id` on the NetBox object alongside its existing
  custom fields. The custom field is created at startup by the same
  bootstrap that already creates `proxmox_id` /
  `proxmox_keep_interface` (NetBox custom fields are a documented
  EdgeUno-side requirement, so the upstream backend already owns
  this surface).
- **New overwrite flag.** `delete_orphans` on
  `ProxboxPluginSettings` + `ProxmoxEndpoint`, default **off**. When
  on, the backend's last pipeline stage walks every plugin-owned
  object kind (VM, IP address, interface, storage, snapshot, backup,
  routine, replication) and deletes records whose
  `proxbox_last_run_id` ≠ the current run UUID **and** whose Proxmox
  source is the endpoint just synced.
- **Constants.** Add to `OVERWRITE_FIELDS` /
  `OVERWRITE_FIELD_GROUPS` (a new "Cleanup" group, or fold into the
  existing "Overwrite" group).
- **Migration.** Mirror `0039` for both models.
- **Contract.** Update `contracts/overwrite_flags.json` and the
  sibling manifest.
- **SSE frame.** New `orphan_deleted` event kind for the live log,
  with the deleted object's PK and kind. Mirror the schema test.

**Migration sketch.**

1. Land the custom field bootstrap on the backend (no behaviour
   change yet).
2. Stamp `proxbox_last_run_id` on every upsert. Still no behaviour
   change.
3. Add the `delete_orphans` flag (default off) on both models.
4. Implement the sweep stage, gated by the flag, scoped per
   endpoint.
5. Add the `orphan_deleted` SSE frame; mirror the schema test.
6. Document loudly in the next release notes — deletion is a class
   of change we have not shipped before.

**Risks & open questions.** What about NetBox VMs that were created
manually but happen to share a `vm_id` with a deleted Proxmox VM?
The sweep should match on the *full identity tuple* (cluster +
proxbox-managed flag), not just `vm_id`. What about audit history?
NetBox's `ObjectChange` already records deletions; we do not need a
parallel audit trail. What about retry semantics? If a sync fails
mid-stream, the sweep stage **must not** run — only successful runs
should delete records. Pin this in the test suite.

---

### 4.10 `ProxboxSession`-style per-cluster session model in `proxbox-api`

**Priority.** Low.

**EdgeUno source.** `proxbox_api_v2/scrapper.py` and the
`PROXMOX_SESSIONS_LIST` module-global. Each cluster has its own
`ProxboxSession` instance bundling Proxmox client + configuration; the
fan-out is `asyncio.gather` across that list.

**Why it is worth importing.** It is not, as a feature. The current
`proxbox-api` already maintains per-endpoint Proxmox clients via the
session module; the EdgeUno wrapper only adds an ergonomic naming
layer. List this as an *optional* refactor for backend readability,
not a feature import.

**Why it has not landed yet.** Existing code already covers the
behaviour, just under different names.

**Target landing site in this repo.** None until a refactor is
explicitly scheduled. If it is scheduled: a new
`proxbox-api/proxbox_api/session/proxmox_session.py` thin dataclass
collapsing the `(client, endpoint, settings)` triple currently passed
around as separate args.

**Migration sketch.** Out of scope.

**Risks & open questions.** Refactor-only; no behaviour change. If
attempted, the AST contract tests in `proxbox-api/tests/` will fail
loudly on signature drift — that is the canary.

---

## 5. Explicit Non-Imports

These items are present in the EdgeUno fork and **should not** be
ported. Each entry cites the policy that rejects it.

### 5.1 JSON-on-disk credentials (`configuration_options.json`)

EdgeUno reads Proxmox host, user, password, NetBox host, and NetBox
token from a JSON file referenced from
`PLUGINS_CONFIG['netbox_proxbox']['filePath']`. Plaintext at rest. This
is rejected by the **DB-first config policy** in
[`CLAUDE.md`](../CLAUDE.md): runtime tunables belong in
`ProxboxPluginSettings` (migration `0037`); credentials belong in the
backend's Fernet store keyed by `PROXBOX_ENCRYPTION_KEY`. Inventing
parallel JSON/YAML files to dodge the migration cost is explicitly
prohibited.

### 5.2 `ssl_verify=False` hardcoded on the NetBox client

EdgeUno's v1 sync passes `ssl_verify=False` to `pynetbox.api(...)`
unconditionally. The 0.0.15 release decoupled `Use HTTPS` from
`Verify SSL` precisely because this overload is dangerous; see
[`docs/release-notes/version-0.0.15.md`](../docs/release-notes/version-0.0.15.md)
§ "#352 — `Use HTTPS` toggle decoupled from `Verify SSL`". Hardcoding
verification off would re-introduce silent MITM exposure on every
install.

### 5.3 `print()`-based logging

EdgeUno emits operational output via `print()` calls scattered through
the `Scrapper`. This clashes with the structured-log + SSE-frame
contract: every operator-visible line in this repo flows through a
typed SSE frame validated by `tests/test_sse_schema_mirror.py` against
`contracts/proxbox_api_sse_schema.json`, and every backend log line
flows through Python's `logging` module. `print()` would bypass both
and silently break the live-log dashboard pane.

### 5.4 `eval()` in templatetags

EdgeUno has `eval()` in at least one templatetag. The plugin's
`netbox_proxbox/templatetags/CLAUDE.md` exists specifically to forbid
this — it is a security hazard, an unbounded RCE primitive, and there
is no scenario under which `eval()` of operator-controlled or
template-context data is acceptable.

### 5.5 `ChangeLoggedModel` instead of `NetBoxModel`

EdgeUno's `ProxmoxVM` and `SyncTask` both extend `ChangeLoggedModel`,
not `NetBoxModel`. The framework stack preference in
[`CLAUDE.md`](../CLAUDE.md) requires using NetBox plugin layer
primitives first. `NetBoxModel` brings tags, custom fields, custom
links, journal entries, and `restrict()` querysets — all of which the
plugin's permission story (`ObjectPermissionRequiredMixin`) depends on.

### 5.6 Web-triggered synchronous sync (held gunicorn worker)

EdgeUno's v1 `ProxmoxFullUpdate` view runs the entire sync in the
request/response cycle. A long sync holds a gunicorn worker for the
duration, blocks any cancel attempt, and fails ungracefully on the
first reverse-proxy timeout. Upstream's contract is RQ + SSE: the
view enqueues a `ProxboxSyncJob` on the `default` queue with
`job_timeout=PROXBOX_SYNC_JOB_TIMEOUT` (7200s), and the SSE stream's
between-chunk read timeout (3600s) lives inside `run_sync_stream`.
That is the only sustainable shape for sync work and it is documented
in [`CLAUDE.md`](../CLAUDE.md) under "Backend integration notes".

### 5.7 Hardcoded example NetBox token in shipped config

EdgeUno's `configuration_options.json` ships with a hardcoded example
NetBox API token. Operators who do not change it get a working but
shared-secret install. The standalone EdgeUno doc lists this as a
documented quirk; we treat it as a security defect that should never
exist in any artefact this repo ships.

### 5.8 `nb_cluster_type.DoesNotExist` swallow-and-continue

EdgeUno has a `try / except DoesNotExist: pass` around its cluster-
type lookup. The sync continues with a partially-broken state. This
clashes with the operator-actionable error path the 0.0.15 release
introduced via `services/_endpoint_errors.py`, which translates known
failure modes into specific, user-visible messages on the FastAPI
endpoint detail page. The right pattern is "fail loud, with a clear
message" — never "silently degrade and hope".

### 5.9 Duplicate sync engines (v1 + v2 coexisting)

EdgeUno ships both `proxbox_api/` (the original v1 sync, still
reachable via the `ProxmoxFullUpdate` view) and `proxbox_api_v2/`
(the async pipeline used by `proxboxscrapper`). Two code paths for the
same job is engineering debt; this repo has one backend
(`proxbox-api`) deliberately.

### 5.10 Version mismatch between `setup.py` / `pyproject.toml` and `PluginConfig.version`

EdgeUno's git tag is `0.1.0`, `setup.py` says `0.1.0`, but
`PluginConfig.version` self-reports `0.0.5`. This repo's CI verifies
the three are aligned (see the `tests/test_version.py` source-contract
test); the mismatch would fail pre-commit immediately.

---

## 6. Implementation Sequencing

Recommended order, with rationale:

1. **§4.4 management command first.** Zero schema risk, useful
   immediately, unblocks §4.5 (scheduler container) and §4.6 (one-shot
   compose). One PR, one new file under
   `netbox_proxbox/management/commands/`, one AST contract test.
2. **§4.9 `proxbox_last_run_id` next.** Foundational for any future
   "sync produces deletions" feature. Ship the *stamping* first,
   default off; ship the *sweep* in a follow-up PR; ship the
   `delete_orphans` UI flag in a third PR. Three small, reversible
   PRs are safer than one large one because deletion is destructive.
3. **§4.1 + §4.2 + §4.3 in one batch.** They share the
   overwrite-flag-plus-migration pattern, the same `_build_base_query_params`
   plumbing change, and the same surface update across form /
   serializer / table. Shipping them together lets the
   `tests/test_overwrite_flags_contract.py` drift detector catch any
   manifest mistakes once instead of three times. Pair this with one
   release-notes file modelled on `version-0.0.15.md`.
4. **§4.5 + §4.6 once §4.4 has shipped.** Both depend on the
   management command existing. §4.5 is a new container image; §4.6 is
   a documentation-only compose file. Land §4.6 first (no CI cost),
   then §4.5.
5. **§4.7, §4.8, §4.10 last.** Ergonomics, an SSE frame addition, and
   an optional refactor — all independently shippable, none blocking
   anything else.

This sequencing keeps every PR small, every schema change additive,
and every behaviour change either default-off or behaviour-preserving
on existing installs. The 0.0.15 release notes are the canonical
template for what a "new opt-in flag" PR description should look like.

---

## 7. Cross-References

- [`EDGEUNO-NETBOX-PROXMOX.md`](./EDGEUNO-NETBOX-PROXMOX.md) — standalone
  deep-dive on the EdgeUno fork; canonical source for all "the fork
  does X" claims in §4.
- [`PROXBOX-FORK-EDGEUNO.md`](./PROXBOX-FORK-EDGEUNO.md) — side-by-side
  comparison; canonical source for "this repo does Y, the fork does X"
  claims and for the verb-coverage matrix referenced in §3.1.
- [`../CLAUDE.md`](../CLAUDE.md) — policy authority cited throughout
  §3 (criteria) and §5 (non-imports).
- [`../docs/release-notes/version-0.0.15.md`](../docs/release-notes/version-0.0.15.md)
  — reference template for "new opt-in overwrite flag + migration +
  form / serializer / table surface +
  `_build_base_query_params` query-string forwarding + backend handler".
  Every High-priority §4 entry follows this shape.
- `../netbox_proxbox/constants.py:5,64` — `OVERWRITE_FIELD_GROUPS` and
  `OVERWRITE_FIELDS`, the canonical 23-flag set every new flag must
  extend.
- `../contracts/overwrite_flags.json` — manifest mirrored against the
  sibling in `proxbox-api/contracts/overwrite_flags.json`; pinned by
  `../tests/test_overwrite_flags_contract.py`.
- `../contracts/proxbox_api_sse_schema.json` — SSE frame schema
  referenced by §4.8 and §4.9; pinned by
  `../tests/test_sse_schema_mirror.py`.
- `../netbox_proxbox/migrations/0037_pluginsettings_runtime_tunables.py`,
  `../netbox_proxbox/migrations/0038_fastapiendpoint_use_https.py`,
  `../netbox_proxbox/migrations/0039_pluginsettings_overwrite_ip_address_dns_name.py`
  — three canonical "production-safe additive schema change" migrations
  every §4 migration sketch references.
- `../netbox_proxbox/management/commands/proxbox_fix_tokens.py` — shape
  reference for the new `proxbox_sync` command in §4.4.
- `../proxbox_cli/__init__.py` — Typer app entry point referenced by
  §4.7.
- `/root/nms/edgeuno/netbox-proxbox/proxbox_api_v2/scrapper.py` —
  EdgeUno source for §4.1, §4.2, §4.3, §4.8, §4.9, §4.10.
- `/root/nms/edgeuno/netbox-proxbox/scanner_scheduler.py` — EdgeUno
  source for §4.5.
- `/root/nms/edgeuno/netbox-proxbox/docker-compose-single-exec.yml` —
  EdgeUno source for §4.6.
- `/root/nms/edgeuno/netbox-proxbox/proxbox_runner.sh` — EdgeUno
  source for §4.7.
