# `netbox-proxmox-automation` — Patterns Valid to Implement Upstream

This document is an **action list**. It distils
[`NETBOX-PROXMOX-AUTOMATION.md`](./NETBOX-PROXMOX-AUTOMATION.md) (the
standalone deep-dive on the NetBox Labs project at
`/root/nms/netbox-proxmox-automation`) and
[`PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md)
(the side-by-side comparison of `netbox-proxbox 0.0.15` + `proxbox-api
0.0.11` against that project) into a single inventory of patterns and
capabilities from `netbox-proxmox-automation` that are worth porting and
are not yet present.

Read those two documents first if you need the *why* behind any cell in
this one. This file does not re-explain either project; it answers the
narrower question **"what should we steal from `netbox-proxmox-automation`,
where does it land, and in what order?"**.

It is the sibling of
[`EDGEUNO-FORK-VALID-TO-IMPLEMENT.md`](./EDGEUNO-FORK-VALID-TO-IMPLEMENT.md),
which performs the same exercise for the EdgeUno fork. The two action
lists share the per-entry template. They diverge sharply in framing:
the EdgeUno fork is a downstream of *this* repo and most of its
imports are extra observer features; `netbox-proxmox-automation` is
the architectural opposite of this repo, and most of its *features*
cannot be ported without inverting the architecture. Section 1 is
where that asymmetry is set out — read it before §4.

---

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [TL;DR](#2-tldr)
3. [Methodology](#3-methodology)
4. [Recommended Imports](#4-recommended-imports)
   - 4.1 [Drift-detecting writes (the `createOrUpdate` pattern)](#41-drift-detecting-writes-the-createorupdate-pattern)
   - 4.2 [Optional NetBox Branching plugin support (`X-NetBox-Branch`)](#42-optional-netbox-branching-plugin-support-x-netbox-branch)
   - 4.3 [Hardware discovery via SSH + `dmidecode` + `ethtool`](#43-hardware-discovery-via-ssh--dmidecode--ethtool)
   - 4.4 [`dcim.mac_addresses` object linkage with `primary_mac_address`](#44-dcimmac_addresses-object-linkage-with-primary_mac_address)
   - 4.5 [NetBox-side bootstrap of cluster type / device role / device type / platform / choice sets](#45-netbox-side-bootstrap-of-supporting-objects)
   - 4.6 [Cloud-init read-side reflection (`ipconfig0`, `sshkeys`, `ostype`)](#46-cloud-init-read-side-reflection)
   - 4.7 [Strictly opt-in operational verbs as REST endpoints in `proxbox-api`](#47-strictly-opt-in-operational-verbs-as-rest-endpoints-in-proxbox-api)
   - 4.8 [Discovery-tag pattern (`proxmox-vm-discovered` / `proxmox-lxc-discovered`)](#48-discovery-tag-pattern)
   - 4.9 [IPv6 link-local skip + zone-ID stripping in IP sync](#49-ipv6-link-local-skip--zone-id-stripping-in-ip-sync)
5. [Explicit Non-Imports](#5-explicit-non-imports)
6. [Implementation Sequencing](#6-implementation-sequencing)
7. [Cross-References](#7-cross-references)

---

## 1. Purpose & Scope

`netbox-proxbox 0.0.15` and `proxbox-api 0.0.11` were certified
together on 2026-05-07. They are a two-service stack: a NetBox plugin
observes Proxmox state, and a separate FastAPI backend executes the
actual Proxmox-to-NetBox transformation, streaming results back over
SSE. The plugin's stance is **observer**: Proxmox is the source of
truth for everything Proxmox owns (clusters, nodes, VMs, storage,
backups, snapshots, replications), and NetBox mirrors that truth.

`netbox-proxmox-automation` at `/root/nms/netbox-proxmox-automation` is
the **architectural opposite**. NetBox is the source of truth: an
operator authors the desired VM in NetBox (custom fields for
`proxmox_node`, `proxmox_disk_storage_volume`, `proxmox_public_ssh_key`,
etc.), NetBox emits webhook events on save, an event-rule listener
catches the event, and either an AWX/Tower/AAP job template or a Flask
shim reaches into Proxmox to **create / clone / start / stop /
snapshot / migrate** the VM to match. The system ships **17 pre-defined
event rules** and a matching **17 webhook targets** for that fan-out.
The model is *desired-state authoring with NetBox→Proxmox dispatch*.

That structural difference is why most of the upstream's load-bearing
features **cannot** be lifted as-is. Anything that depends on NetBox
being authoritative for `proxmox_node` / `proxmox_vm_state` / cloud-init
spec, anything routed through `extras.event_rules` + webhooks, anything
that requires AWX / Tower / AAP as the execution medium, and anything
that synchronously holds an HTTP worker waiting on a Proxmox API call
has no analog in this repo and would invert the observer stance if
forced in. §20 of [`NETBOX-PROXMOX-AUTOMATION.md`](./NETBOX-PROXMOX-AUTOMATION.md)
and §7.5 / §10 of [`PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md)
already pre-chew that boundary.

But several **patterns and idioms** the upstream uses are
architecture-agnostic and slot cleanly into the existing observer
pipeline:

- Drift-detecting writes (`createOrUpdate`) reduce no-op `ObjectChange`
  spam regardless of who owns the source-of-truth direction.
- Optional `X-NetBox-Branch` support layers neatly on the existing
  `netbox-sdk` session.
- `dcim.mac_addresses` linkage with `primary_mac_address` is required
  for NetBox 4.5+ correctness, which both projects target.
- Idempotent bootstrap of cluster type / device role / device type /
  platform / choice sets makes a clean install work without operator
  NetBox prep.
- Discovery scripts that handle IPv6 link-local + zone IDs already
  contain hardening this repo can lift defensively.

And one **strictly opt-in new direction** is worth carving out:
exposing operational verbs (start / stop / snapshot / migrate) as REST
endpoints inside `proxbox-api`, paired with NetBox-side per-VM action
buttons via the existing `template_extensions`. This is **not** the
same as importing upstream's event-rule + webhook architecture — it is
a flag-gated REST surface. Section 4.7 spells the constraints out and
§5.7 / §5.8 spell out what is explicitly *not* being imported.

This document does not propose a release; it does not write code; it
does not assign owners. Treat it as the input to a roadmap planning
session, paired with [`docs/roadmap.md`](../docs/roadmap.md).

---

## 2. TL;DR

Nine import candidates, three priority tiers:

| Tier | Item | Lands |
|------|------|-------|
| High | 4.1 Drift-detecting writes (`createOrUpdate`) | New helper in `proxbox-api/proxbox_api/services/netbox_writers.py` |
| Medium | 4.2 Optional NetBox Branching support | New `enable_netbox_branching` setting + `X-NetBox-Branch` header |
| Medium | 4.3 Hardware discovery via SSH + `dmidecode` + `ethtool` | New opt-in pipeline stage + per-endpoint SSH credentials |
| Medium | 4.4 `dcim.mac_addresses` linkage | Backend interface reconciler |
| Medium | 4.5 NetBox-side bootstrap of supporting objects | Backend bootstrap pass behind `ensure_netbox_objects` |
| Medium | 4.6 Cloud-init read-side reflection | Three new read-only custom fields + VM sync write |
| Medium-Low | 4.7 Strictly opt-in operational verbs | Per-endpoint `allow_writes` + REST endpoints in `proxbox-api` |
| Low | 4.8 Discovery-tag pattern | One-line tag write at object creation |
| Low | 4.9 IPv6 link-local skip + zone-ID strip | Defensive guard in IP reconciler |

