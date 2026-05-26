# Agent Entry Points

## Pre-commit Checklist

Before committing any change:

1. Run syntax check: `python -m compileall netbox_proxbox tests`
2. Run linter: `rtk ruff check .`
3. Run type checker: `rtk ty check proxbox_cli`
4. Run tests: `rtk pytest tests/`

## Framework Stack

When implementing or changing behavior, prefer solutions in this order:

1. NetBox plugin idioms - patterns already used in this plugin and in NetBox's plugin framework.
2. NetBox core - `utilities.forms`, `utilities.views`, `netbox.*` bases, and NetBox-aligned DRF usage.
3. Django - standard `django.*` APIs when NetBox does not provide an equivalent.

Do not add new third-party PyPI dependencies to replace what NetBox or Django already provides. Existing runtime dependencies in `pyproject.toml` — `requests`, `websockets`, `pydantic` (used throughout `schemas/`), and the optional CLI extras — are fine.

## Security

Use NetBox view mixins from `utilities.views` (`ConditionalLoginRequiredMixin`, `TokenConditionalLoginRequiredMixin`, `ContentTypePermissionRequiredMixin`) for custom routes. Enforce object visibility with `QuerySet.restrict()`. Permission strings for ProxBox-specific operations are centralized in [`netbox_proxbox/views/proxbox_access.py`](./netbox_proxbox/views/proxbox_access.py); see [`CLAUDE.md`](./CLAUDE.md) for the current permission and workflow notes.

## Configuration policy

**Prefer DB-backed plugin settings over `.env` variables.**
When adding a new runtime tunable that the plugin or the companion `proxbox-api`
backend needs to read, default to making it a
[`ProxboxPluginSettings`](./netbox_proxbox/models/plugin_settings.py) field —
NetBox-UI-editable and persisted in the NetBox database. On the backend it is read
via `proxbox_api.runtime_settings.get_int / get_float / get_bool / get_str`, which
already resolves **env var (override) → `ProxboxPluginSettings` → built-in default**
with a 5-minute settings cache.

Only fall back to a pure `.env` variable on the backend when the value is needed
**before** the NetBox connection exists or is **operator-only infrastructure** with
no business in the UI: `PROXBOX_BIND_HOST`, `PROXBOX_RATE_LIMIT`,
`PROXBOX_ENCRYPTION_KEY` / `PROXBOX_ENCRYPTION_KEY_FILE`, `PROXBOX_STRICT_STARTUP`,
`PROXBOX_SKIP_NETBOX_BOOTSTRAP`, `PROXBOX_GENERATED_DIR`,
`PROXBOX_CORS_EXTRA_ORIGINS`. Anything that controls sync behavior, batching,
concurrency, caching, or feature toggles belongs in `ProxboxPluginSettings`.

Do **not** invent shadow config layers (parallel JSON/YAML files, ad-hoc dotenv
sections, module-level constants meant as overrides) to dodge the migration cost.
A new field touches all five wiring points — model, migration, form, serializer,
template — and existing fields plus migration
[`0037_pluginsettings_runtime_tunables.py`](./netbox_proxbox/migrations/0037_pluginsettings_runtime_tunables.py)
show the pattern. See [`CLAUDE.md → Plugin settings and configuration`](./CLAUDE.md)
for the full keep-list.

## Release Procedure (summary)

Official releases are cut **from `develop`** and triggered **only** by
GitHub release creation. The publish workflow listens to:

- `push: tags: v*rc*` → TestPyPI (release-candidate gate)
- `release: published` → PyPI (official releases)

Plain non-rc tag pushes (`vX.Y.Z`, `vX.Y.Z.postN`) do **not** trigger
publish. Use `gh release create vX.Y.Z --target develop --verify-tag
--title vX.Y.Z --notes-file docs/release-notes/version-X.Y.Z.md` to fire
the `release: published` event after the version bump commits are merged
into `develop`. Never `twine --skip-existing` — fix forward with the next
`.postN` or `rcN` per PEP 440. Full step-by-step in
[`CLAUDE.md → Release Procedure`](./CLAUDE.md).

## Gitea-to-GitHub Mirror

