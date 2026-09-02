# Recovering / Regenerating Proxbox Data

Use this guide when a NetBox upgrade, plugin reinstall, or failed bootstrap leaves
Proxbox setup data incomplete. A common symptom is that legacy Proxbox custom
fields are missing, so old synced records no longer show the expected Proxmox
metadata.

## Where To Find The Card

The **Repair / Rebuild Proxbox sync-state** card lives on its own page at
`/plugins/proxbox/sync-state/`. Because it is an operator recovery action rather
than a routine one, the page is deliberately **not** listed in the Proxbox
navigation menu: the only entry point is the **Repair / Rebuild sync-state**
link in the footer of `Plugins > Proxbox > Home`.

On that page the card is always visible. What it shows still depends on your
permissions:

- With `view` on `FastAPIEndpoint`, the page checks
  `GET /extras/bootstrap-status` on load and renders the result — the backend
  status badge, any reported detail, and the raw payload. A real bootstrap
  problem is an HTTP 200 response with `ok:false`, e.g. the `Invalid v1 token`
  warnings.
- If you can run the repair but cannot view status (`core.add_job` without
  `view` on `FastAPIEndpoint`), the repair button is still available and no
  bootstrap payload is displayed.

## What The Repair Action Does

When you click **Repair / Rebuild**, the plugin:

1. Calls proxbox-api `POST /extras/custom-fields/reconcile` to recreate or
   update the Proxbox custom-field definitions. This is a **best-effort first
   step, not a gate** (see below).
2. Queues a normal NetBox background job using `ProxboxSyncJob.enqueue`.
3. Runs a full Proxbox sync through the existing sync pipeline. The sync's
   preflight re-pushes the NetBox and Proxmox endpoint credentials to
   proxbox-api and rebuilds the typed sync-state sidecars from live Proxmox
   data — this is the step that recovers a stale/invalid backend credential.

The repair action does not create a separate sync path and does not mutate
Proxmox. It uses the same read-side reflection sync as the regular **Full
Update Sync** button.

## Bootstrap Status

The same UI card displays proxbox-api `GET /extras/bootstrap-status`. Use this
payload to see whether proxbox-api thinks custom fields, content types, endpoint
setup, or other bootstrap pieces are missing.

Permissions:

- Viewing bootstrap status requires `view` permission on `FastAPIEndpoint`.
- Running the repair action requires permission to add NetBox `Job` objects
  (`core.add_job`), the same permission used by Proxbox sync enqueue buttons.

## Recovery Steps

1. Confirm proxbox-api is running and the Proxbox **FastAPI Endpoint** row is
   enabled.
2. Open `Plugins > Proxbox > Home` and follow the **Repair / Rebuild
   sync-state** link in the page footer, or go straight to
   `/plugins/proxbox/sync-state/`.
3. Review **Backend bootstrap status**. If it reports missing setup, keep the
   payload available while troubleshooting.
4. Click **Repair / Rebuild**.
5. Open the linked NetBox job from the flash message and wait for it to finish,
   then re-check the bootstrap status.

The custom-field reconcile is **non-fatal**: if proxbox-api rejects it — which is
expected when the backend holds a stale/invalid NetBox credential, since the
reconcile authenticates with that same credential — the plugin records the
reconcile error as a **warning** and still queues the rebuild sync. The queued
sync's preflight re-pushes the endpoint credentials to proxbox-api and rebuilds
sync-state, which is what actually recovers the `Invalid v1 token` state. The
flash message links the job; open it and confirm the sync completed. Only a
failure to *queue* the sync, a missing permission, or an already-running repair
sync is a hard stop. If the reconcile error persists after the sync completes,
verify the NetBox API token configured on the **NetBox Endpoint** row is valid,
then retry.

## Notes On The Sync-State Sidecar Model

The typed `Proxbox*SyncState` sidecar models are the standard source of truth
for the Proxmox↔NetBox linkage. A normal full sync rebuilds sidecars from live
Proxmox data. Migration 0085 removes the VM-only reflection custom fields and
the obsolete `custom_fields_enabled` setting, so recovery of VM identity and
status always uses `ProxboxVirtualMachineSyncState`; there is no legacy VM
custom-field read path to repair. Migration 0086 removes the remaining thirty
reflection definitions and stale core-object JSON values. Recovery now rebuilds
all reflection state through the typed sidecars; the surviving intent custom
fields are not reflection recovery data.