Eleven explicit *non*-imports rooted in
[`CLAUDE.md`](../CLAUDE.md) policy and the existing wire contracts:
no-queue synchronous webhook execution, file-based YAML config,
`verify_ssl=False` hardcoding, MB÷1000 vs ÷1024 unit drift, plaintext
credentials anywhere on disk, "no test suite at all", AWX / Tower / AAP
dependency for any operational verb, the 17-event-rule + 17-webhook
setup-time explosion, CalVer versioning, BIND9 / gss-tsig DNS update
path, and the cosmetic `Proxmox (common)` / `Proxmox VM` / `Proxmox
LXC` custom-field group renaming. See §5 for the justification for
each.

---

## 3. Methodology

### 3.1 Inclusion criteria

A pattern or capability qualifies as a recommended import if and only
if all four hold:

1. **It is present in `netbox-proxmox-automation`.** Either as runtime
   behaviour (an idiom in `helpers/netbox_objects.py`,
   `helpers/netbox_branches.py`, `setup/netbox-discover-*.py`), or as a
   capability (cloud-init reflection, hardware discovery, branching
   support).
2. **It is absent in `netbox-proxbox 0.0.15` + `proxbox-api 0.0.11`.**
   Confirmed via the §6 feature-comparison matrix and §7 code-pattern
   comparison in [`PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md).
3. **It is compatible with the two-service + observer architecture.**
   Plugin-side work can read `ProxboxPluginSettings` and call the
   backend over HTTP/SSE; backend-side work runs inside `proxbox-api`
   and may stream SSE frames. Anything that reverses the source-of-
   truth direction by default (NetBox→Proxmox writes triggered from a
   NetBox `ObjectChange` save) is rejected.
4. **It does not conflict with [`CLAUDE.md`](../CLAUDE.md) policy.**
   The pre-commit checklist (`compileall`, `rtk ruff check`, `rtk
   pytest`, `rtk ty check`), the framework stack preference (NetBox
   plugin → NetBox core → Django → 3rd-party), the DB-first config
   policy citing migration `0037_pluginsettings_runtime_tunables.py`,
   and the security model around `ObjectPermissionRequiredMixin` /
   `ConditionalLoginRequiredMixin` /
   `ContentTypePermissionRequiredMixin` are all binding.

### 3.2 Exclusion criteria

A pattern or capability is rejected, regardless of operator value, if
porting it would require any of the following:

- **Inverting the observer stance by default.** Making NetBox the
  source of truth for any field Proxmox already owns, or routing
  writes through NetBox `extras.event_rules` + webhooks back into
  Proxmox, is out of scope. This repo's compatibility story (§10 of
  [`PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md))
  is "the two systems can coexist", not "merge them".
- **Synchronous web-triggered Proxmox work.** Holding a Flask /
  gunicorn / Django worker while a Proxmox API call resolves is the
  exact anti-pattern the existing RQ + SSE pipeline replaced. Long
  work belongs on the `default` queue with
  `job_timeout=PROXBOX_SYNC_JOB_TIMEOUT` (7200s) and the SSE
  between-chunk read timeout (3600s) inside `run_sync_stream`.
- **Demoting credential storage.** The backend Fernet store keyed by
  `PROXBOX_ENCRYPTION_KEY` is the only place plaintext credentials
  exist for any meaningful interval. No JSON / YAML / `.env` workaround
  for capabilities that need credentials.
- **Re-introducing file-based YAML config.** Runtime tunables go in
  `ProxboxPluginSettings`. Bootstrap data (cluster types, roles,
  platforms) goes in code, not in `conf.d/netbox_setup_objects.yml`.
  See [`CLAUDE.md`](../CLAUDE.md) "Plugin settings and configuration".
- **Operational-verb work outside the carve-out in §4.7.** Start /
  stop / snapshot / migrate may exist as REST endpoints in
  `proxbox-api`, default-off per endpoint, behind a new permission.
  They may **not** be triggered by NetBox event rules + webhooks. The
  verbs are valid; the dispatch shape is not.

### 3.3 Mapping

Every entry in §4 specifies a concrete destination — file paths in
`/root/nms/netbox-proxbox/` (plugin) and/or `/root/nms/proxbox-api/`
(backend), which side of the two-service boundary each piece sits on,
and which existing pattern it should imitate (an existing model,
migration, overwrite flag, view, or service, cited by path and line).

The canonical reference pattern is the `0.0.15` release that
introduced `overwrite_ip_address_dns_name`, `use_https`, the
`_endpoint_errors` helper, and migrations `0038` / `0039`. See
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

Each entry below uses the same seven-field template (priority,
upstream source, why import, why not yet, target landing site,
migration sketch, risks). Read vertically within an entry; read
horizontally across entries to compare priority and scope. All
upstream paths are rooted at `/root/nms/netbox-proxmox-automation/`
unless qualified otherwise. All this-repo paths are rooted at
`/root/nms/netbox-proxbox/` (plugin) or `/root/nms/proxbox-api/`
(backend).

---

### 4.1 Drift-detecting writes (the `createOrUpdate` pattern)

**Priority.** High.

