# Sync-State Endpoint Backfill

The `proxbox_backfill_sync_state_endpoints` management command repairs typed
sync-state rows whose `endpoint` foreign key is null. The raw
`proxmox_endpoint_raw_id` identifies a row in the current proxbox-api database,
but that integer is not sufficient historical ownership evidence by itself. A
restored or reseeded backend, or a deleted and recreated backend endpoint row,
can reuse an integer that previously belonged to another endpoint.

Routine `ProxboxSyncJob` runs use stronger current-run evidence before this
historical repair is relevant. A successful VM write stamps the sidecar's
`last_run_id`. The job reuses the plugin-pk/backend-id map resolved for that
same run and considers only sidecars carrying the exact run ID, but neither
value proves that proxbox-api refreshed the identity payload. The VM's native
cluster must equal the mapped endpoint's authoritative
`ProxmoxEndpoint.netbox_cluster`, and no different endpoint or tracking row may
claim it. Run the endpoint's protected cluster synchronization first when this
ownership is absent. The resolver binds `proxmox_cluster` from the unique
tracking row linked to that native cluster; `proxmox_cluster_name` is only a
same-endpoint fallback or consistency check. When the VM has a native device,
the resolver selects exactly one node in the corroborated endpoint linked to
that device, checks its tracking cluster, and treats `proxmox_node_name` only as
a consistency check. If the VM has no native device, a unique exact name may
fill a null node relation inside that endpoint, but it cannot replace an
existing relation. This fallback cannot cross endpoints. Zero, multiple, or
contradictory matches remain unchanged and are reported. Same-endpoint drift is
repaired only when the VM device, device-linked node, recorded name, and cluster
agree.

The command reads every enabled `ProxmoxEndpoint`, resolves its plugin primary
key to the proxbox-api database ID through the selected `FastAPIEndpoint`. It
updates a row automatically only when:

- `endpoint IS NULL`; and
- `proxmox_endpoint_raw_id` equals that resolved proxbox-api ID; and
- at least one `proxmox_cluster` or `proxmox_node` relation is present; and
- every present relation belongs to the mapped endpoint.

Already-bound rows and rows with unrelated raw IDs remain unchanged. If two
plugin endpoints claim the same backend ID, that backend ID is skipped with a
named reason; the command never guesses which endpoint owns those rows. Rows
whose raw ID matches but whose own inventory does not corroborate the current
mapping remain unbound. The summary's `unverified` bucket reports their exact
count, why they were refused, and a bounded sample of their primary keys. Rows
with both relations null remain unbound under `no_relation_evidence`, even when
their recorded `proxmox_cluster_name` currently matches a cluster owned by the
mapped endpoint. That name is retained in each reason bucket's `sample_rows` so
an operator can assess it, but it is not automatic ownership evidence. When
both relations are present and either one belongs to another endpoint, neither
relation may override the other: the row remains unbound under
`relations_disagree`.

## Preview the repair

Run the preview first in the NetBox container or virtual environment:

```bash
python manage.py proxbox_backfill_sync_state_endpoints --dry-run
```

Select a specific enabled backend when more than one `FastAPIEndpoint` exists:

```bash
python manage.py proxbox_backfill_sync_state_endpoints \
  --dry-run \
  --fastapi-endpoint 3
```

The preview performs backend endpoint-ID resolution, identifies corroborated
rows, and reports unverified rows. It does not call `QuerySet.update()`, create
a branch, or modify any row.

## Apply the repair

After reviewing the preview, run:

```bash
python manage.py proxbox_backfill_sync_state_endpoints --fastapi-endpoint 3
```

Omit `--fastapi-endpoint` only when the normal default backend selection is the
intended proxbox-api instance. The command exits non-zero when no enabled plugin
endpoint can be resolved to a current backend row.

The command is idempotent because it updates only null foreign keys. A real run
locks the candidate sync-state rows and their related cluster and node evidence,
recomputes corroboration inside the same transaction, and retains the null
endpoint, raw backend ID, and exact primary-key guards on the final update. Its
final line reports the exact number of rows bound per sync-state model, every
backend ID skipped for ambiguity or invalid identity data, and every unverified
group left unbound.

## Confirm an otherwise unverified binding