The Gitea workflow at `.gitea/workflows/mirror-github.yml` mirrors only
approved source branches to the matching GitHub repository. For this repo the
allow-list is `develop` and `main`; `main` is included for future branch
creation, but agents must not create it only for mirroring. The workflow uses
the Gitea Actions secret `GH_MIRROR_TOKEN`, authenticates with `gh`, configures
GitHub git credentials through `gh auth setup-git`, and pushes only
`HEAD:refs/heads/${{ gitea.ref_name }}`. Do not replace it with `git push
--all`, `git push --mirror`, or tag synchronization.

## Navigation

Read [`CLAUDE.md`](./CLAUDE.md) first for the plugin architecture and documentation map. Use the lower-level `CLAUDE.md` files when working in a specific directory or when changing only one layer of the plugin.

Key architectural invariants to keep in mind:

- **`NetBoxEndpoint` and `FastAPIEndpoint` are singletons.** The backend proxy (`services/backend_proxy.py`) and dashboard views always resolve the backend via `.first()`. Import views enforce the singleton constraint — if a record exists, the user is prompted to confirm the override before the existing record is deleted and replaced.
- **Firecracker inventory is separate from QEMU/LXC.** Use `FirecrackerHostPool`, `FirecrackerHost`, `FirecrackerImageTemplate`, and `FirecrackerMicroVM` for NMS Cloud micro-VMs. A Firecracker row exposes `kind="firecracker"` and `instance_ref="firecracker:<id>"`; do not model it as a NetBox core `VirtualMachine`.
- **Endpoint export views require token proof for sensitive fields.** `_validate_sensitive_export_token()` supports v1 (dropdown or manual) and v2 (key + secret) modes. Never bypass this check or expose credential fields without it.
- **Export JS is inlined, not a separate static file.** All three endpoint list templates contain the export-modal IIFE directly in `{% block javascript %}`. Do not move it to a `.js` file — it would then require `collectstatic` to be served.
- **Import forms auto-create IPAddress objects.** All three import forms call `IPAddress.objects.get_or_create` in `clean_ip_address()`. Do not replace this with `CSVModelChoiceField` for `ip_address` — that would break cross-instance imports.

## CLAUDE.md Index

Read the nearest scoped guide for the code you are changing.

- [CLAUDE.md](CLAUDE.md)
- [netbox_proxbox/CLAUDE.md](netbox_proxbox/CLAUDE.md)
- [netbox_proxbox/api/CLAUDE.md](netbox_proxbox/api/CLAUDE.md)
- [netbox_proxbox/forms/CLAUDE.md](netbox_proxbox/forms/CLAUDE.md)
- [netbox_proxbox/management/CLAUDE.md](netbox_proxbox/management/CLAUDE.md)
- [netbox_proxbox/management/commands/CLAUDE.md](netbox_proxbox/management/commands/CLAUDE.md)
- [netbox_proxbox/migrations/CLAUDE.md](netbox_proxbox/migrations/CLAUDE.md)
- [netbox_proxbox/models/CLAUDE.md](netbox_proxbox/models/CLAUDE.md)
- [netbox_proxbox/schemas/CLAUDE.md](netbox_proxbox/schemas/CLAUDE.md)
- [netbox_proxbox/services/CLAUDE.md](netbox_proxbox/services/CLAUDE.md)
- [netbox_proxbox/static/CLAUDE.md](netbox_proxbox/static/CLAUDE.md)
- [netbox_proxbox/static/netbox_proxbox/CLAUDE.md](netbox_proxbox/static/netbox_proxbox/CLAUDE.md)
- [netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md](netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md)
- [netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md](netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md)
- [netbox_proxbox/tables/CLAUDE.md](netbox_proxbox/tables/CLAUDE.md)
- [netbox_proxbox/templates/CLAUDE.md](netbox_proxbox/templates/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md)
- [netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md](netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md)
- [netbox_proxbox/templatetags/CLAUDE.md](netbox_proxbox/templatetags/CLAUDE.md)
- [netbox_proxbox/views/CLAUDE.md](netbox_proxbox/views/CLAUDE.md)
- [netbox_proxbox/views/endpoints/CLAUDE.md](netbox_proxbox/views/endpoints/CLAUDE.md)
- [netbox_proxbox/views/sync_now/CLAUDE.md](netbox_proxbox/views/sync_now/CLAUDE.md)
- [proxbox_cli/CLAUDE.md](proxbox_cli/CLAUDE.md)
- [tests/CLAUDE.md](tests/CLAUDE.md)

