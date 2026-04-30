# Sync Overwrite Flags

Proxbox decides whether each NetBox object's existing field values are
overwritten on every sync, or preserved once they exist. This is controlled by
21 boolean **overwrite** flags grouped by resource. They live in two places:

- The **plugin singleton** (`ProxboxPluginSettings`) — the global default for
  every endpoint that does not override the flag.
- The **per-Proxmox-endpoint** record (`ProxmoxEndpoint`) — each flag is a
  nullable boolean that can either *inherit* (`NULL`) or *override* the global
  value with `True` / `False`.

When the plugin sends a sync request to the FastAPI backend, it flattens the
*resolved* 21 flags into the query string. The backend (`SyncOverwriteFlags`
in `proxbox-api`) reads them and translates each `False` into a corresponding
key being dropped from the `patchable_fields` allowlist used by `rest_reconcile_async`.

## The 21 flags

| Group | Flags |
|-------|-------|
| **Device** | `overwrite_device_role`, `overwrite_device_type`, `overwrite_device_tags`, `overwrite_device_status`, `overwrite_device_description`, `overwrite_device_custom_fields` |
| **Virtual Machine** | `overwrite_vm_role`, `overwrite_vm_tags`, `overwrite_vm_description`, `overwrite_vm_custom_fields` |
| **Cluster** | `overwrite_cluster_tags`, `overwrite_cluster_description`, `overwrite_cluster_custom_fields` |
| **Node Interface** | `overwrite_node_interface_tags`, `overwrite_node_interface_custom_fields` |
| **Storage** | `overwrite_storage_tags` |
| **VM Interface** | `overwrite_vm_interface_tags`, `overwrite_vm_interface_custom_fields` |
| **IP Address** | `overwrite_ip_status`, `overwrite_ip_tags`, `overwrite_ip_custom_fields` |

The canonical list of names lives in `netbox_proxbox/constants.py::OVERWRITE_FIELDS`
and a copy is committed in `contracts/overwrite_flags.json`. The same list is
mirrored by the backend; CI on both repositories fails if the two drift.

## Tri-state inheritance

Each per-endpoint flag accepts three values:

| Endpoint value | Effective behavior |
|----------------|--------------------|
| `True` | Always overwrite the field on this endpoint, regardless of the global. |
| `False` | Never overwrite the field on this endpoint, regardless of the global. |
| Unset / `NULL` | Fall back to the global value from `ProxboxPluginSettings`. |

Resolution is implemented by `ProxmoxEndpoint.effective_overwrites()` and the
caller-side `effective_overwrites_for_endpoint(proxmox_endpoint_id)` helper in
`sync_params.py`.

## Where to set them

- **Global defaults:** *Plugins → Proxbox → Plugin Settings*. The page renders
  one checkbox per flag.
- **Per-endpoint overrides:** open a Proxmox endpoint, click the **Settings**
  tab. Each flag renders as tri-state Yes / No / — (inherit). Empty leaves the
  global value in effect; choose Yes or No to override.

The detail page of each endpoint shows the **resolved** value plus an
*Overridden* marker for any flag set explicitly on the endpoint.

## How the flags reach the backend

1. The plugin builds the flat query string in
   `sync_stages._build_base_query_params()`. With one Proxmox endpoint in
   scope it uses the endpoint's resolved values; with zero or multiple
   endpoints in scope it uses the global singleton (the FastAPI backend
   accepts a single flat group, not a per-endpoint map).
2. Every flag is serialized as `"true"` or `"false"`.
3. The backend receives them as `Annotated[SyncOverwriteFlags, Query()]` and
   passes the resolved object into the affected sync services.
4. Each service derives a `patchable_fields` allowlist from the flags and
   forwards it to `rest_reconcile_async` / `rest_bulk_reconcile_async`.
5. Reconcile drops any keys outside the allowlist from the PATCH body, so
   pre-existing NetBox values survive when the corresponding flag is `False`.

## VM sync also enforces device flags

The `overwrite_device_role`, `overwrite_device_type`, and
`overwrite_device_tags` flags govern **two** different write paths in
`proxbox-api`. The bulk DCIM sync respects them, but a single VM sync also
materializes the VM's parent `Device` record — and prior to the fix shipped
in `proxbox-api 0.0.10` (paired with `netbox-proxbox 0.0.13`+) that per-VM
path was reverting `device_type` to *Proxmox Generic Device* on every run.

If you are on `netbox-proxbox 0.0.13`+ and still see your custom `device_type`
reverting:

1. Confirm the paired `proxbox-api` build contains the `_ensure_device`
   patchable-fields fix (see issue [#342](https://github.com/emersonfelipesp/netbox-proxbox/issues/342)).
2. Set `overwrite_device_type=False` either globally (Plugins → Proxbox →
   Plugin Settings) or on the relevant Proxmox endpoint's Settings tab.
3. Re-run a sync; the device type should now persist across both bulk
   cluster syncs and per-VM syncs.

## Migration note

Upgrading the plugin past version 0.0.13 adds the 16 new per-endpoint
overwrite columns. After installing the new release run:

```bash
python manage.py migrate netbox_proxbox
```

Existing rows are preserved; new columns default to `NULL` (inherit), so the
upgrade is a no-op for behavior unless you start setting overrides.

## See also

- `proxbox-api` documentation: *Synchronization → Overwrite Flags* describes
  the backend schema and `patchable_fields` propagation.
- `netbox_proxbox/CLAUDE.md` *(internal)* — pre-commit checklist and source
  contracts that lock the 21 flags into REST serializers, forms, and tests.