**Upstream source.** `helpers/netbox_objects.py` —
`NetBox.createOrUpdate(obj_kind, declared_fields, **lookup)`. The
upstream helper does the lookup, diffs **each declared field** against
the current value on the existing record, PATCHes only when at least
one field differs, and creates only when the lookup misses. The same
shape recurs across every upstream write site (clusters, devices,
interfaces, IP addresses, custom-field values). See §7.1 of
[`PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md)
for the side-by-side diff.

**Why it is worth importing.** This repo's backend currently goes
through `netbox-sdk`'s typed client; the typed client by itself does
not enforce "PATCH only when changed". The result is that every full
sync emits an `ObjectChange` row per touched object — even when the
sync is a perfect no-op against a cluster that has not moved. On a
1000-VM cluster this turns the NetBox change-log dashboard into noise,
makes diffs across runs unreadable, and increases write volume against
the NetBox database needlessly. A "diff each declared field, PATCH
only on real diff" wrapper is the canonical fix; it is also
defensively correct for cases where NetBox would otherwise reject a
no-op PATCH due to a validator side effect.

**Why it has not landed yet.** The backend was built around
`netbox-sdk`'s typed client and its existing async write helpers. The
absence of an explicit drift-detect wrapper has not been a correctness
bug, only a noise problem; under the original "ship the observer
loop" budget, fixing noise was lower priority than fixing missing
features. With those features now in (snapshots, replications,
backups, dns_name, HA), tightening the write surface is the next
sensible investment.

**Target landing site in this repo.**

- **Backend.** New typed helper in
  `proxbox-api/proxbox_api/services/netbox_writers.py`. Single entry
  point per object kind: `upsert_vm(...)`, `upsert_interface(...)`,
  `upsert_ip_address(...)`, `upsert_cluster(...)`, etc. Each helper
  takes the lookup tuple, the declared payload, and the `netbox-sdk`
  client; performs the GET; diffs; emits a PATCH only on a real diff;
  returns the resulting record plus a `created | updated | unchanged`
  status enum.
- **Reconciler call sites.** Replace direct
  `client.<app>.<model>.create / update / delete` call sites in
  `proxbox-api/proxbox_api/proxmox_to_netbox/` with the new helpers.
- **SSE counters.** Extend the run summary frame to count `unchanged`
  alongside `created` / `updated`, so operators can see "this run
  changed nothing" at a glance.
- **No plugin-side work.** This is purely backend; no migration, no
  flag, no settings change.

**Migration sketch.**

1. Land `netbox_writers.py` with helpers and a comprehensive unit-
   test suite that pins the diff semantics (including how `None` /
   `""` / unset are treated and how M2M / FK fields are compared).
2. Migrate one reconciler — start with the cluster reconciler, the
   smallest one — to use the helper. Verify zero-noise behaviour by
   running two consecutive full syncs against an unchanged cluster
   and confirming the second emits no `ObjectChange` rows.
3. Migrate the remaining reconcilers one at a time. Each migration
   is one PR; each PR is reviewable independently; each PR ships with
   its own "second-run-is-silent" assertion.
4. Update the SSE summary schema (`contracts/proxbox_api_sse_schema.json`
   plus the mirror at `netbox_proxbox/schemas/backend_proxy.py`) to
   include the `unchanged` counter; the schema-mirror test
   `tests/test_sse_schema_mirror.py` will fail otherwise.
5. Document in the release notes as a quality-of-life change with a
   measurable result: "second consecutive sync against unchanged
   cluster emits 0 NetBox ObjectChange rows".

**Risks & open questions.** What about server-side validators that
mutate the value before persisting (e.g. NetBox normalising IPv6 to
canonical form)? The diff must compare against the *post-validation*
form NetBox stores, not the pre-validation form the helper sent.
Solution: do a fresh GET after the PATCH and feed that back as the
truth on the next call. What about FK fields where the helper sees an
ID but NetBox returns a nested record? Pin the comparison to
`record.id` / record `.pk`; never compare nested dicts. Custom-field
diff has the same shape — compare key-by-key, not whole-dict.

---

### 4.2 Optional NetBox Branching plugin support (`X-NetBox-Branch`)

**Priority.** Medium.

**Upstream source.** `helpers/netbox_branches.py` —
`NetBoxBranches(...)`. The upstream helper installs the
`X-NetBox-Branch: <branch>` header on the `pynetbox` session for the
duration of the run. Combined with the
[NetBox Branching plugin](https://github.com/netboxlabs/netbox-branching)
on the NetBox side, every read and write during the run targets the
named branch instead of `main`. Operators can sanity-check large
imports on a branch, diff against `main`, and merge or discard.

**Why it is worth importing.** The two scenarios where branching
matters most are exactly the two scenarios where this plugin produces
the most churn: the **first full sync** of a populated Proxmox cluster
into a clean NetBox install (often hundreds or thousands of new
records on the first pass), and a **migration sync** after an operator
has hand-edited values on existing records (where one wants to inspect
the diff before letting it land). Both are dry-run-shaped requirements
that NetBox's branching plugin already exists to serve; not having a
hook is the only thing keeping this repo from offering the workflow.

**Why it has not landed yet.** NetBox Branching is a separate plugin
that not every operator runs. Adding it as a hard dependency would
break installs that do not have it. The right shape is a runtime
toggle: detect whether the plugin is present, expose a
`branch_name` parameter on the sync trigger when it is, install the
header on the backend's `netbox-sdk` session for the run, and remove
it on completion. Conditional support is more work than blind
support, which is why it has not landed yet.

**Target landing site in this repo.**

- **Plugin model.** New boolean field
  `ProxboxPluginSettings.enable_netbox_branching`, default `False`.
  File: `netbox_proxbox/models/plugin_settings.py`. Migration follows
  `0037_pluginsettings_runtime_tunables.py` shape with `IF NOT
  EXISTS`.
- **Plugin form.** Add the toggle to the Settings tab. When `False`,
  the rest of the branching UI stays hidden.
- **Plugin sync trigger.** When the toggle is on, surface a
  `branch_name` text input on the sync-now form (and on the
  scheduling form). Free text; default empty (= use `main`).
- **Plugin query-string forwarding.** New optional key in
  `netbox_proxbox/sync_params.py::_build_base_query_params`. Only
  emitted when both the toggle is on **and** the operator filled in
  `branch_name`.
- **Backend.** Accept the parameter in the per-run context. Install
  `X-NetBox-Branch: <name>` on the `netbox-sdk` HTTP session for the
  full run. Remove it on completion (success, failure, or cancel —
  cleanup must be in `finally`). Cite §7.3 of
  [`PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md)
  for header-injection comparison against AWX's runtime credentials
  pattern.
- **Detection.** At backend startup, attempt a single
  `GET /api/plugins/branching/branches/?limit=1` to verify the plugin
  is installed. Cache the result for the lifetime of the process.
  When absent, the toggle is honoured-but-ignored on the backend with
  a clear SSE warning frame; the plugin-side toggle stays available
  in case the operator installs the branching plugin later.

**Migration sketch.**

1. Add the `enable_netbox_branching` field; one migration, one form
   change, one serializer change.
2. Surface the `branch_name` field on the sync-now / schedule forms
   conditionally on the toggle.
3. Forward the `branch_name` query-string key when both are set.
4. Backend: install/clear the header in the per-run context; emit a
   warning SSE frame if the branching plugin is absent.
5. Test: AST source-contract test pinning the field name, the
   query-string key, and the backend's header-installation site.

**Risks & open questions.** What happens if the operator names a
non-existent branch? NetBox Branching will reject the request; the
sync will fail loudly on the first call. Acceptable — better than
silently writing to `main`. What happens mid-run if the branch is
deleted? Same — loud failure on the next call. What about
`netbox-sdk` cache interaction with branching headers? The cache key
must include the branch name, otherwise two runs against different
branches could return cached data from the wrong branch; pin this
explicitly in the test suite.

---

### 4.3 Hardware discovery via SSH + `dmidecode` + `ethtool`

**Priority.** Medium.

**Upstream source.** `setup/netbox-discover-proxmox-cluster-and-nodes.py`.
The upstream discovery script SSHes into each Proxmox node and runs
`dmidecode -t system` (manufacturer / product name / serial number)
and `ethtool <iface>` (link speed) per node. Results land on the
NetBox `dcim.Device` record (manufacturer + serial) and on the
`dcim.Interface` records (link speed). See §13 of
[`NETBOX-PROXMOX-AUTOMATION.md`](./NETBOX-PROXMOX-AUTOMATION.md) for
the full discovery flow.

**Why it is worth importing.** Today the plugin's `ProxmoxNode` model
carries only Proxmox-API-derived fields (CPU model, memory total, root
filesystem, status). What it does not carry — and what
`dcim.Device.serial`, `dcim.Manufacturer`, and per-interface link
speed are *for* — is hardware identity. Operators who use NetBox for
hardware tracking (warranty, RMA, audit, racking) currently maintain
that data by hand. Bridging the gap is exactly what the upstream
script is for.

**Why it has not landed yet.** SSH adds a third credential surface
(per-node SSH user / key) on top of the existing Proxmox API token
and NetBox API token. Credential surface area is a security cost; the
default-off design below contains that cost. It also adds
`paramiko` (or equivalent SSH library) to the backend dependency set,
which has historically been a hard sell for any plugin (per the
framework stack preference in [`CLAUDE.md`](../CLAUDE.md)).

