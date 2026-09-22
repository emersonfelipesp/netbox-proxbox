# Troubleshooting Intent Operations

This page covers common failures in the NetBox to Proxmox intent workflow. Use
it after reviewing [NetBox to Proxmox Intent](netbox-to-proxmox.md) and
[Deletion Requests](deletion-requests.md).

## Fast Triage

| Symptom | First check |
| --- | --- |
| Proxbox custom fields vanished after upgrade | [Recovering / Regenerating Proxbox Data](recovering-proxbox-data.md) |
| Plan page says branching is missing | `netbox-branching` plugin installation |
| Plan page has no diffs | Branch contains no VirtualMachine `ChangeDiff` rows |
| Merge is NetBox-only | Branch `apply_to_proxmox` is false |
| Merge is blocked | Plan verdict table |
| Apply job stays queued | RQ worker and default queue |
| Apply job fails immediately | FastAPI endpoint and backend reachability |
| Backend says writes disabled | Proxmox endpoint `allow_writes` |
| Deletion row never appears | Apply job per-VM results |
| Approval is forbidden | Authorizer permission or self-approval policy |
| Drift remains after apply | Reflection sync logs and per-VM results |

## Required Services

Check these processes first:

1. NetBox web process.
2. NetBox RQ worker.
3. Redis.
4. proxbox-api.
5. Proxmox API reachability.

The apply job uses the default NetBox queue. A worker that listens only to a
custom queue will not execute intent jobs.

## Proxmox Status Request Times Out

Symptoms in the NetBox log include:

```text
Proxmox status request failed on attempt 3: ... Read timed out. (read timeout=5)
Unable to hydrate Proxmox card for endpoint ...
```

The status request crosses two network directions. The **FastAPI endpoint**
record tells the NetBox process how to reach `proxbox-api`; the **NetBox
endpoint** record tells the `proxbox-api` process how to reach the NetBox API.
Neither record should point at the other service's container address by
accident.

For a shared Docker Compose network, the usual shape is:

| Record | Consumer | Address and port |
| --- | --- | --- |
| ProxBox API (FastAPI) | NetBox | `proxbox-api:8000` — the backend's container port |
| NetBox API | proxbox-api | `netbox:8080` — the NetBox container port in the deployment's compose file |

These are common Compose examples, not fixed values; use the actual internal
listener configured by the deployment.

The published host port, such as `8800:8000`, is for clients outside the
Compose network. It is not automatically the port that another container
should use. From the **proxbox-api container**, verify the NetBox API target;
from the **NetBox container**, verify the FastAPI target. A successful curl or
netcat from the host does not prove either container-to-container path.

If proxbox-api logs either of these warnings:

```text
Failed to fetch ProxboxPluginSettings ... HTTP 403
Unexpected ProxboxPluginSettings response format
```

check the backend's NetBox endpoint first. Confirm that it reaches the NetBox
API rather than proxbox-api itself, and that its token can read the Proxbox
plugin settings endpoint. A 403 is an authorization or target-identity
problem; changing the Proxmox role does not fix it.

If the FastAPI route is reached but `/proxmox/version` still times out, inspect
reachability from the **proxbox-api container** to the configured Proxmox
domain and port (normally `pve.example:8006`), then verify the Proxmox token or
user realm, TLS setting, and `PVEAuditor` permissions. The plugin allows a
longer backend-operation budget than its five-second lightweight connectivity
probe so proxbox-api can return the actual upstream error. The backend log is
the authority for the remaining Proxmox-side failure.

## Settings Problems

### Master Flag Disabled

Symptom:

- Plan page shows `Intent master flag is disabled`.
- Branch merges do not enqueue apply jobs.

Fix:

1. Open Proxbox settings.
2. Enable `netbox_to_proxmox_enabled`.
3. Type `allow-edit-and-add-actions`.
4. Save.
5. Rerun the plan.

### Typed Phrase Missing

Symptom:

- Settings form refuses to save.
- Field error references the confirmation phrase.

