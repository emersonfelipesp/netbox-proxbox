# Implementation Roadmap

This document is a **sequenced milestone roadmap** across the two
action-list reference docs in this directory. It does not re-explain
either source list; it answers the orthogonal question
**"in what order do we ship these 19 items, grouped how, with what
dependencies between them, and how does each piece earn its place
in a release cycle?"**.

Read the source docs first if you need the *why* behind any cell:

- [`EDGEUNO-FORK-VALID-TO-IMPLEMENT.md`](./EDGEUNO-FORK-VALID-TO-IMPLEMENT.md)
  — 10 import candidates from the EdgeUno fork at
  `/root/nms/edgeuno/netbox-proxbox`.
- [`PROXMOX-AUTOMATION-VALID-TO-IMPLEMENT.md`](./PROXMOX-AUTOMATION-VALID-TO-IMPLEMENT.md)
  — 9 import candidates from the NetBox Labs project at
  `/root/nms/netbox-proxmox-automation`.

Both source docs use the same seven-field-per-entry template
(Priority / Source / Why import / Why not yet / Target landing site
/ Migration sketch / Risks). Their per-item detail is the contract
this roadmap relies on. This file cites them by section number —
e.g. **"automation §4.1"** = `PROXMOX-AUTOMATION-VALID-TO-IMPLEMENT.md`
section 4.1; **"EdgeUno §4.9"** = `EDGEUNO-FORK-VALID-TO-IMPLEMENT.md`
section 4.9.