**Target landing site in this repo.**

- **New per-endpoint credential.** `ProxmoxEndpoint.ssh_username`,
  `ProxmoxEndpoint.ssh_private_key` (encrypted, Fernet, same
  pattern as the existing API token). Optional. Blank → no SSH-based
  discovery for this endpoint.
- **Migration.** New file mirroring `0039`. Two columns; encrypted
  field is stored as text; the encryption is handled by
  `proxbox-api`'s existing `crypto_fields` helper.
- **Plugin form / serializer / table.** Surface the SSH username
  field; the private key is write-only via a separate "rotate SSH
  key" form (mirror the API-token rotation pattern).
- **New overwrite flag.** `discover_node_hardware` on
  `ProxboxPluginSettings` + `ProxmoxEndpoint` (tri-state per-endpoint
  override). Default **off**. Add to `OVERWRITE_FIELDS` and the
  appropriate group (a new "Discovery" group, or fold into
  "Overwrite").
- **Backend pipeline stage.** New SSE pipeline stage
  `node_hardware_discovery`, between `node_sync` and
  `storage_sync`. Skipped when the flag is off. Streams
  `node_hardware_started`, `node_hardware_progress`, and
  `node_hardware_done` SSE frames; mirror in the schema.
- **Backend dependency.** Add `paramiko` (or `asyncssh`) as an
  *optional* extra in `proxbox-api/pyproject.toml`. The flag-gated
  pipeline stage imports it lazily; without the extra installed, the
  stage refuses to run with a clear SSE error frame.

**Migration sketch.**

1. Add the encrypted SSH credential fields and migration; surface in
   form / serializer / table.
2. Add the `discover_node_hardware` flag in the constants + manifests
   + sibling manifest; let the drift detector fail; commit the fix.