---

## Branching-Driven Intent

netbox-proxbox supports **two integration directions**:

1. **Proxmox → NetBox (reflection, default).** The historic, read-only
   pipeline. `proxbox-api` discovers Proxmox state and reflects it into
   NetBox via `createOrUpdate`-style helpers. No Proxmox-side mutation.
2. **NetBox → Proxmox (intent, opt-in).** Operators declare desired state
   on a NetBox **branch**; merging the branch triggers `proxbox-api` to
   apply CREATE / UPDATE / DELETE against Proxmox (VMs, LXC, optional
   Cloud-Init). Gated by
   `ProxboxPluginSettings.netbox_to_proxmox_enabled` (default `False`)
   and per-branch custom field `apply_to_proxmox` (default `False`).

### Decision rule for new features

Every new feature must answer: **does it belong on the reflection side
(read-only), the intent side (write-through), or both?** If "both", ship
the read side first and the write side as a separate sub-PR.

### Invariants for the intent side

- The **single source of truth** for intent is the merged `ChangeDiff`
  list on a branch flagged `apply_to_proxmox=True`.
- The **single trigger** for Proxmox-side mutation is the `post_merge`
  signal from `netbox_branching.signals`. No other code path may mutate
  Proxmox; the operational verbs from #376 (start/stop/snapshot/migrate)
  are the one exception and they are audit-logged identically.
- Direct writes to `main` (no branch) do not trigger applies — they
  remain NetBox-only by construction.
- DELETE requires a **five-lock chain** (see **Safety Model** below):
  master flag + typed confirmation phrase + per-branch
  `apply_destroy_confirmed` + RBAC at request time + a *separate*
  user holding `authorize_deletion_request` who approves the
  resulting `DeletionRequest`. The plugin **never** calls Proxmox
  destroy from the merge handler.
- After every successful apply, the read-side reflection sync must
  produce **zero diffs** (drift-detect verification per #357).

### Safety Model

netbox-proxbox enforces four mandatory safety invariants on the intent
path. Code or configuration that bypasses any of these is a regression.

1. **Default direction is Proxmox → NetBox (read-only).** The intent
   path is opt-in at every level; nothing in this plugin's design
   weakens the read-only default.
2. **Master flag is locked behind a typed confirmation phrase.**
   `netbox_to_proxmox_enabled=True` requires
   `netbox_to_proxmox_typed_confirmation == "allow-edit-and-add-actions"`
   to pass `ProxboxPluginSettingsForm.clean()`. The settings template
   renders a red warning callout listing the risks. Toggling the
   boolean back to `False` clears the typed phrase, forcing a
   re-confirmation on re-enable. Code that bypasses the form-level
   validator is a regression.
3. **Every Proxmox-side DELETE goes through a `DeletionRequest`.**
   Branch merges containing DELETE diffs MUST NOT call Proxmox destroy
   at merge time. Instead, they create a `DeletionRequest` row in
   `pending` state, tag the Proxmox VM `proxbox-pending-deletion`, and
   wait for separate authorization. The metadata snapshot
   (`vmid`, `node`, name, tags, cores, memory, disk, interfaces, IPs,
   CFs) is captured so the executor can act after authorization
   without a NetBox FK. Code that calls Proxmox destroy without first
   creating an *approved* `DeletionRequest` is a regression.
4. **Authorization permission is held separately from
   `intent_delete_*`.** `netbox_proxbox.authorize_deletion_request` is
   declared on `DeletionRequest.Meta.permissions` and is independent
   of `intent_delete_vm` / `intent_delete_lxc` (which control who can
   *request* a delete). Granting both to the same role is allowed,
   but four-eyes self-approval is rejected at the view layer unless
   `intent_apply_authorization_self_approve_allowed=True` (default
   **False**). The Deletion-Requests page lives at
   `/plugins/proxbox/intent/deletion-requests/`.

### Cross-references

- Issue: [`#377`](https://github.com/emersonfelipesp/netbox-proxbox/issues/377)
- Reference doc: [`reference/NETBOX-BRANCHING.md`](./reference/NETBOX-BRANCHING.md)
- Companion roadmap items: #357, #358, #367, #370, #376