Fix:

1. Type the phrase exactly.
2. Do not add quotes.
3. Do not use a translated phrase.
4. Save again.

The phrase is cleared when the master flag is turned off.

### Branch Not Opted In

Symptom:

- Plan page says branch is not opted in.
- Merge completes but Proxmox is unchanged.

Fix:

1. Open the branch's **Proxbox Branch Intent** card.
2. Create or edit the intent and set `apply_to_proxmox=True`.
3. Save.
4. Rerun the plan.

### Destroy Not Confirmed

Symptom:

- DELETE verdict is blocked.
- Message references `apply_destroy_confirmed`.

Fix:

1. Confirm this branch really should request a Proxmox deletion.
2. Set `apply_destroy_confirmed=True` in the **Proxbox Branch Intent** card.
3. Rerun the plan.
4. Continue with separate deletion authorization after merge.

## Merge Validator Problems

### Validator Not Registered

Symptom:

- Branch merges without expected plan blockers.
- No plan call appears in proxbox-api logs.

Fix:

1. Check NetBox `configuration.py`.
2. Confirm netbox-branching merge validators include
   `netbox_proxbox.intent.merge_validator.validate_proxmox_intent`.
3. Restart NetBox.
4. Retry with a test branch.

### Plan Endpoint Unavailable

Symptom:

- Plan summary shows a backend transport error.
- Merge validator blocks with a proxbox-api reachability message.

Fix:

1. Open the FastAPI endpoint detail page.
2. Confirm URL, port, SSL mode, and token.
3. Check proxbox-api `/health`.
4. Check network policy between NetBox and proxbox-api.
5. Check TLS certificates when `verify_ssl=True`.

### Bootstrap status says no NetBox session

Symptom:

- The Proxbox sync-state repair page reports that the backend has no NetBox
  endpoint configured.
- The raw status payload contains `ok:false`, `skipped:true`, and
  `reason:no_netbox_session`.

Fix:

1. Confirm the proxbox-api service is running.
2. Configure proxbox-api's own `NetBoxEndpoint` through its admin UI. The
   NetBox plugin's `FastAPIEndpoint` row configures how NetBox reaches the
   backend; it does not configure how the backend reaches NetBox.
3. Confirm the backend endpoint uses the NetBox service name and
   container-internal port when both services run in one Compose project.
4. Return to the sync-state repair page and select **Check status**.
5. Run **Repair / Rebuild** only after the backend reports a usable session.

## Apply Job Problems

### Job Stays Queued

Symptom:

- Apply job state is queued.
- No live log output appears.

Fix:

1. Start a NetBox RQ worker.
2. Confirm it listens to `default`.
3. Confirm Redis is reachable.
4. Restart the worker after code deployment.
5. Cancel and recreate the job only after confirming the worker state.

### Job Is Running Too Long

Symptom:

- Apply job state remains running.
- Some per-VM results are missing.

Fix:

1. Check proxbox-api logs.
2. Check Proxmox task duration.
3. Confirm backend timeout settings.
4. Confirm network latency to Proxmox.
5. Avoid merging unrelated changes into the same branch while investigating.

### Job Fails With Permission Denied

Symptom:

- Per-VM result message contains `permission denied`.

Fix:

1. Identify operation and kind.
2. Grant the matching permission to the requester.
3. Use `intent_create_vm` or `intent_create_lxc` for creates.
4. Use `intent_update_vm` or `intent_update_lxc` for updates.
5. Use `intent_delete_vm` or `intent_delete_lxc` for deletion requests.
6. Rerun from a new branch or corrected workflow.

### Writes Disabled

Symptom:

- Backend result contains `writes_disabled_for_endpoint`.

Fix:

1. Open the target Proxmox endpoint.
2. Review whether writes are allowed for that endpoint.
3. Enable `allow_writes` only after approval.
4. Rerun the operation.

## Deletion Request Problems

### No Request Created

Symptom:

- A branch deleted a VM but no deletion request exists.

