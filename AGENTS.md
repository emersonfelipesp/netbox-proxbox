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
[`0037_v0_0_15_release.py`](./netbox_proxbox/migrations/0037_v0_0_15_release.py)
show the pattern. See [`CLAUDE.md → Plugin settings and configuration`](./CLAUDE.md)
for the full keep-list.

## Sync Mode Controls

Per-resource sync modes control how each Proxmox resource type is reflected into NetBox.
Three modes per type (global and per-endpoint — endpoint takes priority):

- **`always`** — sync on every run (default)
- **`bootstrap_only`** — create once, tag with `bootstrap-only`, never patch/delete again
- **`disabled`** — skip entirely, leave existing objects untouched

Eight resource types: `sync_mode_vm`, `sync_mode_vm_template`, `sync_mode_vm_interface`, `sync_mode_mac`, `sync_mode_cluster`, `sync_mode_node`, `sync_mode_storage`, `sync_mode_ip_address`.

Effective sync modes resolve through a parent-to-child cascade before stage gating and backend query forwarding. A resource is effectively `disabled` when its own mode is `disabled` or any ancestor is effectively `disabled`; child modes never affect parent modes. The hierarchy is:

```
cluster
└── node

vm + vm_template (both disabled only)
└── vm_interface
    ├── ip_address
    └── mac
```

**VM templates** are stored in `ProxmoxVMTemplate` (not `VirtualMachine`). The model has optional FKs to `VirtualMachine` (`source_vm` and M2M `cloned_vms`), `ProxmoxCluster`, and `ProxmoxNode`.

Key files: `choices.py` (SyncModeChoices), `constants.py` (SYNC_MODE_FIELDS), `models/plugin_settings.py` (global fields), `models/proxmox_endpoint.py` (per-endpoint fields + `effective_sync_mode()`), `models/vm_template.py` (ProxmoxVMTemplate), `sync_stages.py` (gating helpers), `netbox_bootstrap.py` (bootstrap-only tag creation), `services/sync_vm_template.py` (template sync service), `docs/configuration/sync-modes.md` (user docs).

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

## CI/CD Workflows

### End-to-end release pipeline (Gitea-first)

The official release pipeline runs in this order:

1. **Gitea tag push** — push an annotated tag to Gitea (`git tag -a vX.Y.Z && git push gitea vX.Y.Z`).
2. **Gitea Actions: `.gitea/workflows/publish-gitea.yml`** — fires on every tag push. Builds and uploads the dist to the Gitea Package Registry, then calls `push-to-github` to push the tag to GitHub. For non-RC tags it also creates (or publishes an existing draft) GitHub release via `gh release create / gh release edit --draft=false`.
3. **GitHub Actions: `.github/workflows/publish-testpypi.yml` — `release: published` trigger** — fires when `publish-gitea.yml` creates the non-draft GitHub release. Validates version, builds dist, checks if version already on PyPI (skip if yes), uploads to PyPI, runs validate-pypi and E2E checks.
4. **GitHub Actions: Docker Hub** — called by `publish-testpypi.yml` after PyPI validation.

### RC (release-candidate) pipeline

1. Push a `vX.Y.ZrcN` tag to GitHub directly (`git push origin vX.Y.ZrcN`).
2. `.github/workflows/publish-testpypi.yml` fires on `push: tags: v*rc*` → publishes to TestPyPI.

### Idempotency guarantee (PyPI upload)

The `publish-pypi` job in `.github/workflows/publish-testpypi.yml` checks the PyPI API before uploading. If the version already exists (HTTP 200), the upload step is skipped and the job succeeds. This prevents duplicate-upload failures when `release: published` fires after a tag-push run already published to PyPI, and allows safe re-triggering of the workflow.

### Gitea Package Registry

Use `PKG_TOKEN` (not `GITEA_TOKEN` — GITEA_ prefix is reserved and will fail). The registry URL is `https://git.nmulti.cloud/api/packages/emersonfelipesp/pypi`.
The publish workflow may receive Gitea `create` events, but branch creation must
be job-gated out; only tag creation/tag push events should run release version
validation.

### Security

- `publish-gitea.yml` uses `env:` indirection for `inputs.tag_name` and `github.event_name` to prevent CI/CD expression injection.
- Tag pattern validation (`^v[0-9]+\.[0-9]+\.[0-9]+(rc[0-9]+|\.post[0-9]+)?$`) rejects unexpected refs before any build step.

## Gitea-to-GitHub Mirror

The Gitea workflow at `.gitea/workflows/mirror-github.yml` mirrors only
approved source branches to the matching GitHub repository. For this repo the
allow-list is `develop` and `main`; `develop` is the staging branch and `main`
is the production branch. The workflow uses
the Gitea Actions secrets `GH_MIRROR_TOKEN` for GitHub and
`SOURCE_MIRROR_TOKEN` for authenticated Gitea source fetches, runs on the
dedicated `mirror-host` runner label, authenticates with `gh`, configures
GitHub git credentials through `gh auth setup-git`, and pushes only
`HEAD:refs/heads/${{ gitea.ref_name }}`. Do not replace it with `git push
--all`, `git push --mirror`, or tag synchronization.

