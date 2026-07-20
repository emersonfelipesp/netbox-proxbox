# Recovering / Regenerating Proxbox Data

Use this guide when a NetBox upgrade, plugin reinstall, or failed bootstrap leaves
Proxbox setup data incomplete. A common symptom is that legacy Proxbox custom
fields are missing, so old synced records no longer show the expected Proxmox
metadata.

## What The Repair Action Does

The Proxbox UI includes a **Repair / Rebuild Proxbox sync-state** action on:

- `Plugins > Proxbox > Home`, in the Proxbox Configuration section.
- `Plugins > Proxbox > Settings`, above the settings form.

When clicked, the plugin:

1. Calls proxbox-api `POST /extras/custom-fields/reconcile` to recreate or
   update the Proxbox custom-field definitions.
2. Queues a normal NetBox background job using `ProxboxSyncJob.enqueue`.
3. Runs a full Proxbox sync through the existing sync pipeline.

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
2. Open `Plugins > Proxbox > Home` or `Plugins > Proxbox > Settings`.
3. Review **Backend bootstrap status**. If it reports missing setup, keep the
   payload available while troubleshooting.
4. Click **Repair / Rebuild**.
5. Open the linked NetBox job from the success message and wait for it to finish.
6. Run a normal **Full Update Sync** again only if you need a second verification
   pass after fixing backend or Proxmox connectivity.

If proxbox-api is unreachable or returns a non-2xx response, the plugin shows a
NetBox flash message and does not queue the rebuild sync. Fix the FastAPI
endpoint URL, token, TLS setting, or backend service health, then retry.

## Notes During The Custom-Field Retirement Migration

The current migration path keeps legacy custom fields while adding typed
Proxbox sync-state sidecar models. Rebuilding from live Proxmox state depends on
the paired proxbox-api writer for the fields/models available in your deployed
version. The UI action is still useful before the writer switch lands because it
restores the legacy custom-field definitions and then runs the existing
reflection pipeline.
