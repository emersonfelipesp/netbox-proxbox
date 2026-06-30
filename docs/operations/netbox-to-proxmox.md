# NetBox to Proxmox Intent

This guide covers the operator workflow for the opt-in NetBox to Proxmox
intent direction. The historical Proxmox to NetBox reflection path remains the
default. Nothing in this workflow mutates Proxmox unless the instance, branch,
permissions, and endpoint gates all allow it.

Use this page when you want NetBox branches to describe desired VM or LXC
state and have the plugin apply that state after merge review.

## Safety Position

- Reflection remains the default direction.
- Intent is disabled by default.
- Intent requires the plugin settings master flag.
- The master flag requires a typed confirmation phrase.
- Each branch must opt in with `apply_to_proxmox=True`.
- Deletions never destroy from the merge handler.
- Deletions create a `DeletionRequest`.
- A separate authorized user must approve a deletion.
- Direct writes to main do not trigger Proxmox applies.
- A post-apply reflection sync should converge to zero drift.

## Prerequisites

1. Install a release that includes the intent models and migrations.
2. Install and enable `netbox-branching`.
3. Run NetBox migrations.
4. Run plugin migrations.
5. Confirm Redis and an RQ worker are running.
6. Confirm the worker listens to the NetBox `default` queue.
7. Configure one `FastAPIEndpoint`.
8. Configure one or more `ProxmoxEndpoint` rows.
9. Enable `allow_writes` on the Proxmox endpoint add/edit form only for
   endpoints that may receive intent writes.
10. Confirm proxbox-api exposes the `/intent/plan` and `/intent/apply` routes.
11. Register the merge validator for netbox-branching.
12. Grant intent request permissions to operators who may request changes.
13. Grant deletion authorization to a separate role.
14. Review the delete flow before granting `intent_delete_*`.

## Required Plugin Settings

The main settings live under **Plugins > Proxbox > Settings**.

`netbox_to_proxmox_enabled`

: Master switch for the intent direction. Leave it disabled until the branch,
  endpoint, worker, and RBAC prerequisites are complete.

`netbox_to_proxmox_typed_confirmation`

: Confirmation phrase required when the master switch is enabled. The phrase is
  `allow-edit-and-add-actions`.

`intent_apply_authorization_self_approve_allowed`

: Allows a deletion requester to approve their own request. The default is
  `False` and should stay false outside a single-operator lab.

## Enabling Intent

1. Open the Proxbox settings page.
2. Enable `netbox_to_proxmox_enabled`.
3. Type `allow-edit-and-add-actions` exactly.
4. Save the settings form.
5. Confirm the red warning callout is gone after a valid save.
6. Open each target Proxmox endpoint.
7. Enable `allow_writes` on each endpoint add/edit form only where writes are
   allowed.
8. Restart NetBox workers if your deployment requires a restart for new code.
9. Create a test branch and run a plan before any production merge.

If the master flag is later disabled, the typed phrase is cleared. Re-enabling
requires typing the phrase again.

## Merge Validator

The merge validator is the read-only preflight gate. It inspects the branch
`ChangeDiff` rows and calls proxbox-api `/intent/plan`.

The validator checks:

- The plugin master flag.
- The branch `apply_to_proxmox` custom field.
- VirtualMachine and LXC diffs on the branch.
- Operator RBAC for create, update, and delete requests.
- The `apply_destroy_confirmed` branch field for deletions.
- Backend plan verdicts from proxbox-api.
- Cloud-init warnings when configured.

The validator returns a permitted or blocked indicator to netbox-branching. If
it blocks, the merge does not complete and Proxmox is not touched.

## Branch Fields

`apply_to_proxmox`

: Enables intent processing for the branch. If false, the branch merge stays
  NetBox-only.

`apply_destroy_confirmed`

: Required when the branch contains DELETE diffs. This does not authorize a
  destroy. It only allows the merge to create pending deletion requests.

## Plan Summary Page

Open `/plugins/proxbox/intent/plan-summary/<branch_id>/` to view the current
plan for a branch.

The page is read-only. It shows:

- Branch identifier.
- Intent settings state.
- Branch opt-in state.
- VirtualMachine `ChangeDiff` rows.
- Per-VM operation and kind.
- Backend or local verdicts.
- A summary message.

Use the page before requesting a merge. If the page shows a blocked verdict,
fix the branch or permissions before merge review.

## Apply Lifecycle

