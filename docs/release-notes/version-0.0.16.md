# Version 0.0.16

## Summary

Version `0.0.16` introduces the **NetBox → Proxmox intent** path described in
[Issue #377](https://github.com/emersonfelipesp/netbox-proxbox/issues/377), an
opt-in second integration direction that complements the historic read-only
Proxmox → NetBox reflection pipeline. The release is paired with the backend
release `proxbox-api 0.0.12`, which ships the matching `/intent/*` HTTP
surface (plan validator, CREATE/UPDATE/DELETE dispatchers, cloud-init
builder, deletion-request executor, and audit-journal scrubbing).

Twelve sub-issues land together as Sub-PRs A through L:

- **#378 — Sub-PR A — Design doc.** New
  [`docs/design/netbox-to-proxmox-intent.md`](../design/netbox-to-proxmox-intent.md)
  captures the §1–§17 design from #377 verbatim.
- **#379 — Sub-PR B — Gate.** `ProxboxPluginSettings.netbox_to_proxmox_enabled`,
  typed-confirmation phrase `allow-edit-and-add-actions`,
  `apply_destroy_confirmed` flag, seven RBAC permissions registered through
  migration `0038_intent_permissions`, and a red advanced-direction warning
  callout on the Settings page.
- **#380 — Sub-PR C — Bootstrap custom fields.** Migration
  `0039_intent_custom_fields` registers 10 VM CFs and 2 Branch CFs through
  the `_v0_0_16_release_data` bootstrap module. Branching CFs are guarded so
  the migration is a no-op when `netbox_branching` is not installed.
- **#381 — Sub-PR D — Plan validator.** `POST /intent/plan` on the backend
  plus `netbox_proxbox.intent.merge_validator` returning a
  `BranchActionIndicator(permitted, message)` for `netbox-branching` to
  consume.
- **#382 — Sub-PR E — `post_merge` hook.** New `signal_receivers.py` plus
  `netbox_proxbox.intent.apply_job.ProxmoxApplyJob`. Receiver exceptions are
  fully swallowed (the merge transaction has already committed when
  `post_merge` fires). The run phase is a dry-run no-op in this PR.
- **#383 — Sub-PR F — CREATE.** `apply_job.run` builds
  `VMIntentPayload`/`LXCIntentPayload` from NetBox state, POSTs to
  `/intent/apply`, and stamps `proxbox_intent_state=applied` plus
  `proxbox_last_apply_run_id`. UPDATE/DELETE return `501` in this PR.
- **#384 — Sub-PR G — UPDATE.** Adds delta builders, TOCTOU recheck via
  `find_vmid_record`, and offline-required-key gating
  (`QEMU_OFFLINE_REQUIRED_KEYS = {"cores","memory"}`; LXC adds `mp`,
  `rootfs`). Running VMs are never auto-stopped.
- **#385 — Sub-PR H — DELETE → safe-delete.** DELETE diffs create a
  `DeletionRequest` row, tag the Proxmox VM `proxbox-pending-deletion`, and
  capture a metadata snapshot. The plugin never calls Proxmox destroy from
  the merge handler.
- **#386 — Sub-PR I — Deletion Requests UI + executor.** Approve/reject/list
  views, four-eyes self-approval block at model + view + API client layers,
  TTL cron job, and the two-and-only-two backend destroy dispatchers
  (`qemu_destroy.py`, `lxc_destroy.py`).
- **#387 — Sub-PR J — Audit + four-eyes regression suite.** Pure test PR:
  static destroy-gate walker, state-machine, orphan-tag, and journal-emit
  invariants.
- **#388 — Sub-PR K — Cloud-Init.** `CloudInitPayload` Pydantic model and
  `build_proxmox_ci_args` map the four cloud-init CFs to `ciuser`, `sshkeys`
  (URL-encoded), `cicustom`, and `ipconfig0`. The plan validator emits a
  plaintext-password warning when `cloud_init_user_data` contains a
  `password:` key. New `proxbox_api/utils/log_scrubbing.py` strips
  `cipassword`, `password`, `secret`, and `token` from every journal write.
- **#389 — Sub-PR L — UI / docs / polish.** Plan-summary view, live SSE log
  widget on apply-job detail, audit-chain rendering on deletion-request
  detail, operator guides under `docs/operations/`, version bump to
  `0.0.16` / `proxbox-api 0.0.12`, and the four-invariant **Safety Model**
  appended to `CLAUDE.md` and `AGENTS.md`.

The intent path remains **opt-in at every level**. With
`netbox_to_proxmox_enabled=False` (default), nothing in 0.0.16 changes the
historic read-only reflection behavior.

## Safety Model

netbox-proxbox 0.0.16 enforces four mandatory invariants on the intent path.
Code or configuration that bypasses any of these is a regression.

1. **Default direction is Proxmox → NetBox (read-only).** The intent path is
   opt-in at every level.
2. **Master flag is locked behind a typed confirmation phrase.**
   `netbox_to_proxmox_enabled=True` requires
   `netbox_to_proxmox_typed_confirmation == "allow-edit-and-add-actions"` to
   pass `ProxboxPluginSettingsForm.clean()`.
3. **Every Proxmox-side DELETE goes through a `DeletionRequest`.** Branch
   merges containing DELETE diffs do not call Proxmox destroy at merge time.
4. **Authorization permission is held separately from `intent_delete_*`.**
   `netbox_proxbox.authorize_deletion_request` is independent of
   `intent_delete_vm` / `intent_delete_lxc`; self-approval is rejected unless
   `intent_apply_authorization_self_approve_allowed=True` (default `False`).

## Compatibility

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|--------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.16 | v0.0.11 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8 | v0.0.15 | v0.0.11 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8 | v0.0.14 | v0.0.10.post2 | v0.0.8.post1 | v0.0.3.post1 |

NetBox compatibility range: `4.5.8` – `4.6.99` (unchanged).

The 0.0.16 plugin pairs with the **0.0.12** release of `proxbox-api` for the
new intent path. The 0.0.11 backend remains wire-compatible for the
reflection-side surface; intent calls return `404 Not Found` against an
older backend, and the plugin renders an inline "Backend does not support
intent endpoints — upgrade proxbox-api to v0.0.12 or later." banner.

## Upgrade Notes

- Run `python manage.py migrate netbox_proxbox` after upgrading. Migrations
  `0038_intent_permissions`, `0039_intent_custom_fields`,
  `0040_apply_job_full`, and `0041_deletion_request_full` are additive and
  idempotent. The custom-field migration is a no-op for the two Branch CFs
  when `netbox_branching` is not installed.
- The default for `netbox_to_proxmox_enabled` is `False`. Existing installs
  see no behavior change unless an operator explicitly opts in.
- To opt in, see [`docs/operations/netbox-to-proxmox.md`](../operations/netbox-to-proxmox.md)
  and [`docs/operations/deletion-requests.md`](../operations/deletion-requests.md).
  Granting `intent_delete_*` and `authorize_deletion_request` to the same
  user is allowed by default, but the resulting four-eyes self-approval is
  rejected at the view layer unless
  `intent_apply_authorization_self_approve_allowed=True`.
- The `Deletion Requests` UI lives at
  `/plugins/proxbox/intent/deletion-requests/`. The apply-job UI lives at
  `/plugins/proxbox/intent/apply-jobs/`.
