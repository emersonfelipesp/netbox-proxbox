# Sync Overwrite Flags

Proxbox decides whether each NetBox object's existing field values are
overwritten on every sync, or preserved once they exist. This is controlled by
23 boolean **overwrite** flags grouped by resource. They live in two places:

- The **plugin singleton** (`ProxboxPluginSettings`) — the global default for
  every endpoint that does not override the flag.
- The **per-Proxmox-endpoint** record (`ProxmoxEndpoint`) — each flag is a
  nullable boolean that can either *inherit* (`NULL`) or *override* the global
  value with `True` / `False`.

When the plugin sends a sync request to the FastAPI backend, it flattens the
*resolved* 23 flags into the query string. The backend (`SyncOverwriteFlags`
in `proxbox-api`) reads those raw query parameters authoritatively and
translates each `False` into a corresponding key being dropped from the
`patchable_fields` allowlist used by `rest_reconcile_async`.

## The 23 flags

| Group | Flags |
|-------|-------|
| **Device** | `overwrite_device_role`, `overwrite_device_type`, `overwrite_device_tags`, `overwrite_device_status`, `overwrite_device_description`, `overwrite_device_custom_fields` |
| **Virtual Machine** | `overwrite_vm_role`, `overwrite_vm_type`, `overwrite_vm_tags`, `overwrite_vm_description`, `overwrite_vm_custom_fields` |
| **Cluster** | `overwrite_cluster_tags`, `overwrite_cluster_description`, `overwrite_cluster_custom_fields` |
| **Node Interface** | `overwrite_node_interface_tags`, `overwrite_node_interface_custom_fields` |
| **Storage** | `overwrite_storage_tags` |
| **VM Interface** | `overwrite_vm_interface_tags`, `overwrite_vm_interface_custom_fields` |
| **IP Address** | `overwrite_ip_status`, `overwrite_ip_tags`, `overwrite_ip_custom_fields`, `overwrite_ip_address_dns_name` |

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
   `sync_stages._build_base_query_params()`. Each backend SSE request carries
   one flat group of overwrite flags, so a sync covering multiple Proxmox
   endpoints is split into one SSE request per endpoint. If no endpoint exists
   or a helper is called without a concrete endpoint, the global singleton is
   used.
2. Every flag is serialized as `"true"` or `"false"`.
3. The backend resolves the flat query keys into `SyncOverwriteFlags` and
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
in `proxbox-api 0.0.10+` (paired with `netbox-proxbox 0.0.13`+) that per-VM
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

The flag set has grown across releases:

| Migration | Release | Flags added |
|---|---|---|
| `0035_overwrite_fields_expansion` | `0.0.13` | 16 per-endpoint overwrite columns (the original Device / VM / Cluster / Node Interface / Storage / VM Interface / IP base set). |
| `0036_add_overwrite_vm_type` | `0.0.15` | `overwrite_vm_type`. |
| `0039_pluginsettings_overwrite_ip_address_dns_name` | `0.0.15` | `overwrite_ip_address_dns_name`. |

When upgrading from `0.0.12` or earlier, run:

```bash
python manage.py migrate netbox_proxbox
```

Existing rows are preserved; new columns default to `NULL` (inherit), so the
upgrade is a no-op for behavior unless you start setting overrides.

## See also

- `proxbox-api` documentation: *Synchronization → Overwrite Flags* describes
  the backend schema and `patchable_fields` propagation.
- `netbox_proxbox/CLAUDE.md` *(internal)* — pre-commit checklist and source
  contracts that lock the 23 flags into REST serializers, forms, and tests.
