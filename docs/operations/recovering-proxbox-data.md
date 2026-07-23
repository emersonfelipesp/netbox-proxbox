# Recovering / Regenerating Proxbox Data

Use this guide when a NetBox upgrade, plugin reinstall, or failed bootstrap leaves
Proxbox setup data incomplete. A common symptom is that legacy Proxbox custom
fields are missing, so old synced records no longer show the expected Proxmox
metadata.

## When The Card Appears

The **Repair / Rebuild Proxbox sync-state** card lives on
`Plugins > Proxbox > Home` (Proxbox Configuration section) and
`Plugins > Proxbox > Settings` (above the settings form), but it does **not**
show permanently. It only surfaces when it is useful:

- If you can view bootstrap status (`view` on `FastAPIEndpoint`), the card is
  hidden and the page silently checks `GET /extras/bootstrap-status` on load. It
  reveals itself **only** when the backend reports a real bootstrap problem
  (an HTTP 200 response with `ok:false`, e.g. the `Invalid v1 token` warnings).
  A healthy, unreachable, or unconfigured backend keeps the card hidden.
- If you can run the repair but cannot view status (`core.add_job` without
  `view` on `FastAPIEndpoint`), the card is shown so you keep the repair
  affordance; no bootstrap payload is displayed.

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
2. Open `Plugins > Proxbox > Home` or `Plugins > Proxbox > Settings`. If you can
   view bootstrap status and the card is hidden, the backend reported no
   bootstrap problem. (If you can run the repair but cannot view status, the card
   is shown without a status payload — see "When The Card Appears".)
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

The typed `Proxbox*SyncState` sidecar models are now the standard source of
truth for the Proxmox↔NetBox linkage: the proxbox-api writer/reader switch has
landed, so by default (`ProxboxPluginSettings.custom_fields_enabled=False`)
proxbox-api writes and reads the sidecars and does not write, read, or reconcile
the deprecated legacy reflection custom fields. A normal full sync rebuilds the
sidecars from live Proxmox data, so the repair action recovers sync-state even
when the legacy custom fields are missing. The custom-field reconcile step it
runs first is a best-effort compatibility path for deployments that have flipped
`custom_fields_enabled` back on for a transition; its failure never blocks the
rebuild sync (see above).
