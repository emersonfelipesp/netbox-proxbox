# NetBox → Proxmox Intent Layer

> **Status:** design (Sub-PR A of v0.0.15 / proxbox-api v0.0.11).
> **Tracking issue:** [#377](https://github.com/emersonfelipesp/netbox-proxbox/issues/377).
> **Roadmap deviation:** parent issue nominated `v0.1.0`; this work is
> consolidated into the current-version slot (`v0.0.15` /
> `proxbox-api v0.0.11`) and lands as a sequence of 12 sub-PRs (A-L, #378-#389).

## 1. Motivation

Historically `netbox-proxbox` runs a one-way *reflection* sync:
Proxmox is the source of truth, NetBox mirrors it. Operators who want
to *change* infrastructure must do it in Proxmox (UI or API), and the
plugin reflects the change shortly after.

The intent layer inverts that flow for opt-in branches. Operators
edit `VirtualMachine` records (and their cloud-init / placement
custom fields) inside a NetBox *branch*, review the diff, and on
merge the plugin dispatches Proxmox writes (CREATE / UPDATE / DELETE)
through `proxbox-api`. The result is a GitOps-style declarative
workflow on top of NetBox.

The reflection sync still runs unchanged: operators who do not enable
the master flag observe no behavior change.

## 2. Safety Model

Four invariants that hold at every stage of every sub-PR:

1. **Master flag + typed phrase.** Apply only runs when
   `ProxboxPluginSettings.netbox_to_proxmox_enabled` is `True` and
   `netbox_to_proxmox_typed_confirmation` equals
   `allow-edit-and-add-actions`. The form enforces this at save time
   (`netbox_proxbox/forms/settings.py:536`); the apply job re-checks
   at runtime.
2. **Destroy modules allowlist.** After Sub-PR I lands, only two
   modules in the entire workspace may call Proxmox destroy:
   `proxbox_api/routes/intent/dispatchers/qemu_destroy.py` and
   `…/lxc_destroy.py`. A static walker
   (`tests/test_static_destroy_gate.py`) asserts this by walking both
   repos. Sub-PRs F, G, H carry interim versions of the walker so the
   invariant holds throughout the chain.
3. **Four-eyes deletion.** `DeletionRequest.requested_by` must differ
   from `DeletionRequest.authorizer` unless the operator explicitly
   opts in via `intent_apply_authorization_self_approve_allowed=True`.
   Enforced at three layers: model `clean()`, view, API client.
4. **Receiver isolation.** `handle_branch_merged` (the `post_merge`
   signal receiver) runs after the merge transaction has already
   committed. Its body is wrapped in `try/except`; it never re-raises.
   The apply job is enqueued on RQ and runs out-of-band.

## 3. Trigger mechanism (Option B: `post_merge`)

The intent layer hooks `netbox-branching`'s `post_merge` signal.
When an operator merges a branch whose CF `apply_to_proxmox=True`,
`handle_branch_merged` fires, validates pre-conditions (master flag,
phrase, perms), and enqueues a `ProxmoxApplyJob` keyed by the merged
branch.

The signal handler does **not** itself call Proxmox. It does the
minimum work to enqueue, then returns. The RQ worker picks up the job
and runs the dispatch.

This decouples apply latency from the operator's merge action and
isolates dispatch failures from the merge transaction.

## 4. Plan vs. apply

| Phase | Trigger | Side effects | Returns |
|---|---|---|---|
| **Plan** | `merge_validator` invocation (pre-merge) | None | `BranchActionIndicator(permitted, message, plan_summary)` |
| **Apply** | `post_merge` signal → RQ job | Proxmox writes | `ProxmoxApplyJob.per_vm_results` JSONField |

Plan runs in NetBox's request thread (the user is waiting for the
merge button). It is **read-only**: it validates that target nodes
are online, VMIDs are free, template VMIDs exist, cloud-init YAML
parses, the user has the right `intent_*` permissions, and (for
DELETE diffs) `apply_destroy_confirmed=True`.

Apply runs in the worker. It mutates Proxmox state via
`proxbox-api`'s `/intent/apply` route and the deletion-request
executor.

## 5. Diff classification

The validator reads `branch.changediff_set.filter(object_type__model='virtualmachine')` and classifies each diff:

| diff kind | NetBox semantics | Plan check | Apply dispatcher |
|---|---|---|---|
| CREATE | new VM record | VMID free, node online, template VMID exists | `qemu_create.py` / `lxc_create.py` |
| UPDATE | existing VM, fields changed | TOCTOU-safe re-read | `qemu_update.py` / `lxc_update.py` |
| DELETE | record deleted in branch | `apply_destroy_confirmed=True` + perm | NO destroy. Creates `DeletionRequest` + tags Proxmox VM |

DELETE never destroys directly. It triggers the four-eyes deletion
flow (see §11).

## 6. Custom fields landed by Sub-PR C

**10 VM CFs (attach to `virtualization.virtualmachine`):**

```
proxmox_node                text
proxmox_storage             text
proxmox_iso                 text
proxmox_template_vmid       integer
cloud_init_user             text
cloud_init_ssh_keys         text (long)
cloud_init_user_data        text (long)
cloud_init_network          text
proxbox_intent_state        text   # pending|applied|failed|deleted
proxbox_last_apply_run_id   text   # UUID of last ProxmoxApplyJob
```

**2 Branch CFs (attach to `netbox_branching.branch`):**

```
apply_to_proxmox            boolean
apply_destroy_confirmed     boolean
```

The Branch CF registration is guarded by a `ContentType` lookup so
plugin install without `netbox_branching` skips silently (matches the
`is_branching_available()` runtime guard pattern).

## 7. RBAC permissions (Sub-PR B)

Seven new Django permissions, registered via `RunPython` migration
following the #376 `core.run_proxmox_action` precedent:

```
netbox_proxbox.intent_create_vm
netbox_proxbox.intent_update_vm
netbox_proxbox.intent_delete_vm
netbox_proxbox.intent_create_lxc
netbox_proxbox.intent_update_lxc
netbox_proxbox.intent_delete_lxc
netbox_proxbox.authorize_deletion_request
```

Each has a matching helper in `netbox_proxbox/views/proxbox_access.py`
that returns the dotted name; views consume these via
`ContentTypePermissionRequiredMixin`.

## 8. `/intent/*` route surface on proxbox-api

| Route | Method | Sub-PR | Notes |
|---|---|---|---|
| `/intent/plan` | POST | D | Read-only; validates a list of diffs |
| `/intent/apply` | POST | F → G | CREATE in F; UPDATE in G; DELETE always 501 |
| `/intent/deletion-requests/{id}/approve` | POST | I | 4-eyes guard |
| `/intent/deletion-requests/{id}/reject` | POST | I | Returns reason |
| `/intent/deletion-requests/{id}/execute` | POST | I | Triggers qemu/lxc_destroy dispatchers |

Every write route calls `_gate(endpoint)` from
`routes/proxmox_actions.py` to honor `ProxmoxEndpoint.allow_writes`,
and writes a journal entry via
`services/verb_dispatch.write_verb_journal_entry()`.

Auth is global via `APIKeyAuthMiddleware`; no `AUTH_EXEMPT_PATHS`
change is required.

## 9. `ProxmoxApplyJob` model

Promoted to full schema in Sub-PR E (migration `0040_apply_job_full`).

| Field | Type | Notes |
|---|---|---|
| `branch` | FK `netbox_branching.branch` | `on_delete=SET_NULL` (branch may be deleted; job history survives) |
| `user` | FK | the user who merged the branch |
| `run_uuid` | UUIDField | stamps `proxbox_last_apply_run_id` on each VM |
| `state` | CharField | `queued|running|succeeded|failed|partial` |
| `per_vm_results` | JSONField | per-VMID outcome + reason |
| `started_at` | DateTime | nullable until pickup |
| `finished_at` | DateTime | nullable until completion |

A `partial` state means at least one VM succeeded and at least one
failed; the operator inspects `per_vm_results` to decide next steps.

## 10. `DeletionRequest` state machine

Promoted to full schema in Sub-PR H (migration `0041_deletion_request_full`).

```
        +-------------+
        |   pending   |  ← created by apply job on DELETE diff
        +-------------+
         |     |     |
    approve   reject  TTL expires
         |     |     |
         v     v     v
   +---------+---+-----------+--------------+
   | approved | rejected | auto_rejected |
   +----+-----+----------+--------------+
        |
        execute
        |
        v
  +-------------+
  |  executed   |    OR  +---------+
  +-------------+        | failed  |
                         +---------+
```

Self-approval is blocked at three layers (see §2 invariant 3).

## 11. Cloud-Init (Sub-PR K)

The 4 cloud-init CFs feed into a `CloudInitPayload` Pydantic v2 model
on the backend, which the dispatchers map to Proxmox API arguments:

| NetBox CF | Proxmox arg |
|---|---|
| `cloud_init_user` | `ciuser` |
| `cloud_init_ssh_keys` | `sshkeys` (URL-encoded) |
| `cloud_init_user_data` | `cicustom` (YAML) |
| `cloud_init_network` | `ipconfig0` |

`cipassword` is **never** stored in NetBox. If `cloud_init_user_data`
contains a top-level `password:` key, the merge validator emits a
plan-time warning (toggle: `intent_warn_plaintext_password`,
default `True`).

The backend log path runs every dispatched dict through
`proxbox_api/utils/log_scrubbing.py` so plaintext passwords never
land in audit logs.

## 12. `merge_validator` registration

`netbox-branching` exposes the `merge_validators` PLUGINS_CONFIG hook.
Plugins cannot directly mutate `PLUGINS_CONFIG`; the operator must
register the validator in `configuration.py`.

Sub-PR D ships a management command
`proxbox install-merge-validator` that prints the required snippet:

```python
PLUGINS_CONFIG['netbox_branching'] = {
    'merge_validators': [
        'netbox_proxbox.intent.merge_validator.validate_proxmox_intent',
    ],
}
```

Sub-PR L's operator guide repeats this in plain prose.

## 13. SSE plan / apply progress

The existing SSE infrastructure in `views/job_stream.py` is extended
to forward two new frame kinds:

- `plan_summary` — emitted once before apply starts; lists per-VM
  classifications and verdicts.
- `apply_progress` — emitted per VM during dispatch; carries state
  transitions.

The schema lives at `contracts/proxbox_api_sse_schema.json`; Sub-PR D
adds the two new kinds.

## 14. Test scaffolding

| Test | First lands in | Final form in |
|---|---|---|
| `test_settings_form_gate.py` | B | B |
| `test_settings_warning_callout.py` | B | J |
| `test_intent_permissions.py` | B | B |
| `test_intent_shell_models.py` | B | B |
| `test_bootstrap_intent_cfs.py` | C | C |
| `test_merge_validator.py` | D | D |
| `test_plan_endpoint.py` (backend) | D | D |
| `test_signal_receiver.py` | E | E |
| `test_apply_job_dryrun.py` | E | F |
| `test_apply_endpoint_create.py` (backend) | F | F |
| `test_apply_create_vm.py` | F | F |
| `test_apply_create_lxc.py` | F | F |
| `test_static_no_destroy.py` | F | H |
| `test_apply_endpoint_update.py` (backend) | G | G |
| `test_apply_update_vm.py` | G | G |
| `test_apply_toctou.py` | G | G |
| `test_apply_delete_safe.py` | H | H |
| `test_deletion_request_state_machine.py` | H | I |
| `test_deletion_endpoint.py` (backend) | I | I |
| `test_deletion_request_views.py` | I | I |
| `test_deletion_request_approve.py` | I | I |
| `test_deletion_request_executor.py` | I | I |
| `test_deletion_request_ttl.py` | I | I |
| `test_intent_safety.py` | J | J |
| `test_four_eyes.py` | J | J |
| `test_safe_delete_invariants.py` | J | J |
| `test_orphan_tag_invariants.py` | J | J |
| `test_state_machine_full.py` | J | J |
| `test_static_destroy_gate.py` | J | J |
| `test_audit_log_emits.py` | J | J |
| `test_cloud_init_builder.py` (backend) | K | K |
| `test_cloud_init_zero_diff.py` (backend) | K | K |
| `test_log_scrubbing.py` (backend) | K | K |
| `test_apply_cloud_init.py` | K | K |
| `tests/playwright/intent_full_flow.spec.ts` | L | L |

## 15. Migration order on netbox-proxbox

| Number | Purpose | Sub-PR |
|---|---|---|
| `0037_v0_0_15_release` | (already on `origin/develop`) | n/a |
| `0038_intent_permissions` | 7 RBAC perms | B |
| `0039_intent_custom_fields` | 12 intent CFs | C |
| `0040_apply_job_full` | `ProxmoxApplyJob` schema | E |
| `0041_deletion_request_full` | `DeletionRequest` schema | H |
| `0042_intent_warn_plaintext_password` | settings toggle | K |

One migration per sub-PR keeps the chain auditable.

## 16. proxbox-api inline SQLite migrations

proxbox-api uses inline column migrations in
`proxbox_api/database.py::_migrate_*_columns()`. Sub-PR F adds a new
section there only if intent state needs to be persisted on the
backend side (current design holds intent state in NetBox CFs; the
backend remains stateless for `/intent/*`).

## 17. Rollout phases

| Phase | Default state | Operator action to opt in |
|---|---|---|
| **Phase 0** (v0.0.15 ships) | `netbox_to_proxmox_enabled=False` | none — reflection sync continues |
| **Phase 1** (operator opts in) | typed phrase entered | branches with `apply_to_proxmox=True` dispatch on merge |
| **Phase 2** (delete enabled) | `apply_destroy_confirmed` per branch + 4-eyes config | DELETE diffs reach the deletion-request queue |
| **Phase 3** (full automation) | TTL cron enabled | stale requests auto-reject and untag |

Each phase is reversible: toggle off the master flag and the plugin
reverts to reflection-only behavior on the next merge.

## See also

- Operator guide: `docs/operations/netbox-to-proxmox.md` (Sub-PR L)
- Deletion flow: `docs/operations/deletion-requests.md` (Sub-PR L)
- Troubleshooting: `docs/operations/troubleshooting.md` (Sub-PR L)
- Tracking issue: [#377](https://github.com/emersonfelipesp/netbox-proxbox/issues/377)
