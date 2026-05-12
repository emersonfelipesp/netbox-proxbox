# Tenant assignment by VM-name regex

Tracking issue: [#365](https://github.com/emersonfelipesp/netbox-proxbox/issues/365).

The plugin can resolve a NetBox `tenancy.Tenant` for newly-synced VMs by
matching the VM name against a list of operator-defined regex patterns. The
feature is **disabled by default**; operators opt in globally and may
override the toggle and/or the rule list on a per-`ProxmoxEndpoint` basis.

## Configuration

Two model fields, present at both scopes:

| Field | Scope | Default | Inherit semantics |
|---|---|---|---|
| `enable_tenant_name_regex` | `ProxboxPluginSettings` | `False` | — |
| `tenant_name_regex_rules` | `ProxboxPluginSettings` | `[]` | — |
| `enable_tenant_name_regex` | `ProxmoxEndpoint` | `None` (inherit) | `None` → use global; `True`/`False` → override |
| `tenant_name_regex_rules` | `ProxmoxEndpoint` | `None` (inherit) | `None` → use global; non-null list → **replaces** global list |

Resolution helper: `netbox_proxbox.sync_params.effective_tenant_regex_for_endpoint(endpoint_id)`.

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

## Resolution semantics

- The resolver runs **after** the proxbox-api sync writes the VM, in two
  places: per-VM "Sync Now" (`VirtualMachineSyncNowView.post`) and batch
  selected sync (`sync_stages._run_batch_selected_sync`). It does not run
  inside proxbox-api itself — proxbox-api never writes the `tenant` field.
- The resolver **never overwrites** an existing `vm.tenant` assignment. If
  an operator has set the tenant manually (or a prior run assigned it), the
  resolver leaves it alone.
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

On the per-endpoint form:

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
  logger; they do not surface as a dedicated SSE frame.
