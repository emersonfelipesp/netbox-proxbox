# Deletion Requests

Deletion requests are the mandatory four-eyes workflow for NetBox to Proxmox
DELETE intent. A branch merge containing a DELETE diff must not call Proxmox
destroy. It creates a pending `DeletionRequest` row instead.

This page is for operators who request, approve, reject, or investigate
deletions.

## Core Rule

Every Proxmox-side DELETE goes through a `DeletionRequest`.

No merge handler may destroy a VM or LXC. No plan summary may destroy a VM or
LXC. No custom view may bypass approval. The only destructive action happens
after a pending request is approved and an executor calls the backend deletion
route.

## Four-Eyes Chain

The delete path has five locks:

1. Master setting `netbox_to_proxmox_enabled=True`.
2. Typed phrase `allow-edit-and-add-actions`.
3. Branch field `apply_destroy_confirmed=True`.
4. Requester has `intent_delete_vm` or `intent_delete_lxc`.
5. A separate authorizer has `authorize_deletion_request`.

If any lock fails, the deletion does not execute.

## Roles

Requester

: The user who changes a branch and requests a deletion. This user needs the
  relevant `intent_delete_*` permission.

Authorizer

: The user who reviews and approves or rejects a pending request. This user
  needs `authorize_deletion_request`.

Executor

: The background job that acts after approval. It uses the metadata snapshot
  captured at request time.

## Requesting A Deletion

1. Create a branch.
2. Set `apply_to_proxmox=True`.
3. Set `apply_destroy_confirmed=True`.
4. Delete the VM or LXC record in the branch.
5. Review the plan summary.
6. Confirm the plan does not show local blockers.
7. Request the merge.
8. Merge after normal review.
9. Open `/plugins/proxbox/intent/deletion-requests/`.
10. Confirm a pending row exists.

The merge does not destroy the Proxmox object. It records intent and waits for
separate authorization.

## Request Snapshot

The request captures enough data for later execution even if the NetBox object
no longer exists:

- VMID.
- Node.
- Kind (`qemu` or `lxc`).
- Name.
- Tags.
- CPU.
- Memory.
- Disk data.
- Interface data.
- IP data.
- Custom fields.
- Branch reference where available.
- Requesting user.
- Request timestamp.

The detail page renders the metadata snapshot directly. It does not call
external audit services.

## Pending Tag

When tagging is available, the apply job adds the Proxmox tag
`proxbox-pending-deletion`.

The tag is a marker only. It is not authorization. The destroy still requires a
pending request to be approved by an authorized user.

## Approving A Request

1. Open **Plugins > Proxbox > Deletion Requests**.
2. Filter to `pending`.
3. Open the row.
4. Review the metadata snapshot.
5. Confirm the requester.
6. Confirm the branch.
7. Confirm VMID and node.
8. Click **Approve**.
9. Type the requested VMID when the form requires it.
10. Submit.
11. Confirm the row state becomes approved or executing.
12. Watch executor status and run UUID.

The approval view rejects self-approval unless
`intent_apply_authorization_self_approve_allowed=True`.

## Rejecting A Request

1. Open the pending request.
2. Click **Reject**.
3. Enter a short reason.
4. Submit.
5. Confirm the state is rejected.

Rejected rows remain in NetBox for audit. The metadata snapshot stays attached
to the row.

## Execution

After approval, the executor performs the destructive backend call.

The row tracks:

- Current state.
- Authorizer.
- Approval timestamp.
- Execution timestamp.
- Executor run UUID.
- Failure state when execution fails.

The detail page shows the state transition chain so reviewers can see who
requested, who approved, and whether an executor ran.

## States

`pending`

: Created by an apply job and waiting for authorization.

`approved`

: Approved by an authorized user and ready for execution.

`rejected`

: Rejected by an authorized user or policy.

`executing`

: Executor is currently running.

`succeeded`

: Backend deletion completed.

`failed`

: Backend deletion failed or the executor could not complete.

## Self-Approval Policy

The safe default is no self-approval. A user who requested the delete cannot
approve the same request.

Only enable self-approval for a lab or single-operator environment. Production
roles should keep request and authorization separated.

## RBAC Checklist

Requester role:

- View relevant VMs.
- Change branch content.
- `intent_delete_vm` for QEMU VM deletes.
- `intent_delete_lxc` for LXC deletes.

Authorizer role:

- View deletion requests.
- `authorize_deletion_request`.

Operator role for troubleshooting:

- View apply jobs.
- View deletion requests.
- View backend logs when needed.

## Common Errors

`Self-approval blocked`

: A requester attempted to approve their own deletion. Use a different
  authorized user or intentionally enable the self-approval setting.

`permission denied`

: The requester lacks `intent_delete_*` or the authorizer lacks
  `authorize_deletion_request`.

`apply_destroy_confirmed not set`

: The branch contains DELETE diffs but the branch-level confirmation field is
  false.

`DeletionRequest never appears`

: Check the apply job per-VM results. The DELETE may have been skipped before
  request creation.

`executor_run_uuid is empty`

: The request has not reached executor execution yet, or execution failed before
  a run UUID was assigned.

`state stays pending`

: No authorized user has approved the row.

`state stays approved`

: Check RQ workers and queue state.

`state failed`

: Inspect the row, apply job results, backend logs, and Proxmox task output.

## Audit Review

For an incident review, capture:

1. The branch name and ID.
2. The apply job run UUID.
3. The deletion request ID.
4. Requested by.
5. Authorizer.
6. State transitions.
7. Executor run UUID.
8. Metadata snapshot.
9. Backend log lines for the executor call.
10. Proxmox task result where available.

The NetBox row is the starting point for audit. It should be sufficient to show
the human approval chain without calling external audit APIs.

## Operational Guidance

- Keep pending requests low.
- Reject stale requests instead of leaving them pending indefinitely.
- Review metadata before approval, not after.
- Treat VMID mismatch as a stop condition.
- Do not approve a row only because the branch merged.
- Do not remove pending-deletion tags manually unless recovering from a failed
  workflow.
- Prefer fixing the branch and creating a new request over editing snapshots.

## Related Pages

- [NetBox to Proxmox Intent](netbox-to-proxmox.md)
- [Troubleshooting](troubleshooting.md)
- [Operational Verbs](../design/operational-verbs.md)