## Branch-tier Deployment

The deployment workflow at `.gitea/workflows/deploy-production.yml` treats
`develop` as staging and `main` as production. Pushes to `develop` deploy
`netbox-proxbox` to `https://staging.netbox.nmulti.cloud`; pushes to `main`
deploy it to `https://netbox.nmulti.cloud`. Manual dispatch can omit
`environment` for `develop` and `main`; specify `environment=staging|production`
when deploying a ref outside those branch triggers.

## Navigation

Read [`CLAUDE.md`](./CLAUDE.md) first for the plugin architecture and documentation map. Use the lower-level `CLAUDE.md` files when working in a specific directory or when changing only one layer of the plugin.

Key architectural invariants to keep in mind:

- **`NetBoxEndpoint` and `FastAPIEndpoint` are singleton-shaped.** The backend proxy (`services/backend_proxy.py`) and dashboard views resolve the first enabled backend row. Import views enforce the singleton constraint — if a record exists, the user is prompted to confirm the override before the existing record is deleted and replaced.
- **`enabled=False` is a hard no-connection gate for endpoint-like rows.** Disabled `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `PBSEndpoint`, `PDMEndpoint`, and companion endpoint rows remain visible inventory records, but operational paths must return before pushing to proxbox-api, registering keys, fetching OpenAPI/status, resolving backend ids, hydrating dashboard/status cards, scheduling jobs, or calling live HA/storage/firewall/SDN/datacenter routes.
- **Firecracker inventory is separate from QEMU/LXC.** Use `FirecrackerHostPool`, `FirecrackerHost`, `FirecrackerImageTemplate`, and `FirecrackerMicroVM` for NMS Cloud micro-VMs. A Firecracker row exposes `kind="firecracker"` and `instance_ref="firecracker:<id>"`; do not model it as a NetBox core `VirtualMachine`.
- **Endpoint export views require token proof for sensitive fields.** `_validate_sensitive_export_token()` supports v1 (dropdown or manual) and v2 (key + secret) modes. Never bypass this check or expose credential fields without it.
- **Export JS is inlined, not a separate static file.** All three endpoint list templates contain the export-modal IIFE directly in `{% block javascript %}`. Do not move it to a `.js` file — it would then require `collectstatic` to be served.
- **Import forms auto-create IPAddress objects.** All three import forms call `IPAddress.objects.get_or_create` in `clean_ip_address()`. Do not replace this with `CSVModelChoiceField` for `ip_address` — that would break cross-instance imports.

## Code Quality Standards

All changes to netbox-proxbox MUST conform to these quality gates before PR review:

### Code Coverage
- Maintain ≥85% coverage: `rtk pytest tests/ --cov=netbox_proxbox --cov-report=term-missing`
- Coverage is enforced in CI; failing coverage blocks merge
- Document uncovered code with a rationale comment (e.g., "except: pass for legacy compat")

### Regression Testing
- Add a test that fails on pre-fix code before implementing any fix
- Run the full test suite: `rtk pytest tests/ --timeout=30 -v`
- Run integration tests: `rtk pytest tests/integration/ -v --timeout=30`
- Validate against E2E Docker stack before release

### Static Analysis

**Ruff (linting):**
```bash
rtk ruff check .          # Errors, style, unused imports
rtk ruff format --check . # Code formatting
```
Fixes errors before pushing. All violations block CI.

**Type Checking (Pyright strict):**
```bash
rtk ty check proxbox_cli
```
Type mismatches block merge. Use `# type: ignore` only with justification.

**Defect Categories Detected:**
- Undefined variables, imports, method/attribute access
- Unused imports and dead code
- Security: SQL injection, unsafe eval, XSS vectors
- Type mismatches (via Pyright strict)

### Requirements Validation

Before writing code, confirm:
1. The feature is traceable to a GitHub issue (link it in the PR description)
2. The design is documented (update nearest CLAUDE.md with architecture notes)
3. You understand how it affects the backend integration (proxbox-api contracts)
4. You've identified all derived requirements (e.g., "sync behavior must be gated")

### Configuration Control

Changes to these configuration items require explicit PR description and CLAUDE.md update:
- Plugin version (`netbox_proxbox/__init__.py` `__version__`)
- NetBox compatibility floor/ceiling (`min_version`, `max_version`)
- Backend service minimum version (`proxbox_api` floor in `pyproject.toml`)
- Database schema (any model/migration change)
- Backend integration contracts (sync routes, SSE payloads, job queue names)

### Safety Model (Intent Workflows)

If your change touches the Proxmox-side mutation path:
1. Verify the default direction remains Proxmox → NetBox (read-only)
2. Confirm that master flag `netbox_to_proxmox_enabled` requires typed confirmation
3. Check that DELETE goes through `DeletionRequest` (no direct destroy calls)
4. Verify authorization permission is separate from the request permission

Violating any of these four invariants is a regression.

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
