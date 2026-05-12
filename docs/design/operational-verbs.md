# Operational Verbs — Design Contract

Tracking: [issue #376](https://github.com/emersonfelipesp/netbox-proxbox/issues/376).
Source specs: [`reference/IMPLEMENTATION-ROADMAP.md`](../../reference/IMPLEMENTATION-ROADMAP.md)
§5.5 and
[`reference/PROXMOX-AUTOMATION-VALID-TO-IMPLEMENT.md`](../../reference/PROXMOX-AUTOMATION-VALID-TO-IMPLEMENT.md)
§4.7.

This document pins the contract for the operational-verbs carve-out
**before any code lands**. Once approved it is the single source of
truth for sub-PRs B–G. Any later deviation requires a new design-doc
PR; verb PRs that deviate without amending this document must be
rejected on review.

---

## 1. Scope

Four explicit, operator-initiated, idempotent Proxmox-mutating verbs
exposed as REST endpoints on `proxbox-api` and surfaced as per-VM
action buttons in the NetBox plugin UI via `template_extensions`:

| Verb | QEMU endpoint | LXC sibling |
|---|---|---|
| `start` | `POST /proxmox/qemu/{vmid}/start` | `POST /proxmox/lxc/{vmid}/start` |
| `stop` | `POST /proxmox/qemu/{vmid}/stop` | `POST /proxmox/lxc/{vmid}/stop` |
| `snapshot` | `POST /proxmox/qemu/{vmid}/snapshot` | `POST /proxmox/lxc/{vmid}/snapshot` |
| `migrate` | `POST /proxmox/qemu/{vmid}/migrate` | `POST /proxmox/lxc/{vmid}/migrate` |

Out of scope for this carve-out: clone, destroy, resize, console
attach, template conversion, backup-now. They follow the same shape
and can be added later under the same contract; they are not part of
the v0.0.20 milestone.

Also out of scope: importing the upstream `netbox-proxmox-automation`
event-rule + webhook architecture. §4.7 and §5.7/§5.8 of the source
docs reject that shape; this design does not revisit that decision.

---

## 2. Trust boundary and gating

The plugin's existing stance is **observer**: Proxmox is the source of
truth, NetBox mirrors it. Operational verbs are the first feature that
mutates Proxmox state from NetBox. The trust boundary is widened
explicitly and per-endpoint, never globally.

### 2.1 Gate field

A new boolean column on `ProxmoxEndpoint`:

```python
# netbox_proxbox/models/proxmox_endpoint.py
allow_writes = models.BooleanField(
    default=False,
    verbose_name=_("Allow Proxmox-side writes"),
    help_text=_(
        "When enabled, operational verbs (start, stop, snapshot, migrate) "
        "may be dispatched against this endpoint. Default off. Enabling "
        "this widens the trust boundary; restrict the new "
        "core.run_proxmox_action permission to a small operator group."
    ),
)
```

Migration ships as a single `IF NOT EXISTS` column add. Per CLAUDE.md,
the canonical shape is `SeparateDatabaseAndState` with
`ADD COLUMN IF NOT EXISTS` — see
`netbox_proxbox/migrations/0037_pluginsettings_runtime_tunables.py`
for the template.

### 2.2 Why per-endpoint, not global

`ProxboxPluginSettings.operational_verbs_enabled` (the shape proposed
in the original #376 body) would unlock every cluster at once. With
per-endpoint gating, an operator can:

- Enable writes on a lab cluster while production stays read-only.
- Disable writes on a single endpoint during a scheduled freeze
  without disabling the feature globally.
- Audit which endpoints have ever had writes enabled via NetBox's
  `extras.object-changes` log on `ProxmoxEndpoint`.

### 2.3 Enforcement points

Every verb request is gated at **three** layers, in this order:

1. **Plugin UI** — the four buttons are hidden if the user lacks
   `core.run_proxmox_action`. Buttons render disabled with a tooltip
   ("This endpoint does not allow writes") if the VM's endpoint has
   `allow_writes=False`.
2. **NetBox plugin endpoint** — the backend-proxy view that forwards
   the POST to `proxbox-api` checks `core.run_proxmox_action` (via
   `ContentTypePermissionRequiredMixin`) and rejects with 403 if
   the user does not hold it.
3. **proxbox-api route** — the route handler looks up the target
   VM's owning `ProxmoxEndpoint` (via the existing endpoint registry)
   and rejects with 403 if `allow_writes=False`. The 403 response
   body includes a structured `reason` field
   (`"endpoint_writes_disabled"`) so the UI can render an actionable
   error.

The third layer is the load-bearing one. A future external automation
caller that bypasses the plugin must still pass it; the plugin UI
checks are belt-and-braces.

---

## 3. Permission model

One permission, not four. The codename is
**`core.run_proxmox_action`** — content-type-scoped on
`virtualization.virtualmachine` and registered via the existing
`ContentTypePermissionRequiredMixin` pattern in
[`netbox_proxbox/views/proxbox_access.py`](../../netbox_proxbox/views/proxbox_access.py).

### 3.1 Why one, not per-verb

An operator who can `start` a VM in production almost always also
needs to `stop` and `snapshot` it; the per-verb split adds permission
toggles without adding meaningful access control. The verbs share a
trust boundary (they all mutate Proxmox state); they share a single
permission.

If a future deployment needs per-verb granularity it can be added
without breaking the contract — add the new codenames alongside
`run_proxmox_action`, and grant `run_proxmox_action` by default to
keep existing operator groups working.

### 3.2 Permission helper

A new function in `netbox_proxbox/views/proxbox_access.py`:

```python
def permission_run_proxmox_action() -> str:
    return "core.run_proxmox_action"
```

Used by both the verb-button rendering in `template_content.py` and
the backend-proxy POST views.

### 3.3 Read-only NetBox users

A user with only `virtualization.view_virtualmachine` (no
`run_proxmox_action`):

- Sees the VM detail page exactly as today.
- Does not see the four action buttons.
- If they hit the backend-proxy POST URL directly, receives a 403
  with `reason: "permission_denied"`.

---

## 4. Idempotency

Every verb route accepts an optional `Idempotency-Key` header
following the [draft IETF Idempotency-Key for HTTP](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)
semantics:

- **Window:** 60 seconds, sliding from first observed POST.
- **Key scope:** per `(endpoint_id, verb, vmid)` tuple. The same key
  reused across different VMs / verbs does not collide.
- **Resolution:** the second POST within the window returns the
  cached response of the first; the Proxmox API is called once.
- **Storage:** in-memory dict in proxbox-api keyed by
  `(endpoint_id, verb, vmid, key)`. Entries are cleared by a 60-second
  TTL; no SQLite write. Process restart clears the dict — acceptable
  for the 60-second window.

### 4.1 Plugin-side default

When the operator clicks a verb button, the plugin generates a
`uuid4()` and sends it as `Idempotency-Key`. This protects against
double-click in the confirmation modal.

### 4.2 State-based no-op (complementary)

In addition to key-based idempotency, every verb performs a pre-flight
state check:

- `start` against a running VM: no-op, returns 200 with
  `result: "already_running"` and no Proxmox call.
- `stop` against a stopped VM: no-op, returns 200 with
  `result: "already_stopped"`.
- `snapshot` is always dispatched (operator-initiated; the operator
  knows they are creating one).
- `migrate` against a VM already on the target node: no-op,
  returns 200 with `result: "already_on_target_node"`.

State-based no-op runs **before** the Idempotency-Key check is
recorded. A double-clicked `start` on an already-running VM returns
`already_running` both times without consuming the key.

---

## 5. Cancellation semantics

Per-verb:

| Verb | Cancellable mid-flight? | Notes |
|---|---|---|
| `start` | **No.** | The Proxmox API call returns within seconds. No async progress. |
| `stop` | **No.** | Same as start. A "stop" issued during a "shutdown" can be retried; that is a Proxmox-side concern. |
| `snapshot` | **No.** | Snapshot creation is a Proxmox-side atomic operation. |
| `migrate` | **Yes.** | Long-running. The operator may cancel via a separate `DELETE /proxmox/qemu/{vmid}/migrate/{task_upid}` endpoint, which proxies to the Proxmox `nodes/{node}/tasks/{upid}` DELETE. Cancellation is best-effort: Proxmox decides whether the in-flight task can be torn down. |

The migrate cancel endpoint is **part of sub-PR F** (migrate verb),
not a separate PR, since the migrate verb is meaningless without it.

---

## 6. Audit trail

Every verb invocation — successful, failed, or no-op — writes a
**journal entry on the linked VirtualMachine** via
`POST /api/extras/journal-entries/`. The journal entry is the
operator-visible audit trail on the VM detail page; it is not a
`core.Job` row (that model is for background-task state, not user
actions).

### 6.1 Payload shape

```json
{
    "assigned_object_type": "virtualization.virtualmachine",
    "assigned_object_id": <netbox_vm_pk>,
    "kind": "info",
    "comments": "Proxbox operational verb dispatched.\n\n- verb: start\n- actor: alice@netbox\n- result: ok\n- proxmox_task_upid: UPID:pve-node-01:00012F4A:00...\n- idempotency_key: 7b3c9f4a-...\n- endpoint: my-prod-cluster (id=3)\n- dispatched_at: 2026-05-12T18:42:11Z"
}
```

The `comments` field is a structured Markdown block, not free text.
The bullet keys are stable and machine-parseable; release notes
document the parse grammar so downstream automation can rely on it.

### 6.2 Failure-mode invariant

If the Proxmox call fails, the journal entry MUST still be written
(with `kind: "warning"` and `result: "failed"`). Failure to audit is a
P0 bug — pin in tests with a simulated Proxmox 500 response.

If the journal-entry POST itself fails (NetBox unreachable), the
verb route returns 500 with `reason: "audit_write_failed"` and the
Proxmox state may have been mutated. This is the worst-case path; it
is acceptable because (a) Proxmox state is observable on the next
sync, (b) the operator sees a clear error, (c) NetBox-down is a
broader incident than a missed audit row.

### 6.3 Idempotent re-issue

A second POST with the same `Idempotency-Key` does not write a second
journal entry. The cached response (§4) carries the original entry's
URL in a `journal_entry_url` field.

---

## 7. SSE channel

Per §5.5: **only `migrate` streams SSE.** The other three verbs
return their result synchronously on the POST response.

### 7.1 Migrate SSE

The migrate POST returns 202 with `task_upid` and an
`sse_url` in the body. The client opens
`GET /proxmox/qemu/{vmid}/migrate/{task_upid}/stream` to receive
progress frames.

New event types added to `netbox_proxbox/schemas/backend_proxy.py::SseEventType`:

| Event | When emitted |
|---|---|
| `migrate_dispatched` | First frame; mirrors the 202 POST body. |
| `migrate_progress` | Repeating; carries the Proxmox task `progress` percentage and `phase` string. |
| `migrate_succeeded` | Final frame on success. |
| `migrate_failed` | Final frame on failure; carries the Proxmox error chain. |

These are migrate-specific names, not the original
`verb_dispatched`/`verb_succeeded`/`verb_failed` triple proposed in
the issue body. The other three verbs do not need an SSE channel; a
shared family of event names would be premature abstraction.

### 7.2 Schema mirror

The four new event types are added to
`contracts/proxbox_api_sse_schema.json`'s `StreamMessageType` enum
in the same commit as the `backend_proxy.py` change. The
`tests/test_sse_schema_mirror.py` canary enforces the mirror; the
migrate PR (sub-PR F) MUST pass this test before merge.

### 7.3 Non-migrate response shape

`start` / `stop` / `snapshot` return 200 with:

```json
{
    "verb": "start",
    "vmid": 101,
    "vm_type": "qemu",
    "endpoint_id": 3,
    "result": "ok",
    "proxmox_task_upid": "UPID:pve-node-01:00012F4A:...",
    "journal_entry_url": "/api/extras/journal-entries/789/",
    "dispatched_at": "2026-05-12T18:42:11Z"
}
```

A no-op (already-running / already-stopped) returns the same shape
with `result: "already_running"` etc. and no `proxmox_task_upid`.

---

## 8. URL surface and module layout

### 8.1 proxbox-api

New module: `proxbox_api/routes/proxmox_actions.py`. Registered in
`proxbox_api/app/factory.py` alongside the other `routes/proxmox/*`
routers, prefix `/proxmox`. The module exposes:

```
POST /proxmox/qemu/{vmid}/start
POST /proxmox/lxc/{vmid}/start
POST /proxmox/qemu/{vmid}/stop
POST /proxmox/lxc/{vmid}/stop
POST /proxmox/qemu/{vmid}/snapshot
POST /proxmox/lxc/{vmid}/snapshot
POST /proxmox/qemu/{vmid}/migrate
POST /proxmox/lxc/{vmid}/migrate
DELETE /proxmox/qemu/{vmid}/migrate/{task_upid}
DELETE /proxmox/lxc/{vmid}/migrate/{task_upid}
GET  /proxmox/qemu/{vmid}/migrate/{task_upid}/stream
GET  /proxmox/lxc/{vmid}/migrate/{task_upid}/stream
```

The QEMU and LXC variants share a single handler internally,
parameterised by `vm_type`.

### 8.2 New Proxmox-SDK helpers

Added to `proxbox_api/services/proxmox_helpers.py` with the existing
`@_dual_mode` async pattern:

| Helper | Wraps |
|---|---|
| `start_vm(session, node, vm_type, vmid)` | `POST nodes/{node}/{vm_type}/{vmid}/status/start` |
| `stop_vm(session, node, vm_type, vmid)` | `POST nodes/{node}/{vm_type}/{vmid}/status/stop` |
| `create_vm_snapshot(session, node, vm_type, vmid, snapname, description)` | `POST nodes/{node}/{vm_type}/{vmid}/snapshot` |
| `migrate_vm(session, node, vm_type, vmid, target, online)` | `POST nodes/{node}/{vm_type}/{vmid}/migrate` |
| `migrate_preflight(session, node, vm_type, vmid)` | `GET nodes/{node}/{vm_type}/{vmid}/migrate` |
| `get_vm_status(session, node, vm_type, vmid)` | `GET nodes/{node}/{vm_type}/{vmid}/status/current` (used for state-based no-op) |
| `cancel_task(session, node, upid)` | `DELETE nodes/{node}/tasks/{upid}` |
| `get_task_status(session, node, upid)` | already exists as `get_node_task_status` |

All helpers raise `ProxmoxAPIError` on `ProxmoxTimeoutError` /
`ProxmoxConnectionError` per the existing convention.

### 8.3 New NetBox-REST helper

Added to `proxbox_api/netbox_rest.py`:

```python
async def write_journal_entry(
    session: NetBoxSession,
    *,
    assigned_object_type: str,
    assigned_object_id: int,
    kind: Literal["info", "success", "warning", "danger"],
    comments: str,
) -> dict:
    """POST to /api/extras/journal-entries/. Returns the created entry."""
```

Used by every verb route.

### 8.4 Plugin-side backend-proxy

New view in `netbox_proxbox/views/operational.py` (one per verb,
sharing a base class). Each view:

1. Checks `core.run_proxmox_action` via
   `ContentTypePermissionRequiredMixin`.
2. Resolves the VM's `proxmox_endpoint` (via the existing custom
   field on `VirtualMachine`).
3. Generates an `Idempotency-Key` if the request did not carry one.
4. POSTs to the matching proxbox-api route through the existing
   backend-proxy helper.
5. Surfaces the response (or error) as an HTMX response that the
   confirmation modal renders.

---

## 9. Migrate pre-flight

Before dispatching a migrate, the route handler calls
`migrate_preflight(session, node, vm_type, vmid)` which wraps the
Proxmox `GET nodes/{node}/qemu/{vmid}/migrate` endpoint. The response
returns:

- `allowed_nodes` — list of node names the VM can move to.
- `local_disks` — local-only disks blocking online migrate.
- `local_resources` — local resources (pci-passthrough, etc.).
- `running` — current VM running state.

The route rejects with **400** (not 500) if:

- `target` not in `allowed_nodes` — `reason: "target_not_allowed"`.
- `online=True` and `local_disks` is non-empty —
  `reason: "local_disks_block_online_migrate"`.
- `online=True` and `local_resources` is non-empty —
  `reason: "local_resources_block_online_migrate"`.

The 400 response body includes the full preflight payload in a
`preflight` field so the UI can render the reason chain.

---

## 10. Acceptance criteria (pinned)

These are the verifiable conditions for "the carve-out is shipped".
Each verb PR (sub-PRs C–F) carries its own subset; the full set is
the merge gate on sub-PR G.

1. A read-only NetBox user (`virtualization.view_virtualmachine`, no
   `core.run_proxmox_action`) sees the VM detail page exactly as
   today; no action buttons appear.
2. A user with `core.run_proxmox_action` sees four buttons; clicking
   any button opens a confirmation modal that displays the VM
   identity (`name`, `vmid`, `endpoint`) before the POST fires.
3. With `ProxmoxEndpoint.allow_writes=False` on the VM's endpoint,
   the proxbox-api route returns 403 with
   `reason: "endpoint_writes_disabled"`; the modal surfaces the
   error.
4. Two `start` POSTs with the same `Idempotency-Key` within 60 s
   resolve to a single Proxmox call. Pin in tests.
5. Every successful verb invocation writes exactly one journal entry
   on the linked VM with the §6.1 payload shape. Pin in tests.
6. A simulated Proxmox 500 still writes a journal entry (`kind:
   "warning"`, `result: "failed"`). Pin in tests.
7. `start` against an already-running VM returns `result:
   "already_running"` with no Proxmox call (verify via mock-server
   call counter). Same for `stop`/`already_stopped`. Pin in tests.
8. `migrate` to a non-existent or offline target node returns 400
   with `reason: "target_not_allowed"` and the full preflight payload.
   Pin in tests.
9. The next sync after a verb call reflects the new state — no
   verb-vs-sync race; pin via an end-to-end test on the
   `proxmox-mock` HTTP service.
10. `tests/test_sse_schema_mirror.py` passes after sub-PR F adds the
    four migrate event types to `contracts/proxbox_api_sse_schema.json`.

---

## 11. Sub-PR sequence

The seven sub-PRs ship in strict order. Each is a separate review
surface; do not bundle.

| Sub-PR | Scope | Lands |
|---|---|---|
| **A** | This design doc | netbox-proxbox `feat/issue-376-design-doc` → v0.0.15 |
| **B** | `ProxmoxEndpoint.allow_writes` + `run_proxmox_action` permission + stubbed routes returning 403 | both repos |
| **C** | `start` verb (qemu + lxc) | both repos |
| **D** | `stop` verb (qemu + lxc) | both repos |
| **E** | `snapshot` verb (qemu + lxc) | both repos |
| **F** | `migrate` verb (qemu + lxc) + SSE + cancel + preflight | both repos |
| **G** | Plugin-side button wiring (`template_extensions`) + Playwright e2e | netbox-proxbox |

Sub-PRs B–F each ship their own permission test + idempotency test +
journal-entry test + state-based no-op test (where applicable).
Sub-PR G ships the Playwright end-to-end test exercising all four
verbs through the UI.

---

## 12. Dependencies

Per §5.5 the verbs depend on:

- v0.0.16 item #1 (drift-detect helper) — the journal-entry write
  uses the same diff semantics the drift-detect helper introduces.
- v0.0.16 item #2 (NetBox-side bootstrap) — the
  `core.run_proxmox_action` permission's content-type registration
  uses the bootstrap pass.
- This design doc (sub-PR A) — non-negotiable per §5.5.

#367 (run-UUID stamp, v0.0.18 item #11) is **not** in the dependency
chain. It is a useful correlation primitive that the verb work can
adopt if it ships first, but it is not blocking.

---

## 13. Risks and open questions

- **Trust boundary.** Per-endpoint gating + content-type permission +
  confirmation modal + journal-entry audit is the four-layer
  defence. The risk is operator misconfiguration (enabling
  `allow_writes` on a production endpoint without restricting
  `run_proxmox_action`). Mitigation: the migration that adds
  `allow_writes` ships with a release-note security disclaimer; the
  field's `help_text` repeats the warning.
- **Partial-success race.** Proxmox call returns success but the
  response is lost in transit. The idempotency key plus the next
  sync's reconciliation closes the loop: retry is safe, and the
  observer pass corrects the NetBox-side view. Pin in tests via a
  simulated transport failure.
- **Snapshot proliferation.** Repeated `snapshot` clicks create one
  snapshot per click. The verb takes an optional `name` parameter
  defaulting to `proxbox-{idempotency_key_prefix}`. Documented in
  the release note; cleanup is Proxmox's retention concern.
- **Migrate complexity.** The most-complex verb. Pre-flight
  validation, dedicated SSE channel, cancel endpoint, target-node
  validation, online/offline distinction. The migrate sub-PR (F) is
  expected to be the largest of the verb PRs.
- **External automation callers.** The routes are reachable by any
  caller with an `X-Proxbox-API-Key` once `allow_writes` is on. The
  routes do not check NetBox permissions directly (the plugin does).
  An external caller bypasses the NetBox permission layer. This is
  documented as a known property of the API surface; restrict the
  API key to the same operator group that holds
  `run_proxmox_action`.

---

## 14. Non-goals

This carve-out does not:

- Invert the observer stance for any field Proxmox owns.
- Add NetBox `extras.event_rules` rows or webhook listeners.
- Require AWX / Tower / AAP as a dispatch medium.
- Bundle clone / destroy / resize / console / template / backup-now
  verbs.
- Bump the `netbox-proxbox` or `proxbox-api` version.

Operators who want the upstream event-rule + webhook shape can
continue to run `netbox-proxmox-automation` alongside this stack;
the two systems coexist per §10 of
[`PROXBOX-AND-PROXMOX-AUTOMATION.md`](../../reference/PROXBOX-AND-PROXMOX-AUTOMATION.md).