`--confirm-binding BACKEND_ID=PLUGIN_PK:TOKEN` is an explicit operator assertion
that the exact reviewed unverified rows carrying that backend ID belong to that
plugin endpoint. The dry run omits `:TOKEN`; apply requires the token emitted by
that preview. Confirmation is appropriate only when independent operational
records establish the historical ownership, such as after restoring or
reseeding proxbox-api or after deleting and recreating a backend endpoint row.
It must not be used merely to clear the `unverified` bucket.

Use this dry-run-first procedure:

1. Run the ordinary dry run and inspect every `unverified` count, reason, and
   sampled primary key.
2. Establish from recovery records, backups, or change records that the backend
   ID belonged to the named plugin endpoint when those rows were written.
3. Preview the explicit assertion:

   ```bash
   python manage.py proxbox_backfill_sync_state_endpoints \
     --dry-run \
     --fastapi-endpoint 3 \
     --confirm-binding 14=5
   ```

4. Inspect `confirmed_bindings["14=5"].row_pks`. Unlike the bounded
   `unverified` sample, this is the complete list of uncorroborated rows that
   the assertion will bind. The `reasons.no_relation_evidence.sample_rows`
   entries in the ordinary preview retain each sampled row's recorded cluster
   name for operator review. Copy the adjacent deterministic `review_token`. Its
   self-contained, checksummed payload binds the complete sorted primary-key
   list, the confirmed pair, and the full resolved endpoint mapping. The token
   is a checksummed receipt for that reviewed row set, not a secret or proof of
   authentication; independent ownership evidence and command authorization
   remain necessary.
5. Apply the same reviewed assertion by removing `--dry-run` and appending the
   copied token after a colon:

   ```bash
   python manage.py proxbox_backfill_sync_state_endpoints \
     --fastapi-endpoint 3 \
     --confirm-binding 14=5:v1.PAYLOAD.DIGEST
   ```

Repeat `--confirm-binding` for additional independently justified pairs. Each
assertion must match one unambiguous current plugin-to-backend mapping and carry
its own reviewed token, or the command exits without updating rows. During
apply, the command locks and recomputes the current unverified set. If it differs
from the reviewed set, the transaction is refused and the error reports the
exact `added_pks` and `removed_pks`; run and review a new preview instead of
reusing the stale token. The automatic `ProxboxSyncJob` path never supplies
operator confirmations and therefore never binds unverified rows.

## Branch isolation

The command evaluates the same fail-closed branch-isolation setting as
`ProxboxSyncJob` before it reads the backend or changes sync state:

- With `branching_enabled=False`, the real repair updates `main` directly.
- With branch isolation enabled and available, the real repair creates a
  dedicated branch, activates it for the ORM update, and merges it under the
  configured conflict policy. A failed merge leaves the branch available for
  operator inspection and exits non-zero.
- When branch settings cannot be read, or branch isolation is configured but
  `netbox_branching` is unavailable, the command fails before backend access or
  ORM updates.
- `--dry-run` still evaluates the guard but creates no branch and changes
  nothing.

For routine synchronization, use the [`proxbox_sync` management
command](headless-sync.md). Normal `ProxboxSyncJob` runs now perform the same
current-run relation resolution and then the existing locked-relation endpoint
backfill after their backend stages. Both run under the active synchronization
branch. The relation resolver summary is stored as
`sync_state_relation_resolution` beside `sync_state_endpoint_backfill` in the
job data and records bounded counts, primary-key samples, and refusal reasons.
`native_cluster_missing` means the VM must first be assigned to the correct
native cluster. `native_cluster_not_owned_by_endpoint` and
`native_cluster_ownership_ambiguous` require the protected cluster
synchronization and operator review of competing endpoint or tracking claims.
An unexpected resolver error does not fail the synchronization job. The summary
then reports `failed` and `skipped` with the exception class, the resolver
transaction is rolled back, and the next successful run retries the repair. A
job deadline or worker timeout still cancels the job.
Cluster-name/link and node cluster/device contradictions require inventory
correction followed by another full sync; the resolver never guesses.
Selected-VM batch jobs share their job run ID with proxbox-api and use the same
resolver. Direct per-object Sync Now requests do not expose both a caller-known
run stamp and a complete plugin-pk/backend-id map, so they do not invent that
authority; a later staged or selected-VM batch sync performs the repair.