Checks:

1. Did the branch have `apply_to_proxmox=True`?
2. Did the branch have `apply_destroy_confirmed=True`?
3. Did the requester have `intent_delete_*`?
4. Did the apply job run?
5. What does the DELETE per-VM result say?

### Approval Forbidden

Symptom:

- The approval page returns forbidden.

Checks:

1. Is the user authenticated?
2. Does the user have `authorize_deletion_request`?
3. Is the user also the requester?
4. Is self-approval disabled?
5. Is the request still pending?

### Executor Does Not Run

Symptom:

- Request state is approved but not executing.

Fix:

1. Check RQ workers.
2. Check Redis.
3. Confirm the executor job was enqueued.
4. Confirm the worker has current code.
5. Review NetBox job logs.

### Executor Fails

Symptom:

- Request state is failed.
- Executor run UUID may be present.

Fix:

1. Review the metadata snapshot.
2. Check Proxmox object still exists.
3. Check node name and VMID.
4. Check backend credentials.
5. Check proxbox-api logs.
6. Resolve the backend error.
7. Re-run only through the approved executor path.

## Cloud-Init Warnings

The branch validator can warn when cloud-init user data contains a plaintext
`password:` line.

Treat the warning as a review stop unless the password is intentionally
temporary and approved by local policy.

Fix:

1. Prefer SSH keys.
2. Use secrets handled outside branch data.
3. Remove plaintext password lines.
4. Rerun the plan.

## Drift After Apply

Expected result:

- CREATE and UPDATE apply to Proxmox.
- Reflection sync runs later.
- NetBox and Proxmox converge.
- Drift is zero for the applied objects.

If drift remains:

1. Open apply job per-VM results.
2. Check whether the operation succeeded, skipped, or failed.
3. Run a normal reflection sync.
4. Compare Proxmox normalized values with NetBox values.
5. Check whether a field is unsupported by the payload builder.
6. Check whether someone changed Proxmox out of band.
7. File a bug if the apply succeeded but reflection cannot converge.

## Live SSE Log Problems

The apply job detail page shows a live log when it can find the backing NetBox
job row.

If the log is empty:

1. Confirm the apply job was enqueued by the plugin.
2. Confirm the core Job row still exists.
3. Confirm the browser can access the stream URL.
4. Confirm the job has not already been purged.
5. Check browser console errors for blocked EventSource connections.

For a background synchronization job, the plugin probes each unique configured
primary/IP candidate before choosing one. It may select the IP candidate when
the primary readiness probe fails. Once it attempts the mutating stream request
through the selected candidate, it never falls back for a connection, TLS,
timeout, HTTP, body, or semantic failure. The backend may have accepted or
started work even if the Job has not received a progress frame, so replaying
through another candidate could apply the same work twice. Diagnose the prior
run from the Job and backend logs, establish its outcome, and then retry as a
new operator action. A bounded 401 authentication rebind is the only automatic
restart because authentication rejection precedes route work.

## Plan Summary Problems

If the plan page returns a local message instead of backend verdicts:

- Intent is disabled.
- The branch is not opted in.
- The branch has no VM diffs.
- Destroy confirmation is missing.
- proxbox-api is unreachable.

Fix the local blocker first. The backend plan is called only after local gates
are satisfied.

## Escalation Bundle

When opening an issue or escalating internally, include:

1. Plugin version.
2. proxbox-api version.
3. NetBox version.
4. Branch ID.
5. Plan summary screenshot or copied verdicts.
6. Apply job ID.
7. Apply job run UUID.
8. Deletion request ID if involved.
9. Relevant backend logs.
10. Proxmox task output if available.

Do not include plaintext tokens, backend secrets, or cloud-init passwords.

## Related Pages

- [NetBox to Proxmox Intent](netbox-to-proxmox.md)
- [Deletion Requests](deletion-requests.md)
- [Headless Sync](headless-sync.md)
- [Operational Verbs](../design/operational-verbs.md)
