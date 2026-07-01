# Tenant assignment by VM-name regex or tags

Tracking issue: [#365](https://github.com/emersonfelipesp/netbox-proxbox/issues/365).

The plugin can resolve a NetBox `tenancy.Tenant` for newly-synced VMs by
matching the VM name against a list of operator-defined regex patterns, or by
reading a Proxmox-sourced NetBox tag convention. Both features are **disabled by
default**; operators opt in globally and may override the toggles on a
per-`ProxmoxEndpoint` basis.

## Configuration

Two model fields, present at both scopes:

| Field | Scope | Default | Inherit semantics |
|---|---|---|---|
| `enable_tenant_name_regex` | `ProxboxPluginSettings` | `False` | — |
| `tenant_name_regex_rules` | `ProxboxPluginSettings` | `[]` | — |
| `enable_tenant_tag_assignment` | `ProxboxPluginSettings` | `False` | — |
| `enable_tenant_name_regex` | `ProxmoxEndpoint` | `None` (inherit) | `None` → use global; `True`/`False` → override |
| `tenant_name_regex_rules` | `ProxmoxEndpoint` | `None` (inherit) | `None` → use global; non-null list → **replaces** global list |
| `enable_tenant_tag_assignment` | `ProxmoxEndpoint` | `None` (inherit) | `None` → use global; `True`/`False` → override |

Resolution helpers:
`netbox_proxbox.sync_params.effective_tenant_regex_for_endpoint(endpoint_id)` and
`netbox_proxbox.sync_params.effective_tenant_tag_assignment_for_endpoint(endpoint_id)`.

### Rule shape

Each rule is a JSON object with two required keys and one optional key:

```json
[
  {"pattern": "^cust-acme-",  "tenant_slug": "acme",  "label": "Acme Corp"},
  {"pattern": "^cust-bigco-", "tenant_slug": "bigco", "label": "BigCo"},
  {"pattern": "^infra-",      "tenant_slug": "internal"}
]
```

- `pattern` — Python regex compiled at save time. Matched with `re.search`.
- `tenant_slug` — slug of an existing `tenancy.Tenant`. Verified on save.
- `label` — optional operator-facing label, not used during resolution.

The list is **ordered**. Resolution is **first-match-wins** — put more
specific patterns before less specific ones (e.g. `^cust-acme-` before
`^cust-`).

### Tag convention

Tag assignment runs after regex assignment. It requires both:

- Marker tag: `cloud-customer`
- Tenant tag: exactly one tag whose slug starts with `tenant-`, for example
  `tenant-confitec`

The tenant slug is the part after `tenant-`. If the VM has no marker, no
tenant tag, an empty `tenant-` tag, or more than one `tenant-*` tag, assignment
is a no-op. Ambiguous multiple tenant tags are logged as a warning.

If the derived tenant does not exist, the plugin creates a `TenantGroup` with
slug `cloud-customers` and name `Cloud Customers` if needed, then creates the
tenant with `slug=<derived slug>`, `name=<derived slug>.title()`, and that group.

## Resolution semantics

- The resolver runs **after** the proxbox-api sync writes the VM, in two
  places: per-VM "Sync Now" (`VirtualMachineSyncNowView.post`) and batch
  selected sync (`sync_stages._run_batch_selected_sync`). It does not run
  inside proxbox-api itself — proxbox-api never writes the `tenant` field.
- The resolver **never overwrites** an existing `vm.tenant` assignment. If
  an operator has set the tenant manually (or a prior run assigned it), the
  resolver leaves it alone.
- Regex assignment runs first. Tag assignment only fills the tenant when the VM
  is still unassigned.
- If a rule's `tenant_slug` no longer resolves to a NetBox tenant at sync
  time, the resolver logs a warning via `logging.warning` and **stops**
  (it does not fall through to the next rule — operator intent was specific).
- An unmatched VM is a no-op.

## Per-endpoint override examples

| Global enabled? | Global rules | Endpoint `enable` | Endpoint `rules` | Effective behavior |
|---|---|---|---|---|
| `False` | any | `None` | `None` | No-op (default) |
| `True` | `[A]` | `None` | `None` | Uses `[A]` |
| `True` | `[A]` | `False` | `None` | No-op on this endpoint |
| `False` | `[]` | `True` | `[B]` | Uses `[B]` on this endpoint only |
| `True` | `[A]` | `None` | `[B]` | Uses `[B]` (endpoint list **replaces** `[A]`) |
| `True` | `[A]` | `None` | `[]` | No rules on this endpoint (explicit override) |

## Form validation

Both the global plugin settings form and the per-endpoint settings form
accept the rule list as JSON entered into a `<textarea>`. Validation runs
at save time and rejects:

- Uncompilable regex (`re.error`).
- `tenant_slug` that does not resolve to a `tenancy.Tenant`.
- Duplicate patterns within the same list.
- Non-list JSON (e.g. `{}`, scalars).

On the per-endpoint form (the endpoint's **Settings** tab → **Tenant
Assignment** sub-tab; a save rejected for a bad regex re-opens that sub-tab
automatically):

- Empty / whitespace-only input → stored as `None` (inherit global).
- Literal `[]` → stored as empty list (explicit override: disable all
  global rules for this endpoint).
- Any other valid JSON list → validated and stored.

## Operational notes

- Tenant assignment is a single SQL update per matched VM
  (`vm.save(update_fields=["tenant"])`).
- proxbox-api requires no changes — the `tenant` field is excluded from
  `_compute_vm_patchable_fields` on the proxbox-api side and is not present
  in the VM create body, so the plugin's assignment is stable across
  subsequent re-syncs.
- Warnings about missing tenant slugs land in the standard NetBox plugin
  logger; tag ambiguity warnings use the same logging path. They do not surface
  as dedicated SSE frames.