1. Operator creates a netbox-branching branch.
2. Operator sets `apply_to_proxmox=True`.
3. Operator changes VMs or LXC records inside the branch.
4. Operator requests a merge.
5. The merge validator runs a read-only plan.
6. Reviewers inspect the plan summary.
7. The branch is merged.
8. The netbox-branching `post_merge` signal fires.
9. Proxbox enqueues a `ProxmoxApplyJob`.
10. The RQ worker runs the apply job on the default queue.
11. The job builds create, update, or delete payloads.
12. CREATE and UPDATE are sent to proxbox-api `/intent/apply`.
13. DELETE creates a `DeletionRequest`.
14. The job records per-VM results on the apply job row.
15. Reflection sync should later report zero drift.

## Apply Jobs

Apply jobs live at `/plugins/proxbox/intent/apply-jobs/`.

The detail page shows:

- Branch.
- User.
- Run UUID.
- State.
- Start and finish timestamps.
- Per-VM results.
- Live SSE log when the backing NetBox job row exists.

Queued or running jobs can be cancelled from the detail page. Cancellation marks
the apply job failed and records a cancellation entry in `per_vm_results`.

## Create Behavior

CREATE diffs use payloads built from the NetBox VM or LXC record. The backend
performs the Proxmox-side action. If proxbox-api rejects the create, the
per-VM result is failed and the remaining diffs continue where possible.

Common create blockers:

- Missing Proxmox endpoint.
- Endpoint writes disabled.
- VMID already in use.
- Target node missing.
- Target storage missing.
- Cloud-init payload invalid.
- Operator lacks `intent_create_vm` or `intent_create_lxc`.

## Update Behavior

UPDATE diffs compare the branch object with the pre-change data from the
`ChangeDiff`. No-op updates are skipped. Real deltas are sent to proxbox-api.

Common update blockers:

- Operator lacks `intent_update_vm` or `intent_update_lxc`.
- VMID moved between plan and apply.
- Proxmox normalized a field differently than NetBox.
- Endpoint writes are disabled.
- Backend route is unavailable.

## Delete Behavior

DELETE diffs are intentionally different.

The merge handler never calls Proxmox destroy. The apply job creates a pending
`DeletionRequest`, snapshots metadata, and tags the Proxmox object as pending
deletion when tagging is available. A separate authorizer must approve the row
before an executor can call the backend deletion route.

See [Deletion Requests](deletion-requests.md) for the full four-eyes flow.

## RBAC

Grant request permissions narrowly:

- `netbox_proxbox.intent_create_vm`
- `netbox_proxbox.intent_update_vm`
- `netbox_proxbox.intent_delete_vm`
- `netbox_proxbox.intent_create_lxc`
- `netbox_proxbox.intent_update_lxc`
- `netbox_proxbox.intent_delete_lxc`

Grant authorization separately:

- `netbox_proxbox.authorize_deletion_request`

Operators may hold both request and authorization permissions, but self-approval
is blocked unless the self-approval setting is explicitly enabled.

## Stopping Intent

To stop new applies:

1. Disable `netbox_to_proxmox_enabled`.
2. Save settings.
3. Confirm the typed phrase clears.

To block writes even if the master flag is on:

1. Open each Proxmox endpoint.
2. Disable `allow_writes`.
3. Save.

To stop a queued job:

1. Open the apply job detail page.
2. Click **Cancel Apply Job**.
3. Confirm the state changes to failed.

## Common Errors

`netbox-branching is not installed`

: Install and enable the netbox-branching plugin before using branches.

`Intent master flag is disabled`

: Enable the setting and type the confirmation phrase.

`Branch is not opted in`

: Set `apply_to_proxmox=True` on the branch custom fields.

`DELETE diffs require apply_destroy_confirmed=True`

: Set the branch destroy confirmation field, then rerun the plan.

`No FastAPIEndpoint is configured`

: Create the FastAPI endpoint row and verify the backend is reachable.

`writes_disabled_for_endpoint`

: Enable `allow_writes` on the target Proxmox endpoint only after review.

`permission denied`

: Grant the corresponding intent permission to the requesting role.

`Job stays queued`

: Start an RQ worker that listens to the default queue.

`Apply succeeded but drift remains`

: Run reflection sync, compare per-VM results, and review field mappings.

## Related Pages

- [Deletion Requests](deletion-requests.md)
- [Troubleshooting](troubleshooting.md)
- [Headless Sync](headless-sync.md)
- [Operational Verbs](../design/operational-verbs.md)