3. Implement the pipeline stage; cover with mock-SSH unit tests
   (paramiko's loopback testing pattern, or a fake `asyncssh` server).
4. Stream SSE frames; mirror schema.
5. Document in release notes with a loud security note: enabling
   this flag widens the credential surface and requires per-endpoint
   SSH access.

**Risks & open questions.** What about Proxmox clusters where the
API user has a different identity than any SSH account? Solved — SSH
credentials are stored separately. What about clusters that disable
SSH entirely? The flag stays off; no harm done. What about Proxmox
versions where `dmidecode` is not installed by default? Catch the
"command not found" exit code per node; emit a `node_hardware_skipped`
SSE frame with the reason; do not fail the run. What about non-x86
Proxmox installs where `dmidecode` is absent (ARM)? Same skip logic.

---

### 4.4 `dcim.mac_addresses` object linkage with `primary_mac_address`

**Priority.** Medium.

**Upstream source.** `setup/netbox-discover-proxmox-vms.py` and the
related discovery scripts. NetBox 4.5+ models MAC addresses as
standalone objects on `dcim.mac_addresses`, linked from interfaces
via `primary_mac_address` (FK). Upstream's discovery scripts already
write through that object model: a discovered MAC becomes a
`dcim.MACAddress` row, and the interface's `primary_mac_address` FK
points at it.

**Why it is worth importing.** The legacy "MAC as a string field on
the interface" path is on a deprecation track in NetBox 4.x. NetBox
4.6 emits warnings when a plugin writes through it, and some 4.6
behaviours (e.g. MAC search) only work against the new object model.
This repo's `min_version` is `4.5.8` and `max_version` is `4.6.99`
([`netbox_proxbox/__init__.py:124-125`](../netbox_proxbox/__init__.py)),
so the plugin must support the new model — at minimum on writes — to
remain certified through the 4.6 window.

**Why it has not landed yet.** The migration may already be
done — this needs a spot-check of the existing reconciler in
`proxbox-api/proxbox_api/proxmox_to_netbox/` (interfaces / IPs). If
the spot-check shows the legacy string field is still in use, then
this entry applies; if the new object model is already in use, then
this entry collapses to a verification-only test entry.

**Target landing site in this repo.**

- **Backend reconciler.** The relevant interface and IP reconciler
  files in `proxbox-api/proxbox_api/proxmox_to_netbox/`. After spot-
  check: either port to the object model and link via
  `primary_mac_address`, or add an AST contract test that pins the
  current code at the new object model so any regression fails CI.
- **No plugin-side schema change.** This is purely a write-path fix
  on the backend.
- **No new flag.** Correctness change, not a feature.

**Migration sketch.**

1. Spot-check the relevant reconciler. Read the file end-to-end and
   document which model is in use. Cite the result in the PR
   description.
2. If legacy: rewrite the MAC write path to upsert a
   `dcim.MACAddress` row first, then PATCH the interface's
   `primary_mac_address` FK. Reuse the §4.1 drift-detect helper if it
   has shipped by then.
3. If modern: add an AST source-contract test pinning the code at
   the new model, so a regression cannot land silently.
4. Test against a NetBox 4.5.x and 4.6.0 fixture pair (the existing
   compatibility matrix already covers this).
5. Document in release notes only if a code change was required.

**Risks & open questions.** What about NetBox installs that have
manually populated the legacy string field with values not in
`dcim.mac_addresses`? The first sync after the change will create
`dcim.MACAddress` rows for those values, then link them. Migration
loud-fails only on duplicate-MAC-address conflicts (NetBox enforces
uniqueness on the new model). Acceptable. What about VMs in
Proxmox that have multiple MACs per interface? Proxmox's per-interface
schema only carries one; no migration risk.

---

### 4.5 NetBox-side bootstrap of supporting objects

**Priority.** Medium.

**Upstream source.** `setup/netbox_setup_objects_and_custom_fields.py`
plus `conf.d/netbox_setup_objects.yml`. The upstream bootstrap script
ensures that the supporting NetBox rows exist before the first sync:
`dcim.cluster_types` (a row named "Proxmox VE"),
`dcim.device_roles` (e.g. "Hypervisor"),
`dcim.device_types`, `dcim.platforms`,
`extras.custom_field_choice_sets`, and the tags
`proxmox-vm-discovered` / `proxmox-lxc-discovered` (see §4.8). The
script is **idempotent**: existing rows are reused, missing rows are
created, and rows with drifted fields are corrected.

**Why it is worth importing.** Today, on a fresh NetBox install, the
plugin requires the operator to pre-create at least the Proxmox cluster
type and device role before the first sync, or the sync fails. That is
a documentation burden and a foot-gun. Upstream's bootstrap pass
removes the burden entirely: the first sync just works.

**Why it has not landed yet.** The bootstrap responsibility was kept
on the operator side originally to avoid coupling the plugin to
NetBox's data model in ways that would break across NetBox versions.
With the §4.1 drift-detect helper in place, the bootstrap pass can
reuse the same idempotent semantics — find by name, diff each declared
field, PATCH only on diff, create only on miss — and the brittleness
goes away.

**Target landing site in this repo.**

- **Backend bootstrap pass.** New module
  `proxbox-api/proxbox_api/services/netbox_bootstrap.py`. Runs once
  per process startup, before the first sync, behind a new flag.
- **New plugin setting.** `ProxboxPluginSettings.ensure_netbox_objects`,
  default **on** (the bootstrap is purely additive). Field follows
  the `0037` shape; new migration with `IF NOT EXISTS`.
- **Bootstrap inventory.** Hard-coded in code, not in YAML. The
  inventory is small enough (cluster types, two roles, the discovered
  tags from §4.8, custom-field choice sets for §4.6) that file-based
  config is unnecessary.
- **Reuse §4.1.** Each bootstrap object goes through the
  `createOrUpdate`-shaped helper from §4.1. If §4.1 has not shipped
  yet, sequence §4.5 after it (see §6).
- **No plugin-side schema change beyond the flag.**

**Migration sketch.**

1. Add the `ensure_netbox_objects` flag with the canonical shape
   (model + migration + form + serializer + table + manifest entry).
2. Land `netbox_bootstrap.py` with the inventory and unit tests.
3. Wire the bootstrap into `proxbox-api`'s startup path; gate it on
   the flag.
4. Stream a single `bootstrap_done` SSE frame at the start of any
   run that has just bootstrapped (or that has skipped because the
   inventory was already complete). Mirror the schema.
5. Document in release notes: "fresh installs no longer require
   manual NetBox setup before the first sync".

**Risks & open questions.** What about operators who have hand-edited
the cluster type's `slug` or `description`? The drift-detect helper
will not overwrite custom values unless explicitly told to (the diff
matches *declared* fields, not the full record). Default-on is safe
because the declared payload is the minimum to make the plugin work.
What about NetBox versions that change the supporting models'
required fields between minor releases? Each bootstrap entry is
guarded by a `try/except` that emits a clear SSE warning frame on
mismatch; the run continues, the operator gets actionable feedback.

---

### 4.6 Cloud-init read-side reflection

**Priority.** Medium.

**Upstream source.** Upstream *writes* cloud-init via
`awx-proxmox-set-ipconfig0.yml` and the related event-rule webhook
fan-out: an operator authors a VM in NetBox, NetBox emits the
`object_created` event, the AWX job template writes the
corresponding `ipconfig0` / `sshkeys` / `ostype` into Proxmox. See
§14 of [`NETBOX-PROXMOX-AUTOMATION.md`](./NETBOX-PROXMOX-AUTOMATION.md)
for the desired-state authoring flow.

**Why it is worth importing.** *Reverse* the write direction. The
plugin's observer stance does not include cloud-init metadata
today — `ipconfig0`, `sshkeys`, and `ostype` are visible in Proxmox
but absent in NetBox. Operators answering "what IP is this VM
configured to come up on?" or "which key is authorised on this VM
on first boot?" have to open Proxmox to find out. Surfacing those
three values as **read-only** custom fields on the synced VM is a
small, additive, observer-compatible enrichment.

**Why it has not landed yet.** Cloud-init reading was never
prioritised because the existing IP and DNS-name flows already cover
the most common "what is this VM's IP?" question for VMs that have
booted. For VMs that have **not** yet booted, only the cloud-init
config has the answer; that gap is the scenario this entry closes.

**Target landing site in this repo.**

- **Three new custom fields**, created by the §4.5 bootstrap pass on
  `virtualization.VirtualMachine`:
  - `proxmox_cloudinit_ipconfig0` — TextField, read-only on the
    NetBox UI side (use `extras.custom_field.ui_visible="hidden"`
    only on the *edit* form; show on the *detail* view).
  - `proxmox_cloudinit_ssh_keys_hash` — short hash (SHA-256, hex)
    of the configured SSH key bundle. Storing the full key list as a
    custom field is too large; the hash lets operators answer "is
    this the key set I expected?" without leaking material.
  - `proxmox_cloudinit_ostype` — choice field over Proxmox's
    `ostype` enum; choices live in an
    `extras.custom_field_choice_set` row created by the §4.5
    bootstrap.
- **Backend reconciler.** Read these three values from the
  `qemu/<id>/config` Proxmox API response (already fetched per-VM
  during sync). Hash the SSH keys server-side; never persist the
  raw key. Write through the §4.1 drift-detect helper.
- **No plugin-side schema change beyond the bootstrap inventory.**
- **No new flag.** This is small enough and read-only enough that
  default-on is acceptable. If an operator wants it off, they can
  unset the custom field in NetBox and the next sync will re-create
  it; gating it behind a flag for that one workflow is overhead.

**Migration sketch.**

1. Extend the §4.5 bootstrap inventory with the three custom fields
   and the choice set.
2. Extend the per-VM reconciler to read the three values from the
   already-fetched config response.
3. Hash the SSH keys via stdlib `hashlib.sha256`; never log the
   plaintext keys.
4. Write through the §4.1 helper. Add a unit test that pins the
   hash format ("sha256:" + 64-hex) so the choice of hash function
   does not silently drift.
5. Document in release notes as an observer enhancement.

**Risks & open questions.** What about VMs that do not use
cloud-init? The three custom-field values stay unset; harmless. What
about operators who hand-edit the custom field values? The
drift-detect helper will overwrite them on the next sync because
Proxmox is the source of truth for cloud-init state — that is by
design and matches the plugin's observer stance. Document loudly in
the release notes. What about VMs whose `ostype` is not in the
choice set? Catch the unknown-choice exception and write `null`;
emit a one-line SSE warning frame; do not fail the run.

---

### 4.7 Strictly opt-in operational verbs as REST endpoints in `proxbox-api`

**Priority.** Medium-Low.

**Upstream source.** `helpers/proxmox_api.py` and the AWX job
templates `awx-proxmox-clone-vm.yml`, `awx-proxmox-start-vm.yml`,
`awx-proxmox-stop-vm.yml`, `awx-proxmox-snapshot-vm.yml`,
`awx-proxmox-migrate-vm.yml`, etc. Upstream exposes ~17 operational
verbs through ~17 NetBox `extras.event_rules` rows that webhook into
either AWX job templates or the Flask shim. The verbs themselves
(start, stop, snapshot, migrate, clone) are sound; the
event-rule + webhook dispatch is what this entry refuses to import.

**Why it is worth importing.** The single biggest gap upstream
highlights against this repo is that `netbox-proxbox` cannot start,
stop, snapshot, or migrate a VM. An operator with a NetBox tab open
on a Proxbox-synced VM cannot act on it without context-switching to
the Proxmox UI. That gap is real. The verbs themselves are a fair
ask. Closing the gap as **REST endpoints inside `proxbox-api`** —
called by **per-VM action buttons** rendered via the existing
`template_extensions` — is observer-compatible: the verb writes are
explicit, operator-initiated, idempotent, and never triggered by a
NetBox `ObjectChange` event.

**Why it has not landed yet — and the constraint that prevented it.**
The natural reading of "let NetBox initiate Proxmox actions" is
upstream's reading: **event rules + webhooks**. That reading inverts
this repo's observer stance by default — every VM save in NetBox
becomes a potential write to Proxmox, the registration step alone
spawns 17 operator-managed objects (17 event rules + 17 webhooks +
their secrets), and the dispatch path requires either AWX (3rd-party
infrastructure) or the Flask shim (synchronous gunicorn worker
holding open a Proxmox API call). All three are rejected by §3.2 and
§5.7 / §5.8. So the verbs were left out — not because they are wrong,
but because the obvious implementation shape is wrong.

**Target landing site in this repo.**

- **Backend endpoints.** New REST routes under
  `proxbox-api/proxbox_api/routes/proxmox_actions.py`. One verb per
  route:
  - `POST /proxmox/qemu/{vmid}/start`
  - `POST /proxmox/qemu/{vmid}/stop`
  - `POST /proxmox/qemu/{vmid}/snapshot` (body: snapshot name)
  - `POST /proxmox/qemu/{vmid}/migrate` (body: target node)
  - LXC siblings: `/proxmox/lxc/{vmid}/start`, etc.
- **Per-endpoint gate.** New boolean field
  `ProxmoxEndpoint.allow_writes`, default `False`. File:
  `netbox_proxbox/models/proxmox_endpoint.py`. New migration with
  `IF NOT EXISTS`. When the flag is off on the endpoint that owns
  the target VM, the backend route returns `403` with a clear
  message.
- **Permission.** New content-type permission
  `core.run_proxmox_action` (gated on `ContentTypePermissionRequiredMixin`,
  the existing operational-endpoint pattern documented in
  [`netbox_proxbox/views/proxbox_access.py`](../netbox_proxbox/views/proxbox_access.py)).
  Operators get fine-grained control: a read-only NetBox user keeps
  read-only access to the VM detail page; the action buttons are
  hidden unless the user has the new permission.
- **Plugin-side button wiring.** Use the existing
  `template_extensions` registration to add per-VM buttons that POST
  to the `proxbox-api` route through the existing backend-proxy
  helper. Each button is wrapped in a confirmation modal with the
  VM identity displayed.
- **Idempotency.** Each route accepts an `Idempotency-Key` header
  (per RFC draft); two POSTs with the same key inside a 60-second
  window resolve to the same single Proxmox call. This protects
  against double-click and against retried webhook deliveries (if
  this surface is ever called by external automation).
- **Audit trail.** Each verb call writes a NetBox `ObjectChange`-
  shaped log entry on the linked VM via the `extras.journal_entries`
  endpoint, recording the verb, the actor, the result, and the
  Proxmox task ID.

**Migration sketch.**

1. Land the design doc first. Pin the permission model (§4.7
   above), the cancellation semantics (a `start` cannot be
   cancelled mid-flight; a `migrate` *can*; document each verb's
   behaviour), the idempotency-token shape, the audit-log payload,
   and the per-endpoint `allow_writes` default.
2. Land `allow_writes` and the permission. One PR, one migration,
   one permission registration. No verb routes yet — just the gate.
3. Land verbs one at a time, one PR per verb, in this order:
   `start` → `stop` → `snapshot` → `migrate`. Each verb is a
   separate review surface; each ships with its own permission test,
   idempotency test, and journal-entry test.
4. Land the plugin-side button wiring last. Until then, the backend
   routes are reachable by external automation but invisible in the
   NetBox UI.
5. Document each verb in release notes with a loud security
   disclaimer: enabling `allow_writes` on an endpoint widens the
   trust boundary; `core.run_proxmox_action` should be restricted
   to a small operator group.

**Risks & open questions.** What about race conditions between a
running sync and a verb call? The verb calls Proxmox directly; the
next sync reflects the new state. No additional locking needed,
because Proxmox is the source of truth. What about partial failures
(start succeeds in Proxmox API but the response gets lost)? The
idempotency key plus the next sync's reconciliation closes the loop:
the verb is safe to retry, and the next observer pass corrects the
NetBox-side view. What about long-running verbs (migrate)? Return
the Proxmox task ID immediately; emit progress through a dedicated
SSE channel; the NetBox UI polls task status separately. What about
operators who *want* the upstream event-rule + webhook shape because
they have existing automation built on it? They can keep using
`netbox-proxmox-automation` for that; the two systems coexist (§10
of [`PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md)).

---

### 4.8 Discovery-tag pattern

**Priority.** Low.

**Upstream source.** `setup/netbox_setup_objects_and_custom_fields.py`
creates two `extras.tags` rows: `proxmox-vm-discovered` (slug
`proxmox-vm-discovered`) and `proxmox-lxc-discovered` (slug
`proxmox-lxc-discovered`). Discovery scripts apply the appropriate tag
to every newly-created VM / LXC. Operators can then filter on
"objects this automation just created" with one tag query.

**Why it is worth importing.** Auditability. After a large initial
sync into a populated NetBox, operators want to answer "show me only
the VMs Proxbox just imported, not the ones that were already here".
NetBox's tag filter is the canonical shape for that query. Without
the tag, operators have to reverse-engineer the answer from custom-
field presence or `last_updated` ranges, which is brittle.

**Why it has not landed yet.** Trivial; never prioritised because
the use case is operator-side audit rather than runtime correctness.

**Target landing site in this repo.**

- **§4.5 bootstrap inventory.** Add the two tags. (This entry is
  effectively a tail of §4.5; sequencing is set out in §6.)
- **Backend reconciler.** In the VM and LXC reconcilers in
  `proxbox-api/proxbox_api/proxmox_to_netbox/`, after a `created`
  result from the §4.1 helper (and only `created`, not `updated` —
  this tags first-discovery, not every reconcile), add the
  appropriate tag.
- **No plugin-side schema change.** No new flag. The behaviour is
  always-on once the bootstrap has shipped.

**Migration sketch.**

1. Extend the §4.5 bootstrap inventory.
2. One conditional line in each reconciler: `if status == "created":
   apply_tag(record, "proxmox-vm-discovered")`. Reuse §4.1's status
   enum.
3. Test: pin the behaviour with a unit test that creates one VM,
   asserts the tag, runs a second reconcile, and asserts no second
   tag application.
4. Document in release notes as a one-line bullet.

**Risks & open questions.** What about operators who delete the
tag manually? The next reconcile leaves the deleted tag deleted —
the tag is applied only on creation, not on every sync, so manual
deletes stick. What about renaming the tag? Tag lookup is by slug;
a renamed tag's slug stays the same, so the §4.5 idempotency check
will not double-create. Renamed-and-re-slugged is a destructive
choice; the bootstrap will re-create the original tag at the
original slug, and the operator ends up with both. Acceptable; not
worth special-casing.

---

### 4.9 IPv6 link-local skip + zone-ID stripping in IP sync

**Priority.** Low.

**Upstream source.** `setup/netbox-discover-proxmox-vms.py`. The
upstream discovery script deliberately skips IPv6 link-local
addresses (`fe80::/10`) — they are interface-scoped, not globally
unique, and writing them to NetBox creates spurious "duplicate
address across interfaces" rows. It also strips IPv6 zone IDs (the
`%eth0` suffix) before writing — NetBox's IPAM rejects addresses
with zone IDs as malformed, and the zone ID carries no information
NetBox needs (the interface is already linked).

**Why it is worth importing.** Defensive. Both behaviours are pure
correctness fixes. If the backend already implements them, this
entry collapses to a verification-only test entry. If it does not,
this entry adds two short defensive guards to the IP reconciler.

**Why it has not landed yet.** Possibly already done — needs a
spot-check of `proxbox-api/proxbox_api/proxmox_to_netbox/`. The IPv6
zone-ID footgun is rarely hit in practice (most Proxmox-reported
addresses are already cleaned), so a missing guard would have been
silent until someone hits a case that triggers it.

**Target landing site in this repo.**

- **Backend IP reconciler.** Spot-check the IP reconciler. If
  link-local skip and zone-ID stripping are not present, add them
  as the first two operations in the per-IP write path:
  - Skip if `ip in IPv6Network("fe80::/10")`.
  - Strip everything from `%` onwards if present.
- **No plugin-side change.** No new flag. Behaviour-correctness
  fix.

**Migration sketch.**

1. Spot-check; document the result in the PR description.
2. If absent: add the two guards; cover with unit tests
   (`fe80::1` skipped, `fe80::1%eth0` skipped, `2001:db8::1%eth0`
   becomes `2001:db8::1`).
3. If present: add an AST source-contract test that pins the
   behaviour at the current code so any regression fails CI.
4. No release-notes entry needed unless a code change was required.

**Risks & open questions.** What about operators who *want*
link-local addresses recorded? Out of scope; if a future operator
asks for it, gate it behind a flag. What about IPv6 unique
local addresses (`fc00::/7`)? Those *are* globally meaningful within
the operator's own scope; record them as-is. What about
link-local addresses that are operator-assigned static routes?
Same answer — out of scope for the default reconciler.

---

## 5. Explicit Non-Imports

These items are present in `netbox-proxmox-automation` and **should
not** be ported. Each entry cites the policy or contract that
rejects it.

### 5.1 No-queue synchronous webhook execution (held gunicorn worker)

The Flask shim in `helpers/proxmox_api.py` accepts an HTTP webhook
from NetBox, runs the entire Proxmox API call in the request /
response cycle, and returns. A long Proxmox call holds a gunicorn
worker for the duration, blocks any cancel attempt, and fails
ungracefully on the first reverse-proxy timeout. Already named as a
rejected pattern in §7.4 of
[`PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md).
Upstream's contract here is RQ + SSE: the trigger enqueues a
`ProxboxSyncJob` on the `default` queue with
`job_timeout=PROXBOX_SYNC_JOB_TIMEOUT` (7200s), and the SSE between-
chunk read timeout (3600s) lives inside `run_sync_stream`. That is
the only sustainable shape for any work that talks to Proxmox over a
network and it is documented in [`CLAUDE.md`](../CLAUDE.md) under
"Backend integration notes".

### 5.2 File-based YAML config (`conf.d/netbox_setup_objects.yml`, `app_config.yml`)

Upstream's bootstrap inventory and runtime tunables both live in
on-disk YAML. This is rejected by the **DB-first config policy** in
[`CLAUDE.md`](../CLAUDE.md) "Plugin settings and configuration":
runtime tunables go in `ProxboxPluginSettings` (migration `0037` is
the canonical example), and bootstrap inventory goes in code (see
§4.5 above). Inventing parallel JSON / YAML config layers to dodge
the migration cost of a new field is explicitly prohibited.

### 5.3 `verify_ssl=False` hardcode in the Flask helper

Upstream's `helpers/proxmox_api.py` passes `verify_ssl=False`
unconditionally to its Proxmox HTTPS client. The 0.0.15 release
explicitly decoupled `Use HTTPS` from `Verify SSL` precisely because
this overload is dangerous; see
[`docs/release-notes/version-0.0.15.md`](../docs/release-notes/version-0.0.15.md)
§ "#352 — `Use HTTPS` toggle decoupled from `Verify SSL`".
Hardcoding verification off would re-introduce silent MITM exposure
on every install and undo the work that release shipped.

### 5.4 MB÷1000 vs ÷1024 unit drift between Flask and Ansible

Upstream's Flask helper computes memory in MB÷1000 while at least
one of its Ansible playbooks computes the same field in MB÷1024.
The two paths produce different numbers for the same VM. This is a
straightforward bug, not a feature; conversions belong in **one**
place and must round-trip. The §4.1 drift-detect helper plus a
single conversion helper in
`proxbox-api/proxbox_api/services/units.py` is the right shape; do
not import the bug.

### 5.5 Plaintext credentials anywhere on disk

Upstream stores Proxmox credentials in plain text in
`conf.d/proxmox_credentials.yml` (or equivalent), and NetBox
credentials in plain text in the AWX job-template inputs. This is
rejected: the backend Fernet store keyed by `PROXBOX_ENCRYPTION_KEY`
is the only place plaintext credentials exist for any meaningful
interval, and runtime rotation lives at
`routes/admin/encryption.py` (0.0.11). Any artifact this repo
ships — config example, docker-compose, CI fixture — must use the
Fernet store, not a plaintext file.

### 5.6 No test suite at all

Upstream ships zero pytest files. This repo has 50+ pytest files
including:

- AST source-contract tests (`tests/test_form_and_helper_source_contracts.py`,
  `tests/test_views_vm_config.py`, `tests/test_views_vm_ha.py`,
  `tests/test_views_ha.py`, `tests/test_cli_contracts.py`).
- The cross-repo overwrite-flags drift detector
  (`tests/test_overwrite_flags_contract.py`) paired with the
  manifest at `contracts/overwrite_flags.json` and its sibling in
  `proxbox-api`.
- The SSE schema mirror test (`tests/test_sse_schema_mirror.py`)
  paired with `contracts/proxbox_api_sse_schema.json`.

Any code imported from upstream must come with tests in *this*
shape — AST contracts where applicable, drift detectors where the
two repos must stay aligned, schema mirrors where the wire format
matters. Importing untested code is rejected.

### 5.7 AWX / Tower / AAP dependency for any operational verb

Upstream ships ~13 Ansible playbooks meant to be imported as AWX /
Tower / AAP job templates. Each verb (clone, set-ipconfig0, start,
stop, snapshot, migrate) is one job template. The dispatch path
requires AWX as the execution medium. AWX is heavy, opinionated 3rd-
party infrastructure that adds an entire authn / authz / inventory /
audit surface. The §4.7 carve-out exposes the same verbs as REST
endpoints inside `proxbox-api` — no AWX dependency, no inventory
authoring, no separate auth surface, no second audit log. The verbs
are valid; the dispatch shape is not.

### 5.8 17-event-rule + 17-webhook setup-time explosion

Upstream's installation guide is, in significant part, "create these
17 `extras.event_rules` rows and these 17 `extras.webhooks` rows
with these specific filters and these specific URLs". That is 34
operator-managed NetBox objects per install, all of which must stay
synchronised with the backend's URL routing, all of which carry
shared secrets. Setup is fragile (one misnamed filter and the verb
silently no-ops), upgrade is fragile (a new verb adds two more
objects), and audit is hard (operators cannot tell at a glance
which rules are still wired correctly). The §4.7 carve-out exposes
verbs through **per-VM action buttons** rendered by the existing
`template_extensions` plus authenticated REST calls — not through 34
operator-managed NetBox objects.

### 5.9 CalVer (`2025.11.01`) versioning

Upstream uses CalVer-style version tags (`2025.11.01` and similar).
This repo is on SemVer; `tests/test_version.py` pins the three
version surfaces (`pyproject.toml`, `setup.py` if present, and
`PluginConfig.version`) to a SemVer string and will fail loudly on a
CalVer string. Cosmetic mismatch; no benefit to importing.

### 5.10 BIND9 / gss-tsig DNS update path

Upstream includes Ansible plumbing to push DNS records into a BIND9
server via gss-tsig dynamic updates as part of the VM-creation flow.
The IPAM `dns_name` write added in 0.0.15 (§ "#354 — IPAM
`dns_name` populated from Proxmox guest hostnames" of
[`docs/release-notes/version-0.0.15.md`](../docs/release-notes/version-0.0.15.md))
already covers the "hostname-in-NetBox" use case that BIND
integration would otherwise serve from this repo. Anything beyond
that — actual DNS-server-side record management — belongs in a
dedicated DNS plugin (see `netbox-plugin-dns` for the canonical
shape), not here. Out of scope for `netbox-proxbox`.

### 5.11 Custom-field group renaming (`Proxmox (common)` / `Proxmox VM` / `Proxmox LXC`)

Upstream organises its custom fields into three named groups:
`Proxmox (common)`, `Proxmox VM`, and `Proxmox LXC`. This repo's
existing custom-field grouping is already coherent and used by every
existing install. Renaming the groups to match upstream would churn
every existing install (operator-visible field labels change,
reports break, dashboards re-render) for zero functional benefit.
Cosmetic-only; not imported.

---

## 6. Implementation Sequencing

Recommended order, with rationale:

1. **§4.1 drift-detecting writes first.** This is the foundation
   every other backend-write entry benefits from. Shipping it
   reduces ChangeLog spam immediately, gives §4.5 / §4.6 / §4.8
   their idempotency primitive, and makes the §4.4 spot-check trivial
   (the helper either is or is not in use).

2. **§4.5 NetBox-side bootstrap next.** It makes clean installs
   work without operator NetBox prep, and gives §4.6 (cloud-init
   custom fields) and §4.8 (discovery tags) a place to land. It
   also depends on §4.1 for its idempotency story.

3. **§4.4 `dcim.mac_addresses` linkage.** The spot-check is small;
   if the modern model is already in use, this entry collapses to
   a verification-only test entry. If it is not, this is the
   highest-priority correctness fix because NetBox 4.6 compatibility
   needs it.

4. **§4.6 cloud-init reflection.** Small, additive, observer-
   compatible. Lands cleanly once §4.5 is in.

5. **§4.9 IPv6 hardening.** Defensive, low risk. Same shape as
   §4.4: spot-check first, code or test second.

6. **§4.8 discovery tag.** Single-line write at object creation,
   gated by §4.5. Lowest-risk feature in the list.

7. **§4.2 branching support.** Separate-feature PR; orthogonal to
   the rest. Land any time after §4.1.

8. **§4.3 hardware discovery.** Biggest scope of the observer-
   compatible items. Three new components: encrypted SSH credential
   field, opt-in pipeline stage, optional dependency. Ship after
   §4.1 and §4.5 stabilise.

9. **§4.7 operational verbs last.** And only after a written
   design doc that pins permission model, cancellation semantics,
   idempotency-token shape, and audit-log payload. Each verb
   (`start`, `stop`, `snapshot`, `migrate`) is a separate PR. Plugin-
   side button wiring is the last PR in the chain. None of this
   ships until §4.1, §4.5, and the design doc are in.

This sequencing keeps every PR small, every schema change additive,
and every behaviour change either default-off or behaviour-
preserving on existing installs. The 0.0.15 release notes are the
canonical template for what a "new opt-in flag" PR description
should look like; the §4.7 release notes will need to additionally
spell out the security implications of `allow_writes`.

---

## 7. Cross-References

- [`NETBOX-PROXMOX-AUTOMATION.md`](./NETBOX-PROXMOX-AUTOMATION.md) —
  standalone deep-dive on `netbox-proxmox-automation`. Canonical
  source for all "the upstream does X" claims in §4 and §5; §20
  pre-chews the "patterns worth borrowing / patterns to reject"
  split that this document refines into action items.
- [`PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md) —
  side-by-side comparison; canonical source for "this repo does Y,
  the upstream does X" claims, the §6 21-row feature comparison,
  and the §7 5-section code-pattern comparison referenced in §3.1
  and §3.2.
- [`EDGEUNO-FORK-VALID-TO-IMPLEMENT.md`](./EDGEUNO-FORK-VALID-TO-IMPLEMENT.md) —
  sibling action-list with the same per-entry template; covers a
  different upstream (the EdgeUno fork) with a different framing
  (downstream of *this* repo, observer-compatible by lineage).
- [`../CLAUDE.md`](../CLAUDE.md) — policy authority cited throughout
  §3 (criteria), §4 (target landing sites), and §5 (non-imports).
- [`../docs/release-notes/version-0.0.15.md`](../docs/release-notes/version-0.0.15.md) —
  reference template for "new opt-in flag + migration + form /
  serializer / table surface + `_build_base_query_params` query-
  string forwarding + backend handler". Every flag-shaped §4 entry
  follows this shape.
- `../netbox_proxbox/__init__.py:124-125` — `min_version="4.5.8"`,
  `max_version="4.6.99"`. Pinned by §4.4 (NetBox 4.5+ MAC object
  model is mandatory in this window).
- `../netbox_proxbox/constants.py:5,64` — `OVERWRITE_FIELD_GROUPS`
  and `OVERWRITE_FIELDS`, the canonical 23-flag set every new flag
  must extend.
- `../contracts/overwrite_flags.json` — manifest mirrored against
  the sibling in `proxbox-api/contracts/overwrite_flags.json`;
  pinned by `../tests/test_overwrite_flags_contract.py`.
- `../contracts/proxbox_api_sse_schema.json` — SSE frame schema
  referenced by §4.1 (the new `unchanged` counter), §4.3 (the new
  `node_hardware_*` frames), and §4.5 (the new `bootstrap_done`
  frame); pinned by `../tests/test_sse_schema_mirror.py`.
- `../netbox_proxbox/migrations/0037_pluginsettings_runtime_tunables.py`,
  `../netbox_proxbox/migrations/0038_fastapiendpoint_use_https.py`,
  `../netbox_proxbox/migrations/0039_pluginsettings_overwrite_ip_address_dns_name.py` —
  three canonical "production-safe additive schema change"
  migrations every §4 migration sketch references.
- `../netbox_proxbox/management/commands/proxbox_fix_tokens.py` —
  shape reference for any new management command (none introduced
  by this document; used as the "we already have this pattern"
  citation under §3.1).
- `../netbox_proxbox/views/proxbox_access.py` — existing
  `ContentTypePermissionRequiredMixin` permission registrations;
  shape reference for the new `core.run_proxmox_action` permission
  in §4.7.
- `../proxbox_cli/__init__.py` — Typer app entry point. Not
  modified by any §4 entry, but cited under §3.3 as a reusable
  surface for any future CLI affordances atop these patterns.
- `/root/nms/netbox-proxmox-automation/helpers/netbox_objects.py` —
  upstream source for §4.1.
- `/root/nms/netbox-proxmox-automation/helpers/netbox_branches.py` —
  upstream source for §4.2.
- `/root/nms/netbox-proxmox-automation/setup/netbox-discover-proxmox-cluster-and-nodes.py` —
  upstream source for §4.3.
- `/root/nms/netbox-proxmox-automation/setup/netbox-discover-proxmox-vms.py` —
  upstream source for §4.4 and §4.9.
- `/root/nms/netbox-proxmox-automation/setup/netbox_setup_objects_and_custom_fields.py` —
  upstream source for §4.5 and §4.8.
- `/root/nms/netbox-proxmox-automation/awx-proxmox-set-ipconfig0.yml` —
  upstream source for the *write*-direction cloud-init flow;
  reversed for §4.6.
- `/root/nms/netbox-proxmox-automation/helpers/proxmox_api.py` —
  upstream source for §4.7's verbs (rejected dispatch shape; see
  §5.7 / §5.8).