---

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [TL;DR](#2-tldr)
3. [Methodology / Re-Ranking](#3-methodology--re-ranking)
4. [Cross-Source Synergies & Conflicts](#4-cross-source-synergies--conflicts)
5. [Milestones](#5-milestones)
   - 5.1 [v0.0.16 — Foundation](#51-v0016--foundation)
   - 5.2 [v0.0.17 — Observer Enrichment](#52-v0017--observer-enrichment)
   - 5.3 [v0.0.18 — Sync Auditability](#53-v0018--sync-auditability)
   - 5.4 [v0.0.19 — Operations & Ergonomics](#54-v0019--operations--ergonomics)
   - 5.5 [v0.0.20 — Operational Verbs (carve-out)](#55-v0020--operational-verbs-carve-out)
6. [Critical Path](#6-critical-path)
7. [Combined Non-Imports Index](#7-combined-non-imports-index)
8. [Cross-References](#8-cross-references)

---

## 1. Purpose & Scope

`netbox-proxbox 0.0.15` and `proxbox-api 0.0.11` were certified
together on 2026-05-07 against NetBox 4.5.8 / 4.5.9 / 4.6.0. The two
action-list reference docs in this directory inventory **what** is
worth importing from two separate upstream projects and **where**
each item lands in the two-service codebase. Together they propose
**19** candidate imports, each with a fixed seven-field justification
template.

This roadmap takes those 19 items, re-ranks them across both source
docs, surfaces dependencies between items that originated in
different docs, and groups the result into five proposed releases on
the existing 0.0.x line — **v0.0.16 Foundation** through
**v0.0.20 Operational Verbs**. Each milestone is a coherent themed
release: a reader of the roadmap can predict what a given release
brings without reading the source docs end-to-end.

This is **not a merger**. The full per-item detail (target landing
site, migration sketch, risk callouts) lives in the two source docs;
this file cites them and does not duplicate. Treat it as the input to
a roadmap-planning session, paired with [`docs/roadmap.md`](../docs/roadmap.md).
This document does not propose a release calendar; it does not write
code; it does not assign owners. Milestone naming is the *theme*,
not a calendar commitment.

---

## 2. TL;DR

Nineteen items, five milestones. Sorted by milestone, then by
ship-within-milestone order.

| #  | Item                                                       | Source     | §    | Original priority | Milestone | Blockers                     |
|----|------------------------------------------------------------|------------|------|-------------------|-----------|------------------------------|
| 1  | Drift-detecting writes (`createOrUpdate` helper)            | automation | 4.1  | High              | v0.0.16   | none                         |
| 2  | NetBox-side bootstrap of supporting objects                 | automation | 4.5  | Medium            | v0.0.16   | item #1                      |
| 3  | `dcim.mac_addresses` linkage spot-check + fix-or-pin        | automation | 4.4  | Medium            | v0.0.16   | item #1 (if rewrite needed)  |
| 4  | `proxbox_sync` Django management command                    | EdgeUno    | 4.4  | High              | v0.0.16   | none                         |
| 5  | Cloud-init read-side reflection (`ipconfig0` + 2 fields)    | automation | 4.6  | Medium            | v0.0.17   | items #1, #2                 |
| 6  | Discovery-tag pattern (`proxmox-vm-discovered` etc.)        | automation | 4.8  | Low               | v0.0.17   | items #1, #2                 |
| 7  | IPv6 link-local skip + zone-ID strip                        | automation | 4.9  | Low               | v0.0.17   | none (defensive)             |
| 8  | Tenant assignment by VM-name regex                          | EdgeUno    | 4.1  | High              | v0.0.17   | item #1                      |
| 9  | `description`-field parsing (4 new overwrite flags)         | EdgeUno    | 4.2  | High              | v0.0.17   | item #1                      |
| 10 | Role pinning by VM type (`VPS` / `LXC`)                     | EdgeUno    | 4.3  | Medium            | v0.0.17   | item #2                      |
| 11 | `latest_job` UUID stamp + `delete_orphans` (3 sub-PRs)      | EdgeUno    | 4.9  | High              | v0.0.18   | items #1, #2                 |
| 12 | Duplicate-VM-name `" (2)"` suffix + new SSE frame           | EdgeUno    | 4.8  | Medium            | v0.0.18   | item #1                      |
| 13 | Optional NetBox Branching (`X-NetBox-Branch`) support       | automation | 4.2  | Medium            | v0.0.18   | item #1                      |
| 14 | One-shot `docker-compose-single-exec.yml`                   | EdgeUno    | 4.6  | Medium            | v0.0.19   | item #4                      |
| 15 | Standalone scheduler container (`PROXBOX_MODE`)             | EdgeUno    | 4.5  | Medium            | v0.0.19   | item #4                      |
| 16 | `pxb sync run` CLI subcommand                               | EdgeUno    | 4.7  | Low               | v0.0.19   | item #4                      |
| 17 | Hardware discovery via SSH + `dmidecode` + `ethtool`        | automation | 4.3  | Medium            | v0.0.19   | items #1, #2                 |
| 18 | `ProxboxSession`-style backend refactor (optional)          | EdgeUno    | 4.10 | Low               | v0.0.19   | none                         |
| 19 | Strictly opt-in operational verbs as REST endpoints         | automation | 4.7  | Medium-Low        | v0.0.20   | items #1, #2; design doc PR  |

The "Blockers" column refers to roadmap-row numbers (the leftmost
column), not source-doc section numbers, so the table is self-
contained. Items #1, #2 (drift-detect helper + bootstrap pass) are
the load-bearing primitives the rest of the roadmap reuses; that
is why v0.0.16 ships them first.

---

## 3. Methodology / Re-Ranking

### 3.1 Why re-rank

The two source action lists were authored independently. Both use a
three-tier priority scale (High / Medium / Low) but a "High" in one
doc is not automatically more urgent than a "Medium" in the other;
the scales are calibrated against different upstream comparisons. A
roadmap that cared only about original priority would land EdgeUno
§4.1 (tenant regex, High) before automation §4.1 (`createOrUpdate`,
High) without any way to tell that the second is a foundational
primitive the first benefits from. The roadmap therefore re-ranks
across both docs with explicit rules.

### 3.2 Re-ranking rules, in order of authority

1. **NetBox 4.6 compatibility correctness wins over additive
   features.** Anything required for the plugin to remain certified
   inside the `min_version="4.5.8"` / `max_version="4.6.99"` window
   declared at `netbox_proxbox/__init__.py:124-125` is non-optional.
   If automation §4.4's spot-check shows the legacy MAC string
   field is still in use, item #3 rises to v0.0.16 by this rule.
2. **Foundational primitives that other items reuse win over leaf
   features.** Items #1 and #2 (drift-detect helper, bootstrap pass)
   ship in v0.0.16 because items #5, #6, #10, #11 — and most of the
   v0.0.17 and v0.0.18 work — reuse their idempotency and lookup
   semantics. Shipping a leaf feature first would mean writing the
   primitive twice.
3. **Schema-additive observer features win over opt-in writes win
   over new dispatch surfaces win over operational verbs.** Sync
   enrichment (cloud-init, tenant regex, role pin) lands in v0.0.17;
   sync auditability (delete_orphans, branching) in v0.0.18; new
   dispatch surfaces (scheduler, single-exec compose, pxb subcommand)
   in v0.0.19; verbs in v0.0.20. The §4.7 carve-out is last by
   design — it ships only after the design doc PR pins permission,
   cancellation, idempotency, and audit-log payload.

### 3.3 What a "milestone" means here

A proposed minor or patch release tagged against the existing 0.0.x
line. Each milestone bundles items that share a theme and a wiring
shape — same `_build_base_query_params` plumbing change, same
`OVERWRITE_FIELDS` manifest update, same release-notes section
template. Bundling lets the cross-repo overwrite-flags drift
detector at `tests/test_overwrite_flags_contract.py` catch any
manifest mistakes once per release instead of once per item.

The 0.0.15 release is the canonical reference template for what a
"new opt-in flag" PR description and migration look like; see
[`docs/release-notes/version-0.0.15.md`](../docs/release-notes/version-0.0.15.md)
for the full inventory of model field → migration with `IF NOT
EXISTS` → form / serializer / table surface →
`_build_base_query_params` query-string forwarding → backend handler
→ AST contract test.

---

## 4. Cross-Source Synergies & Conflicts

Six places where an item from one source doc materially affects an
item from the other. Each entry is the load-bearing rationale for
*why* a milestone bundles what it bundles.

### 4.1 automation §4.1 `createOrUpdate` ↔ EdgeUno §4.9 `delete_orphans`

Both touch the per-record write path. Ship automation §4.1 first
(item #1, v0.0.16); EdgeUno §4.9's `latest_job` stamp + sweep
(item #11, v0.0.18) reuses §4.1's diff semantics for "did this
object change in this run?" identification. Without §4.1 the sweep
has no clean idempotency primitive — the sweep would either
re-implement the diff or operate at the coarser "stamp-or-not-stamp"
granularity, both of which are inferior to the §4.1 helper's
field-level diff. This is the single highest-leverage synergy in the
roadmap.

### 4.2 automation §4.5 bootstrap ↔ EdgeUno §4.3 role pinning

Bootstrap (item #2, v0.0.16) creates the `dcim.device_roles` rows
(`Hypervisor`, etc.); role pinning (item #10, v0.0.17) consumes
them. Bootstrap ships first; role pinning fails gracefully if
bootstrap is off, because EdgeUno §4.3 already specifies "log + skip,
do not crash" when the named role is missing. Operators who disable
the bootstrap (`ensure_netbox_objects=False`) and want role pinning
must pre-create the roles; the failure mode is a one-line warning
SSE frame, not a crash.

### 4.3 automation §4.5 bootstrap ↔ automation §4.8 discovery tags ↔ automation §4.6 cloud-init custom fields

All three depend on the bootstrap pass owning the `extras.tags` and
`extras.custom_fields` / `extras.custom_field_choice_sets`
creation. Sequence within the roadmap: §4.5 (item #2, v0.0.16) →
(§4.6 item #5 + §4.8 item #6 in either order, both v0.0.17). The
two leaf items ship in v0.0.17 because v0.0.16 is bandwidth-
constrained on the foundation work; bundling all three into one
release would inflate the v0.0.16 review surface unnecessarily.

### 4.4 EdgeUno §4.4 management command ↔ EdgeUno §4.5 scheduler ↔ EdgeUno §4.6 single-exec compose ↔ EdgeUno §4.7 pxb subcommand

A clean dependency chain: management command (item #4, v0.0.16)
first, then the three thin wrappers around it (items #14, #15, #16,
all v0.0.19). The wrappers exist *because* the command exists; none
of them adds new sync logic. Splitting the wrappers across v0.0.19
keeps the v0.0.16 review surface small (one new file at
`netbox_proxbox/management/commands/proxbox_sync.py`) while letting
v0.0.19 ship the deployment artefacts together.

### 4.5 automation §4.2 NetBox Branching support ↔ everything else

Branching (item #13, v0.0.18) is orthogonal: the toggle installs an
`X-NetBox-Branch` header on the `netbox-sdk` session for the
duration of a run. Once item #1 (`createOrUpdate`) is in, branching
layers on transparently because every backend write goes through
the same helper which goes through the same session. No conflicts;
ship any time after v0.0.16. It is bundled into v0.0.18 (Sync
Auditability) because the feature is *most useful* alongside
`delete_orphans`: an operator who wants to dry-run a deletion-
producing run on a branch first.

### 4.6 automation §4.7 operational verbs ↔ EdgeUno §4.4 management command

Both are dispatch surfaces but they do not conflict. The management
command (item #4) is a sync-trigger; the verbs (item #19) are
per-VM operational actions. They share a permissions story
(`ContentTypePermissionRequiredMixin` from
[`netbox_proxbox/views/proxbox_access.py`](../netbox_proxbox/views/proxbox_access.py)),
a release-notes security-disclaimer pattern, and a 0.0.15-style
migration shape, but no code. They land in different milestones
(v0.0.16 vs v0.0.20) because the verbs are deliberately gated
behind a written design doc PR (see §5.5).

---

## 5. Milestones

Each milestone subsection uses the same sub-template:

- **Theme.** One line.
- **Summary.** Two sentences.
- **Items.** Table of items; numbers refer to the §2 TL;DR row
  number.
- **Schema changes.** New columns, new flags. One bullet per item.
- **Contract changes.** Updates to `OVERWRITE_FIELDS`, the SSE
  schema, and the cross-repo manifests.
- **Dependencies.** What must have shipped before this milestone.
- **Acceptance criteria.** Concrete, observable. The plugin's
  existing test suite (`tests/test_overwrite_flags_contract.py`,
  `tests/test_sse_schema_mirror.py`,
  `tests/test_form_and_helper_source_contracts.py`) is the canary
  for most of these.
- **Risk callouts.** Things unique to this milestone.

### 5.1 v0.0.16 — Foundation

**Theme.** Drift-detect primitive + idempotent bootstrap +
management-command trigger.

**Summary.** The release that makes the rest of the roadmap
possible. Three of the four items are the foundational primitives
that subsequent milestones reuse; the fourth (management command)
unblocks the v0.0.19 deployment-artefact work and gives operators a
cron / Kubernetes / Ansible-friendly trigger today.

**Items.**

| # | Item                                                | Source     | §   | Order |
|---|-----------------------------------------------------|------------|-----|-------|
| 1 | Drift-detecting writes (`createOrUpdate` helper)     | automation | 4.1 | 1     |
| 2 | NetBox-side bootstrap of supporting objects          | automation | 4.5 | 2     |
| 3 | `dcim.mac_addresses` linkage spot-check + fix-or-pin | automation | 4.4 | 3     |
| 4 | `proxbox_sync` Django management command             | EdgeUno    | 4.4 | 4     |

**Schema changes.**

- Item #2: new `ProxboxPluginSettings.ensure_netbox_objects`
  (default `True`). Migration follows
  [`0037_pluginsettings_runtime_tunables.py`](../netbox_proxbox/migrations/0037_pluginsettings_runtime_tunables.py)
  shape with `IF NOT EXISTS`.
- Items #1, #3, #4: no schema changes.

**Contract changes.**

- SSE schema: new `unchanged` counter on the run-summary frame
  (item #1); new `bootstrap_done` event (item #2). Mirror at
  `netbox_proxbox/schemas/backend_proxy.py`; canary at
  `tests/test_sse_schema_mirror.py`.
- `OVERWRITE_FIELDS` / manifests: no changes.

**Dependencies.** None. v0.0.16 can ship against the v0.0.15
codebase as-is.

**Acceptance criteria.**

- Item #1: a second consecutive full sync against an unchanged
  Proxmox cluster emits zero NetBox `ObjectChange` rows. Pin in a
  test that runs two syncs back-to-back and counts diffs.
- Item #2: a fresh NetBox install (no Proxmox cluster type, no
  device role, no choice sets) accepts a first sync without any
  operator NetBox prep. The bootstrap pass creates everything.
- Item #3: AST source-contract test pins the interface / IP
  reconciler at the new `dcim.mac_addresses` object model. If a
  rewrite was required, the PR description documents the legacy
  → modern transition.
- Item #4: `python manage.py proxbox_sync --endpoint <name>`
  enqueues a `ProxboxSyncJob` on the `default` queue and exits
  zero; `--wait` blocks until terminal and exits non-zero on
  `errored` / `failed`.

**Risk callouts.**

- Item #1's diff semantics around `None` / `""` / unset must be
  pinned by tests *before* call sites migrate; otherwise the per-
  reconciler migration risks introducing silent diff mismatches
  against NetBox-validated state. Item #1's PR ships first; each
  reconciler migration is a follow-up PR with its own "second-run-
  is-silent" assertion.
- Item #3 is a spot-check first. If the modern model is already in
  use, item #3 collapses to a verification-only AST test entry; if
  not, the rewrite is the largest single piece of work in v0.0.16
  and ships against item #1 having already landed.

### 5.2 v0.0.17 — Observer Enrichment

**Theme.** Six small, observer-compatible enrichments that all
reuse the v0.0.16 primitives.

**Summary.** Each item adds operator-visible signal that Proxmox
already carries — cloud-init metadata, discovery-tag audit, IPv6
hardening, tenant-by-regex, description-parsed metadata, role-by-
type. None inverts the observer stance; all are opt-in or
default-on-and-additive.

**Items.**

| #  | Item                                                  | Source     | §   | Order |
|----|-------------------------------------------------------|------------|-----|-------|
| 7  | IPv6 link-local skip + zone-ID strip                  | automation | 4.9 | 1     |
| 6  | Discovery-tag pattern (`proxmox-vm-discovered` etc.)  | automation | 4.8 | 2     |
| 5  | Cloud-init read-side reflection                       | automation | 4.6 | 3     |
| 10 | Role pinning by VM type (`VPS` / `LXC`)               | EdgeUno    | 4.3 | 4     |
| 8  | Tenant assignment by VM-name regex                    | EdgeUno    | 4.1 | 5     |
| 9  | `description`-field parsing (4 new overwrite flags)   | EdgeUno    | 4.2 | 6     |

Order rationale: defensive guards first (item #7, no schema
change), then leaf bootstrap-extensions (#6, #5), then the three
configurable enrichments (#10, #8, #9) in increasing scope.

**Schema changes.**

- Item #5: three new custom fields on `virtualization.VirtualMachine`
  (`proxmox_cloudinit_ipconfig0`, `proxmox_cloudinit_ssh_keys_hash`,
  `proxmox_cloudinit_ostype`) created by item #2's bootstrap pass.
  No new model column.
- Item #6: two new `extras.tags` rows added to item #2's bootstrap
  inventory. No new model column.
- Item #10: two new `ProxboxPluginSettings` columns
  (`default_role_qemu`, `default_role_lxc`), default blank.
- Item #8: one new `ProxmoxEndpoint` column (`tenant_regex`,
  blank).
- Item #9: four new flags on `ProxboxPluginSettings` and four
  matching tri-state columns on `ProxmoxEndpoint`
  (`overwrite_tenant_from_description`,
  `overwrite_contact_from_description`,
  `overwrite_main_ip_from_description`,
  `overwrite_ip_allocation_from_description`).

**Contract changes.**

- `OVERWRITE_FIELDS` / `OVERWRITE_FIELD_GROUPS` at
  `netbox_proxbox/constants.py:5,64`: four new entries (item #9),
  plus a new "Tenancy" group.
- `contracts/overwrite_flags.json` and the sibling manifest in
  `proxbox-api/contracts/overwrite_flags.json`: four new entries.
  The drift detector at `tests/test_overwrite_flags_contract.py`
  is the canary.
- SSE schema: no new frames.

**Dependencies.** v0.0.16 (items #1 and #2). Items #5, #6 cannot
land without #2; items #8, #9, #10 benefit from #1's drift-detect
helper for their write paths. Item #7 is independent and could ship
in v0.0.16 if reviewer bandwidth allows.

**Acceptance criteria.**

- Item #5: a synced VM that has `qemu_set_meta_args` cloud-init
  configured shows non-empty values in all three custom fields on
  the NetBox detail page.
- Item #6: every newly synced VM / LXC carries the appropriate
  `proxmox-{vm,lxc}-discovered` tag; a re-reconcile of an existing
  object does not re-apply (idempotency pin).
- Item #7: a Proxmox-reported `fe80::1%eth0` does not produce an
  `ipam.IPAddress` row; a `2001:db8::1%eth0` produces a row with
  address `2001:db8::1` (zone stripped).
- Item #8: a VM named `acme-web-01` with `tenant_regex=^([^-]+)-`
  on its endpoint lands with `tenant=acme` (slug lookup); no
  auto-create on miss.
- Item #9: each of the four flags, when off (default), leaves the
  corresponding NetBox field unchanged on existing records; when
  on, writes the parsed value through item #1's helper.
- Item #10: blank `default_role_qemu` / `default_role_lxc` (the
  default) leaves new VMs role-less; populated values that match a
  `dcim.DeviceRole.name` populate the `role` FK on creation only;
  populated values that do *not* match emit a one-line SSE warning
  frame at sync start and skip role assignment for the rest of the
  run.

**Risk callouts.**

- Item #9's description parser must reject malformed values
  silently — operator typos in the Proxmox description should
  *never* fail the run. Pin in a unit-test fixture covering at
  least: missing colon, trailing whitespace, multiple values per
  line, encoding edge cases.
- Item #10's "missing role → log + skip, do not crash" behaviour
  is the canonical replacement for upstream EdgeUno's
  `nb_cluster_type.DoesNotExist` swallow-and-continue antipattern
  (EdgeUno §5.8). A test must pin the difference: skip-with-log on
  miss, *not* swallow-with-pass.

### 5.3 v0.0.18 — Sync Auditability

**Theme.** Stale-record cleanup, collision handling, and dry-run
on a branch.

**Summary.** The release that lets operators audit and validate
sync behaviour. `delete_orphans` is the first time the plugin
deletes records on the operator's behalf, so it ships behind a
default-off flag in three explicit sub-PRs (stamp → sweep → flag).

**Items.**

| #  | Item                                                       | Source     | §   | Order |
|----|------------------------------------------------------------|------------|-----|-------|
| 11 | `latest_job` UUID stamp + `delete_orphans` (3 sub-PRs)     | EdgeUno    | 4.9 | 1     |
| 12 | Duplicate-VM-name `" (2)"` suffix + new SSE frame          | EdgeUno    | 4.8 | 2     |
| 13 | Optional NetBox Branching (`X-NetBox-Branch`) support      | automation | 4.2 | 3     |

Order rationale: item #11 is the largest piece of work and
foundational for the milestone's auditability theme; #12 is a
small SSE-schema change that benefits from #11 having shipped
first (the `duplicate_name_resolved` and `orphan_deleted` frames
touch the same renderer); #13 layers on once the write path is
stable.

**Schema changes.**

- Item #11 sub-PR (a): new custom field `proxbox_last_run_id` on
  every plugin-managed object kind, created by item #2's bootstrap.
  No new model column.
- Item #11 sub-PR (b): no schema change — the sweep code lands
  behind a default-off flag.
- Item #11 sub-PR (c): one new flag on `ProxboxPluginSettings`
  (`delete_orphans`) and one tri-state column on `ProxmoxEndpoint`.
- Item #12: no new model column; new SSE event variant.
- Item #13: one new field on `ProxboxPluginSettings`
  (`enable_netbox_branching`, default `False`).

**Contract changes.**

- `OVERWRITE_FIELDS` / `OVERWRITE_FIELD_GROUPS`: one new entry
  (item #11 sub-PR c), in a new "Cleanup" group or folded into
  "Overwrite". Manifests on both sides.
- SSE schema: two new event kinds — `duplicate_name_resolved`
  (item #12), `orphan_deleted` (item #11). Mirror at
  `netbox_proxbox/schemas/backend_proxy.py`; canary at
  `tests/test_sse_schema_mirror.py`.

**Dependencies.** v0.0.16 (items #1 and #2). Item #11's sub-PR (a)
depends on #2's bootstrap to own the `proxbox_last_run_id` custom-
field creation; sub-PR (b)'s sweep reuses #1's diff helper for
identity comparison. Item #13's `X-NetBox-Branch` header
installation depends on #1 because every write site must funnel
through the same `netbox-sdk` session.

**Acceptance criteria.**

- Item #11 sub-PR (a): every VM / IP / interface / storage /
  snapshot / backup / routine / replication touched in a run
  carries a `proxbox_last_run_id` custom-field value matching the
  run UUID. No deletion behaviour yet.
- Item #11 sub-PR (b): with the flag on, a Proxmox VM that was
  deleted between two syncs is removed from NetBox on the second
  sync; a sync that fails mid-stream does *not* trigger the sweep
  (only successful runs delete records — pin in a test).
- Item #11 sub-PR (c): default-off; an operator must explicitly
  flip the flag to opt in.
- Item #12: when two VMs across two clusters share a `name`, both
  records exist in NetBox; the second carries the `" (2)"` suffix
  and the SSE log shows a typed `duplicate_name_resolved` frame
  with both VM identities. Idempotent: re-running does not produce
  `" (3)"`.
- Item #13: with branching enabled and `branch_name=foo`, the
  backend's `netbox-sdk` session sends `X-NetBox-Branch: foo` for
  every request; on completion (success / failure / cancel) the
  header is cleared in `finally`. With the branching plugin
  absent, an SSE warning frame is emitted and the run continues
  against `main`.

**Risk callouts.**

- Item #11 is the first time the plugin deletes records on the
  operator's behalf. The release notes must spell this out loudly
  alongside the upgrade-time guidance for operators with hand-
  edited records. Default-off is non-negotiable.
- Item #13's `netbox-sdk` cache must include the branch name in
  the cache key. Two runs against two different branches that
  share a cache entry would cross-contaminate. Pin explicitly in
  the test suite.

### 5.4 v0.0.19 — Operations & Ergonomics

**Theme.** Operator quality-of-life: deployment artefacts,
schedulers, ergonomic CLI, plus the SSH-based hardware discovery
extension.

**Summary.** Three thin wrappers around v0.0.16's management
command, an optional backend refactor, and the SSH discovery
pipeline stage. The SSH piece is the heaviest item in the milestone;
it lands here because v0.0.18's auditability work needs to ship
first to reduce credential-surface risk on a production install.

**Items.**

| #  | Item                                                  | Source     | §    | Order |
|----|-------------------------------------------------------|------------|------|-------|
| 14 | One-shot `docker-compose-single-exec.yml`             | EdgeUno    | 4.6  | 1     |
| 15 | Standalone scheduler container (`PROXBOX_MODE`)       | EdgeUno    | 4.5  | 2     |
| 16 | `pxb sync run` CLI subcommand                         | EdgeUno    | 4.7  | 3     |
| 17 | Hardware discovery via SSH + `dmidecode` + `ethtool`  | automation | 4.3  | 4     |
| 18 | `ProxboxSession`-style backend refactor (optional)    | EdgeUno    | 4.10 | 5     |

Order rationale: docs-only first (item #14), then the new sidecar
image (item #15), then the `pxb` subcommand (item #16, also a thin
wrapper), then the SSH discovery pipeline stage (item #17, the
heavy one), then the optional refactor (item #18) which is purely
backend-internal and can be deferred to a later release without
blocking anything.

**Schema changes.**

- Item #17: two new encrypted fields on `ProxmoxEndpoint`
  (`ssh_username`, `ssh_private_key`) using the existing Fernet
  pattern; new flag on `ProxboxPluginSettings` and tri-state column
  on `ProxmoxEndpoint` (`discover_node_hardware`, default off).
- Items #14, #15, #16, #18: no schema changes.

**Contract changes.**

- `OVERWRITE_FIELDS` / `OVERWRITE_FIELD_GROUPS`: one new entry
  (item #17), in a new "Discovery" group or folded into
  "Overwrite". Manifests on both sides.
- SSE schema: three new event kinds for item #17 —
  `node_hardware_started`, `node_hardware_progress`,
  `node_hardware_done`. Plus the skip-and-continue variant
  `node_hardware_skipped` for `dmidecode`-absent nodes.
- New optional dependency in `proxbox-api/pyproject.toml`:
  `paramiko` (or `asyncssh`) under `[project.optional-dependencies]`.
  The pipeline stage imports it lazily; without the extra
  installed, the stage refuses to run with a clear SSE error frame.

**Dependencies.**

- Items #14, #15, #16: depend on item #4 (v0.0.16 management
  command).
- Item #17: depends on items #1 and #2 (drift-detect helper +
  bootstrap pass) for its `dcim.Device` enrichment writes.
- Item #18: no dependencies; it is an internal refactor that
  collapses an existing `(client, endpoint, settings)` triple into
  a thin dataclass. AST contract tests in `proxbox-api/tests/`
  catch any signature drift.

**Acceptance criteria.**

- Item #14: `docker compose -f docs/installation/docker-compose-
  single-exec.yml run --rm netbox` runs one full sync end-to-end
  and exits zero on success.
- Item #15: with `PROXBOX_MODE=interval` and a 60-second cadence,
  the scheduler container triggers exactly one
  `proxbox_sync --wait` per minute. With `PROXBOX_MODE=off`, the
  container idles.
- Item #16: `pxb sync run --enqueue --endpoint <name>` succeeds
  whether the operator's working directory is the NetBox root, the
  plugin root, or anywhere else under `/opt/netbox`. AST contract
  test in `tests/test_cli_contracts.py`.
- Item #17: with the flag on and SSH credentials populated, a
  cluster sync produces `dcim.Device.serial`, manufacturer FK, and
  per-`dcim.Interface` link-speed values. With the flag off, the
  pipeline stage is skipped (no SSH attempted, no SSE frames).
  With `dmidecode` absent on a node, a `node_hardware_skipped`
  frame is emitted and the run continues.
- Item #18: AST contract test pins the new
  `ProxmoxSession`-style dataclass shape; signature drift fails CI.
  Behaviour-only — no observable change in sync output.

**Risk callouts.**

- Item #17 widens the credential surface area on every endpoint
  that opts in. The release notes must call this out explicitly,
  paired with the recommendation to use a dedicated SSH key per
  endpoint (not the operator's personal key).
- Item #15's `croniter` dependency lands as an optional extra in
  `pyproject.toml` only — the plugin's core install footprint must
  not grow.

### 5.5 v0.0.20 — Operational Verbs (carve-out)

**Theme.** Per-VM start / stop / snapshot / migrate as REST
endpoints inside `proxbox-api`, gated and audited.

**Summary.** The single biggest gap upstream highlights against
this repo: an operator with a NetBox tab open on a Proxbox-synced
VM cannot act on it without context-switching to the Proxmox UI.
This release closes that gap as REST endpoints inside `proxbox-api`
called by NetBox-side per-VM action buttons via the existing
`template_extensions` — **not** via NetBox event rules + webhooks
(see §5.7 / §5.8 of automation-VALID-TO-IMPLEMENT for the
non-imports rejection of the upstream dispatch shape).

**Items.**

| #  | Item                                                 | Source     | §   | Order |
|----|------------------------------------------------------|------------|-----|-------|
| 19 | Strictly opt-in operational verbs as REST endpoints  | automation | 4.7 | 1     |

Item #19 is the only item in this milestone, but it ships as a
strict sequence of seven PRs, one verb per PR, with the design doc
PR landing first:

1. **Design doc PR.** Pins permission model, cancellation
   semantics (start cannot be cancelled mid-flight; migrate can —
   document each verb), idempotency-token shape, audit-log
   payload, and the per-endpoint `allow_writes` default (off).
2. **Gate PR.** New `ProxmoxEndpoint.allow_writes` boolean (default
   `False`); migration with `IF NOT EXISTS`. New permission
   `core.run_proxmox_action` registered via
   `ContentTypePermissionRequiredMixin`. No verb routes yet.
3. **`POST /proxmox/qemu/{vmid}/start` PR** + LXC sibling. Includes
   `Idempotency-Key` header support and `extras.journal_entries`
   audit-log write.
4. **`POST /proxmox/qemu/{vmid}/stop` PR** + LXC sibling.
5. **`POST /proxmox/qemu/{vmid}/snapshot` PR** + LXC sibling.
   Body: snapshot name.
6. **`POST /proxmox/qemu/{vmid}/migrate` PR** + LXC sibling.
   Body: target node. Long-running — returns Proxmox task ID
   immediately; progress through dedicated SSE channel.
7. **Plugin-side button wiring PR.** Adds per-VM buttons via
   `template_extensions`, each wrapped in a confirmation modal
   with the VM identity displayed. Until this PR, the backend
   routes are reachable by external automation but invisible in
   the NetBox UI.

**Schema changes.**

- New column `ProxmoxEndpoint.allow_writes` (boolean, default
  `False`). One migration with `IF NOT EXISTS`.
- New permission `core.run_proxmox_action` (registered through
  the existing operational-endpoint pattern documented in
  [`netbox_proxbox/views/proxbox_access.py`](../netbox_proxbox/views/proxbox_access.py)).

**Contract changes.**

- `OVERWRITE_FIELDS` / manifests: no changes (this is a writes-side
  feature, not an overwrite flag).
- SSE schema: new progress channel for long-running verbs
  (item #19 PR 6 — `migrate`). Mirror at
  `netbox_proxbox/schemas/backend_proxy.py`; canary at
  `tests/test_sse_schema_mirror.py`.

**Dependencies.** v0.0.16 (items #1 and #2 — drift-detect helper
for the journal-entry write, bootstrap for the permission's
content-type registration), plus the design doc PR landing
*before* any code PR.

**Acceptance criteria.**

- A read-only NetBox user (`view` on `VirtualMachine`, no
  `core.run_proxmox_action`) sees the VM detail page but no
  action buttons.
- A user with `core.run_proxmox_action` sees the buttons, can
  click them, and is required to confirm the VM identity in the
  modal before the POST fires.
- With `ProxmoxEndpoint.allow_writes=False` on the target VM's
  endpoint, the backend route returns `403` with a clear message;
  the modal surfaces the error.
- Two `start` POSTs with the same `Idempotency-Key` inside a
  60-second window resolve to a single Proxmox call.
- Every verb call writes a journal-entry row on the linked VM
  recording the verb, the actor, the result, and the Proxmox task
  ID.
- The next sync after a verb call reflects the new state — there
  is no race between a running verb and a running sync, because
  Proxmox is the source of truth.

**Risk callouts.**

- This is the closest the roadmap comes to challenging the
  observer stance. Every PR must repeat the security disclaimer:
  enabling `allow_writes` on an endpoint widens the trust
  boundary; `core.run_proxmox_action` should be restricted to a
  small operator group.
- The design doc PR is non-negotiable. Skipping it and landing
  verbs ad-hoc would mean writing the permission, idempotency,
  and audit-log story incrementally, which is the antipattern
  upstream's 17-event-rule explosion exemplifies (see §5.8 of
  automation-VALID-TO-IMPLEMENT).
- Operators who *want* the upstream event-rule + webhook shape
  for their existing automation can keep using
  `netbox-proxmox-automation` for that — the two systems coexist
  (§10 of `PROXBOX-AND-PROXMOX-AUTOMATION.md`).

---

## 6. Critical Path

If review bandwidth is constrained and only one item ships per
quarter, the roadmap's load-bearing seven items, in order:

1. **automation §4.1 `createOrUpdate` (item #1).** Foundation for
   every other backend-write entry. Shipping it reduces ChangeLog
   spam immediately and gives every later item its idempotency
   primitive.
2. **automation §4.5 bootstrap pass (item #2).** Makes fresh
   installs work without operator NetBox prep, and gives items #5,
   #6, and #11 (sub-PR a) a place to land their custom-field
   creations.
3. **automation §4.4 `dcim.mac_addresses` linkage (item #3).** The
   only item that can be promoted to "must-ship" purely on NetBox
   compatibility grounds. Spot-check first; rewrite only if the
   spot-check shows the legacy string field is still in use.
4. **EdgeUno §4.4 management command (item #4).** Zero schema
   risk, useful immediately, and unblocks the v0.0.19 deployment-
   artefact items.
5. **EdgeUno §4.9 `latest_job` + `delete_orphans` (item #11).**
   The audit story. Closes the "Proxmox VMs deleted from Proxmox
   linger forever in NetBox" gap, on operator-explicit opt-in.
6. **EdgeUno §4.1 tenant regex (item #8).** The highest-impact
   observer enrichment for multi-tenant ISPs and hosting
   providers. Single-field migration; one regex compile per run.
7. **automation §4.7 operational verbs (item #19).** Last. The
   work that earns this repo a per-VM action surface inside
   NetBox, gated behind the design doc PR and the `allow_writes`
   permission. Each verb is a separate PR.

This sequence keeps every milestone's foundational primitive
ahead of its leaf consumers, ensures NetBox 4.6 compat work lands
early, and pins operational verbs at the end where the design-doc
gate is strictest.

---

## 7. Combined Non-Imports Index

The two source docs together reject 21 ideas. Several reject the
same idea from different angles. This table indexes each
non-import; the Citation Root column points to the policy or
contract that authoritatively rejects it. Read the source-doc
section for the per-item justification.

| Title (short)                                                  | EdgeUno § | automation § | Citation root                                                                                  |
|----------------------------------------------------------------|-----------|--------------|------------------------------------------------------------------------------------------------|
| Web-triggered synchronous sync (held gunicorn worker)           | 5.6       | 5.1          | [`CLAUDE.md`](../CLAUDE.md) "Backend integration notes" — RQ + SSE contract                    |
| Plaintext credentials anywhere on disk                          | 5.1       | 5.5          | [`CLAUDE.md`](../CLAUDE.md) "Plugin settings and configuration" — Fernet store                 |
| File-based YAML / JSON config for tunables                      | 5.1       | 5.2          | [`CLAUDE.md`](../CLAUDE.md) "Plugin settings and configuration" — `ProxboxPluginSettings`      |
| `ssl_verify=False` / `verify_ssl=False` hardcode                | 5.2       | 5.3          | [`docs/release-notes/version-0.0.15.md`](../docs/release-notes/version-0.0.15.md) §"#352"     |
| `print()`-based logging                                         | 5.3       | —            | SSE schema contract at `tests/test_sse_schema_mirror.py`                                       |
| `eval()` in templatetags                                        | 5.4       | —            | [`netbox_proxbox/templatetags/CLAUDE.md`](../netbox_proxbox/templatetags/CLAUDE.md)            |
| `ChangeLoggedModel` instead of `NetBoxModel`                    | 5.5       | —            | [`CLAUDE.md`](../CLAUDE.md) "Framework stack preference"                                       |
| Hardcoded example NetBox token in shipped config                | 5.7       | —            | [`CLAUDE.md`](../CLAUDE.md) "Security and permissions"                                         |
| `nb_cluster_type.DoesNotExist` swallow-and-continue             | 5.8       | —            | `services/_endpoint_errors.py` operator-actionable error path                                  |
| Duplicate sync engines (v1 + v2 coexisting)                     | 5.9       | —            | Single backend invariant: `proxbox-api`                                                        |
| Version mismatch between `setup.py`/`pyproject.toml` / config   | 5.10      | —            | `tests/test_version.py`                                                                        |
| MB÷1000 vs ÷1024 unit drift                                     | —         | 5.4          | Bug, not a feature. Conversions in one place.                                                  |
| No test suite at all                                            | —         | 5.6          | `tests/test_overwrite_flags_contract.py`, `tests/test_sse_schema_mirror.py`                    |
| AWX / Tower / AAP dependency for any operational verb           | —         | 5.7          | This roadmap §5.5 — verbs ship as REST endpoints in `proxbox-api`                              |
| 17-event-rule + 17-webhook setup-time explosion                 | —         | 5.8          | This roadmap §5.5 — verbs ship as `template_extensions` buttons + REST                         |
| CalVer (`2025.11.01`) versioning                                | —         | 5.9          | `tests/test_version.py` pins SemVer                                                            |
| BIND9 / gss-tsig DNS update path                                | —         | 5.10         | 0.0.15 `dns_name` write covers the use case; DNS-server-side mgmt belongs in `netbox-plugin-dns` |
| Custom-field group renaming (`Proxmox (common)` etc.)           | —         | 5.11         | Cosmetic; would churn every existing install                                                   |

Two non-imports — "synchronous sync" and "plaintext credentials"
— are rejected by *both* source docs from different angles, which
makes them the strongest negative invariants for this repo. Any
future contribution that re-opens either is a regression.

---

## 8. Cross-References

- [`EDGEUNO-FORK-VALID-TO-IMPLEMENT.md`](./EDGEUNO-FORK-VALID-TO-IMPLEMENT.md)
  — source action list for items #4, #8, #9, #10, #11, #12, #14,
  #15, #16, #18.
- [`PROXMOX-AUTOMATION-VALID-TO-IMPLEMENT.md`](./PROXMOX-AUTOMATION-VALID-TO-IMPLEMENT.md)
  — source action list for items #1, #2, #3, #5, #6, #7, #13,
  #17, #19.
- [`EDGEUNO-NETBOX-PROXMOX.md`](./EDGEUNO-NETBOX-PROXMOX.md) —
  standalone deep-dive on the EdgeUno fork; the canonical source
  for "the EdgeUno fork does X" claims behind every EdgeUno-§
  citation.
- [`NETBOX-PROXMOX-AUTOMATION.md`](./NETBOX-PROXMOX-AUTOMATION.md)
  — standalone deep-dive on the NetBox Labs project; the
  canonical source for "the upstream does X" claims behind every
  automation-§ citation.
- [`PROXBOX-FORK-EDGEUNO.md`](./PROXBOX-FORK-EDGEUNO.md) —
  side-by-side comparison this repo ↔ EdgeUno fork.
- [`PROXBOX-AND-PROXMOX-AUTOMATION.md`](./PROXBOX-AND-PROXMOX-AUTOMATION.md)
  — side-by-side comparison this repo ↔ `netbox-proxmox-automation`.
- [`../CLAUDE.md`](../CLAUDE.md) — policy authority cited
  throughout §3 (re-ranking rules), §5 (acceptance criteria
  rooted in pre-commit checklist + framework stack preference +
  security model), and §7 (non-imports).
- [`../docs/release-notes/version-0.0.15.md`](../docs/release-notes/version-0.0.15.md)
  — canonical "new opt-in flag + migration + form / serializer /
  table surface + `_build_base_query_params` query-string
  forwarding + backend handler + AST contract test" template
  every milestone with a new flag follows.
- [`../docs/roadmap.md`](../docs/roadmap.md) — this document is
  the input to that roadmap planning session.
- `../netbox_proxbox/__init__.py:124-125` — `min_version="4.5.8"`,
  `max_version="4.6.99"`. Pinned by §3.2 rule (1) and by item #3.
- `../netbox_proxbox/constants.py:5,64` — `OVERWRITE_FIELD_GROUPS`
  and `OVERWRITE_FIELDS`, the canonical 23-flag set every new
  flag in v0.0.17 / v0.0.18 / v0.0.19 must extend.
- `../contracts/overwrite_flags.json` — manifest mirrored against
  the sibling in `proxbox-api/contracts/overwrite_flags.json`;
  pinned by `../tests/test_overwrite_flags_contract.py`. Canary
  for every overwrite-flag-shaped milestone item.
- `../contracts/proxbox_api_sse_schema.json` — SSE frame schema
  referenced by milestone items adding new SSE event kinds (#1,
  #2, #11, #12, #17, #19); pinned by
  `../tests/test_sse_schema_mirror.py`.
- `../netbox_proxbox/migrations/0037_pluginsettings_runtime_tunables.py`,
  `../netbox_proxbox/migrations/0038_fastapiendpoint_use_https.py`,
  `../netbox_proxbox/migrations/0039_pluginsettings_overwrite_ip_address_dns_name.py`
  — three canonical "production-safe additive schema change"
  migrations every milestone schema-change bullet references.
- `../netbox_proxbox/management/commands/proxbox_fix_tokens.py`
  — shape reference for item #4's new `proxbox_sync` command.
- `../netbox_proxbox/views/proxbox_access.py` — existing
  `ContentTypePermissionRequiredMixin` permission registrations;
  shape reference for item #19's `core.run_proxmox_action`.
- `../proxbox_cli/__init__.py` — Typer app entry point for item
  #16's `pxb sync run` subcommand.
