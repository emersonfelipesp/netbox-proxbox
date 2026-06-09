# netbox-proxbox Codebase Guide

## Pre-commit Checklist

**Before committing ANY change:**

1. Run syntax check: `python -m compileall netbox_proxbox tests`
2. Run linter: `rtk ruff check .`
3. Run tests: `rtk pytest tests/`
4. Run type checker: `rtk ty check proxbox_cli`

---

## Framework stack preference

Follow the same dependency order agents use (see [`AGENTS.md`](./AGENTS.md)):

1. **NetBox plugin layer** — Reuse this plugin’s established patterns and NetBox’s plugin APIs (registration, plugin paths, `NetBoxModel` / `NetBoxModelViewSet`, tables and filtersets consistent with other plugin code here).
2. **NetBox core** — Prefer `utilities.forms.fields`, `utilities.forms.widgets`, `utilities.views`, and other `utilities.*` / `netbox.*` primitives before inventing parallel implementations.
3. **Django** — Use `django.forms`, `django.http`, ORM, and related stdlib-backed APIs when NetBox does not offer a specific helper.

**Third-party packages:** Do not introduce new PyPI dependencies for capabilities NetBox or Django already cover. The project already declares `requests`, `websockets`, and optional CLI-related packages in [`pyproject.toml`](./pyproject.toml); add new deps only for integration needs that have no NetBox/Django path, not as shortcuts for UI or API patterns the core stack handles.

**Example:** NetBox may remove or rename widgets (for example legacy Select2 helpers under `utilities.forms.widgets`). Prefer current NetBox field/widget pairs such as `DynamicModelMultipleChoiceField` with API-driven multi-select rather than pulling in extra front-end or Python widget libraries. For form layout and field choices in this plugin, see [`netbox_proxbox/forms/CLAUDE.md`](./netbox_proxbox/forms/CLAUDE.md).

## Security and permissions

- **Registered CRUD** (via `register_model_view` and `netbox.views.generic`) inherits NetBox `ObjectPermissionRequiredMixin`: model permissions plus `queryset.restrict()` for object-level rules.
- **Custom views** should use `utilities.views.ConditionalLoginRequiredMixin` (respects `LOGIN_REQUIRED`) instead of Django’s unconditional `login_required`, and `TokenConditionalLoginRequiredMixin` where REST tokens should authenticate browser-style endpoints.
- **Operational endpoints** (sync actions, schedule job, WebSocket bridge): `ContentTypePermissionRequiredMixin` with permissions defined in [`netbox_proxbox/views/proxbox_access.py`](./netbox_proxbox/views/proxbox_access.py) — typically `add` on core `Job` for queueing sync work, `delete` on core `Job` for cancel actions, and `view` on `FastAPIEndpoint` for read-only WebSocket test UI.
- **Dashboard and JSON helpers**: plugin home requires at least one of `view` on `ProxmoxEndpoint` / `NetBoxEndpoint` / `FastAPIEndpoint` when the user is authenticated; endpoint lists use `.restrict(request.user, "view")`. Proxmox card and keepalive JSON resolve objects through restricted querysets (`get_object_or_404(...restrict(...))`). Tagged devices and VMs use `Device.objects.restrict` / `VirtualMachine.objects.restrict` before listing.
- **Plugin REST API** remains on `NetBoxModelViewSet` with standard NetBox/DRF permission classes.

---

This repository packages the `netbox_proxbox` NetBox plugin. The plugin adds endpoint inventory for Proxmox, NetBox, and the companion ProxBox FastAPI backend; UI pages for sync operations, cluster summaries, status checks, and job actions; REST API endpoints for the core plugin models; Firecracker host-pool, image-template, and micro-VM inventory for NMS Cloud; and a small amount of browser-side JavaScript and styling for the plugin pages.

## Installation documentation truths

- The plugin supports both traditional host/venv NetBox deployments and Docker-based NetBox deployments (for example `netbox-community/netbox-docker`).
- Docker-based plugin installation docs are maintained at [`docs/installation/3-installing-plugin-docker.md`](./docs/installation/3-installing-plugin-docker.md), including `plugin_requirements.txt` and `configuration/plugins.py` usage.
- Backend Docker examples map host `8800` to container `8000` (`-p 8800:8000`) because the published `proxbox-api` image serves through nginx on container port `8000`.

The current plugin config lives in [`netbox_proxbox/__init__.py`](./netbox_proxbox/__init__.py). It declares plugin version `0.0.20.post3` and NetBox compatibility `4.5.8` through `4.6.99` (validated against `4.5.8`, `4.5.9`, `4.6.0`, and official `4.6.1`). The current pairing is `netbox-proxbox 0.0.20.post3` ↔ `proxbox-api 0.0.17.post1` ↔ `proxmox-sdk 0.0.11.post1` ↔ `netbox-sdk 0.0.9.post1`. The `0.0.20.post3` release makes disabled endpoint-like rows inventory-only across Proxmox, NetBox, FastAPI, PBS, PDM, and companion endpoint paths; the `0.0.20.post2` release adds the read-only homepage Latest Sync Jobs table and View all sync jobs button; the `0.0.20.post1` release wires VM-template sync into `ProxboxSyncJob`; the base `0.0.20` release carries the IP-address ownership safety fix across all sync paths and the interface-batch settings persistence fix. The previous `0.0.19` release pairs with backend `0.0.16`. `proxbox-api` is not a Python dependency of this plugin; the services communicate over HTTP.

**Companion repos (cross-link map):**

- Backend service: [`emersonfelipesp/proxbox-api`](https://github.com/emersonfelipesp/proxbox-api) — the full v0.0.17 feature set (firewall model scaffolding, intent tag helpers at `PUT /intent/tag-pending-deletion` and `PUT /intent/untag-pending-deletion`, HA REST shim) requires `proxbox-api >= 0.0.13`. HA endpoints alone require `>= 0.0.12`. Firecracker Cloud provisioning uses proxbox-api `/cloud/firecracker/provision` and `/cloud/firecracker/provision/stream` after this plugin creates or exposes the NetBox-side `FirecrackerMicroVM` record. See its [`docs/api/cluster-ha.md`](https://github.com/emersonfelipesp/proxbox-api/blob/main/docs/api/cluster-ha.md) for the upstream HA contract this plugin proxies.
- Workspace context: [`personal-context/claude-reference/netbox-proxbox.md`](https://github.com/emersonfelipesp/personal-context/blob/main/claude-reference/netbox-proxbox.md) — N-MultiCloud workspace-level notes (cross-repo deps, NetBox compatibility rotation policy).

## Architecture Summary

- `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `ProxmoxCluster`, `ProxmoxNode`, `ProxmoxStorage`, `ProxmoxStorageVirtualDisk`, `BackupRoutine`, `Replication`, `VMBackup`, `VMSnapshot`, `VMTaskHistory`, and `ProxboxPluginSettings` are the plugin's core Proxmox reflection models.
- Companion endpoint models: `PBSEndpoint`, `PDMEndpoint`, `PDMRemote` for Proxmox Backup Server and Datacenter Manager inventory.
- SSH and hardware discovery: `NodeSSHCredential` stores per-node SSH credentials for the optional hardware-discovery pass.
- VM lifecycle models: `ProxmoxVMTemplate` (VM template inventory with optional FK to `VirtualMachine`), `ProxmoxVMCloudInit` (cloud-init config), `CloudImageTemplate` (Firecracker/image factory catalog), `ProxmoxApplyJob` (intent apply job), `DeletionRequest` (auditable delete-request workflow).
- Datacenter config: `ProxmoxDatacenterCpuModel` (custom CPU models synced from PVE).
- Firewall inventory (6 models, read-only): `ProxmoxFirewallSecurityGroup`, `ProxmoxFirewallRule`, `ProxmoxFirewallIPSet`, `ProxmoxFirewallIPSetEntry`, `ProxmoxFirewallAlias`, `ProxmoxFirewallOptions`.
- SDN inventory (3 models, PVE 9.2+): `ProxmoxSdnFabric`, `ProxmoxSdnRouteMap`, `ProxmoxSdnPrefixList`.
- Firecracker Cloud uses separate `FirecrackerHostPool`, `FirecrackerHost`, `FirecrackerImageTemplate`, and `FirecrackerMicroVM` models. A micro-VM is not a NetBox core `VirtualMachine`; API clients identify it with `kind="firecracker"` and `instance_ref="firecracker:<id>"`.
- `ProxboxPluginSettings` includes sync mode fields `sync_mode_vm_interface` and `sync_mode_mac` (migration 0051) and interface-batch tunables `interface_batch_size` (default 5) and `interface_batch_delay_ms` (default 100).
- **`NetBoxEndpoint` and `FastAPIEndpoint` are singletons** — the backend proxy and dashboard always use the first row of each, so only one should exist. Their bulk-import views enforce this by prompting for confirmation before replacing an existing record.
- NetBox UI routes live in [`netbox_proxbox/urls.py`](./netbox_proxbox/urls.py) and are implemented primarily in `netbox_proxbox/views/`.
- The plugin also exposes a NetBox plugin API under `netbox_proxbox/api/`, using serializers, filtersets, and standard `NetBoxModelViewSet` classes.
- Sync actions enqueue NetBox background jobs (`ProxboxSyncJob`) on NetBox's default RQ queue and call the external ProxBox FastAPI SSE endpoints to record progress/result on the Job row.
- The dashboard and Job detail pages are extended by template extensions so Proxbox jobs get run-now/cancel controls and live stream/log helpers.
- Browser updates can flow over SSE streams or the existing WebSocket channel.
- Templates and static assets are conventional Django plugin assets under `netbox_proxbox/templates/` and `netbox_proxbox/static/`.
- All three endpoint types support **CSV/JSON/YAML export** (safe and sensitive modes) and **bulk import** with IP auto-creation and id-stripping. See [`netbox_proxbox/views/endpoints/CLAUDE.md`](./netbox_proxbox/views/endpoints/CLAUDE.md).

## Backend integration notes

- **Single enabled FastAPI row:** HTTP and WebSocket helpers such as `get_fastapi_request_context()` in [`netbox_proxbox/services/backend_proxy.py`](./netbox_proxbox/services/backend_proxy.py), `websocket_client`, and several dashboard views resolve the backend via the first `FastAPIEndpoint` with `enabled=True` (or the first enabled row from a restricted queryset). If multiple enabled FastAPI endpoints exist, whichever row sorts first is used; plan automation and operator docs accordingly.
- **Background Proxbox sync jobs (RQ):** `ProxboxSyncJob` enqueues on NetBox’s **`default`** RQ queue (`RQ_QUEUE_DEFAULT`) so a stock **`manage.py rqworker`** (no queue arguments) picks them up. NetBox’s default worker only listens to **`high`**, **`default`**, and **`low`**; the extra django-rq queue **`netbox_proxbox.sync`** is legacy only. Older Job rows may still show **`netbox_proxbox.sync`** in **Queue**; cancel/RQ lookup uses the stored name. Jobs call proxbox-api **SSE** via [`run_sync_stream`](./netbox_proxbox/services/backend_proxy.py) until a terminal `complete` event.
- **Disabled endpoint rows are a hard no-connection gate:** any endpoint-like row with `enabled=False` (`ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `PBSEndpoint`, `PDMEndpoint`, or companion plugin endpoint objects such as `PBSServer`) remains visible through the API/UI for inventory, but operational paths must return before proxbox-api or remote-service network calls. This includes backend key registration, startup/signal pushes, OpenAPI fetches, keepalive/status probes, backend-id resolution, dashboard/API live reads, and scheduled/manual sync scopes.
- **RQ timeout vs HTTP stream:** NetBox’s default **`RQ_DEFAULT_TIMEOUT`** (often **300s** via `configuration.py`) applies to RQ jobs unless overridden. Long syncs were previously killed by RQ while `requests` was still reading the SSE body. The plugin sets a default **`job_timeout`** of **`PROXBOX_SYNC_JOB_TIMEOUT`** (7200s) in [`ProxboxSyncJob.enqueue`](./netbox_proxbox/jobs.py); pass a larger `job_timeout=` to `enqueue()` if needed. That is separate from the HTTP **between-chunk read** timeout (3600s) inside [`run_sync_stream`](./netbox_proxbox/services/backend_proxy.py).
- **HTTP timeouts for large syncs:** VM sync operations and full-update runs use a 3600-second (1-hour) read timeout instead of the default 5 seconds. VMs with 50+ interfaces require extended time because each interface needs multiple sequential API calls to NetBox (VLAN, bridge, MAC, IPs). See [`http_timeout_for_sync_path`](./netbox_proxbox/services/backend_auth.py) for timeout configuration per sync path.
- **When a job looks “stuck”:** **pending** usually means **no RQ worker** is running (or it does not listen to **`default`**). **running** for a long time usually means proxbox-api is still syncing or the stream is slow/buffered; **errored** with **`JobTimeoutException`** means RQ’s wall-clock limit was hit—increase `job_timeout` or `PROXBOX_SYNC_JOB_TIMEOUT`. Inspect the job **log** and **error** fields before changing code.
- **Cancel on Job detail:** For Proxbox Sync rows in **pending**, **scheduled**, or **running** state, the plugin adds **Cancel job** (POST to `proxbox-cancel`). It requires **delete** permission on the core **Job** model, cancels or stops the linked RQ job when possible, then marks the NetBox job **failed** with a “Cancelled by user.” message. Stopping a **running** job is best-effort (RQ stop + long HTTP reads may not abort instantly).
- **Run now on Job detail:** Shown only when the job is in a **terminal** state (**completed**, **errored**, or **failed**), including after **Cancel** (failed). It is **not** shown for **pending**, **scheduled**, or **running**—use **Cancel** first if a queued run should be abandoned, then **Run now** on the finished row to queue a new sync with the same parameters.
- **Full update (UI vs jobs):** The plugin home may still use non-streaming helpers such as [`sync_full_update_resource`](./netbox_proxbox/services/backend_proxy.py) for JSON/redirect flows. Scheduled or immediate **Proxbox Sync** jobs use **`full-update/stream`** on proxbox-api and execute the full stage chain in one stream: devices, storage, virtual machines, virtual disks, backups, snapshots, network interfaces, IP addresses, VM interfaces, backup routines, and replications.

### SSL Certificate Verification

The `verify_ssl` setting that controls whether proxbox-api verifies NetBox's SSL certificate **belongs in proxbox-api, not in this plugin**. It is configured in the proxbox-api admin UI (typically `http://proxbox-api-host:8000`), not in the NetBox plugin settings.

**Common mistake:** Users encountering SSL verification errors may look for the setting in the NetBox Proxbox plugin or the `FastAPIEndpoint.verify_ssl` field in NetBox. These are incorrect locations. The relevant setting is:
- **In:** proxbox-api admin UI → **NetBox Endpoint** → **Verify SSL** checkbox
- **Not in:** NetBox Proxbox plugin settings
- **Not in:** `FastAPIEndpoint.verify_ssl` (that field controls the plugin's connection to proxbox-api, not proxbox-api's connection to NetBox)

**Minimum version:** proxbox-api **v0.0.14+** (released May 2026) is required for SSL verification settings to work correctly. Earlier versions had a bug where `verify_ssl=False` was ignored due to missing database migrations and incorrect connector logic. If you are experiencing "SSL certificate verify failed" errors despite unchecking `verify_ssl` in the proxbox-api admin UI, upgrade to **v0.0.14 or later** (see [issue #544](https://github.com/emersonfelipesp/netbox-proxbox/issues/544) for details).

**Manual workaround** (before upgrading):
```bash
sqlite3 /path/to/proxbox-api/database.db \
  "UPDATE netboxendpoint SET verify_ssl = 0 WHERE name = 'your-endpoint-name';"
```
Then restart proxbox-api.

## Plugin settings and configuration

**Configuration policy — prefer DB-backed plugin settings.**
When adding a new runtime tunable that proxbox-api or this plugin needs to read,
default to making it a [`ProxboxPluginSettings`](./netbox_proxbox/models/plugin_settings.py)
field (NetBox-UI-editable, persisted in the NetBox database). On the proxbox-api side
it is read via `proxbox_api.runtime_settings.get_int / get_float / get_bool / get_str`,
which resolves **env var (override) → `ProxboxPluginSettings` → built-in default**
with a 5-minute settings cache.

Only fall back to a pure `.env` variable on the backend when the value is needed
**before** the NetBox connection exists or is **operator-only infrastructure** that
has no business in the UI: `PROXBOX_BIND_HOST`, `PROXBOX_RATE_LIMIT`,
`PROXBOX_ENCRYPTION_KEY` / `PROXBOX_ENCRYPTION_KEY_FILE`, `PROXBOX_STRICT_STARTUP`,
`PROXBOX_SKIP_NETBOX_BOOTSTRAP`, `PROXBOX_GENERATED_DIR`,
`PROXBOX_CORS_EXTRA_ORIGINS`. Anything that controls sync behavior, batching,
concurrency, caching, or feature toggles belongs in `ProxboxPluginSettings`.

Do **not** invent shadow config layers (parallel JSON/YAML files, ad-hoc dotenv
sections, module-level constants meant as overrides) to dodge the migration cost.
A new field touches all five wiring points — model, migration, form, serializer, and
template — and the existing fields plus migration
[`0037_v0_0_15_release.py`](./netbox_proxbox/migrations/0037_v0_0_15_release.py)
show the pattern (`SeparateDatabaseAndState` + `IF NOT EXISTS` for production-safe
additive schema changes).

## Sync Mode Controls

Per-resource sync modes let operators control how each Proxmox resource type is
reflected into NetBox. Three modes are available:

- **`always`** (default) — sync on every run; objects are created, updated, and deleted as Proxmox changes.
- **`bootstrap_only`** — sync the object once on first discovery, tag it with `bootstrap-only` in NetBox, and leave it completely untouched on all subsequent runs.
- **`disabled`** — skip this resource type entirely; existing objects are not modified or removed.

Controlled resource types: `sync_mode_vm`, `sync_mode_vm_template`, `sync_mode_vm_interface`, `sync_mode_mac`, `sync_mode_cluster`, `sync_mode_node`, `sync_mode_storage`, `sync_mode_ip_address`.

Resolution priority: **endpoint-level setting takes priority over the global default**. An endpoint field set to null inherits the global `ProxboxPluginSettings` value.

Effective sync modes resolve through a parent-to-child cascade before stage gating and backend query forwarding. A resource is effectively `disabled` when its own mode is `disabled` or any ancestor is effectively `disabled`; child modes never affect parent modes. The hierarchy is:

```
cluster
└── node

vm + vm_template (both disabled only)
└── vm_interface
    ├── ip_address
    └── mac
```

### VM Templates

Proxmox VM templates (`template=True` in the Proxmox API) are stored in the dedicated `ProxmoxVMTemplate` model, NOT as `virtualization.VirtualMachine` rows. Key fields:

- `proxmox_endpoint` (required FK → ProxmoxEndpoint)
- `cluster`, `node` (optional FKs, SET_NULL)
- `source_vm` (optional FK → VirtualMachine, SET_NULL) — the VM this template was made from
- `cloned_vms` (optional M2M → VirtualMachine) — VMs cloned from this template
- Full config snapshot: `vcpus`, `memory`, `disk`, `os_type`, `net_config`, `disk_config`, `raw_config`

`sync_mode_vm` and `sync_mode_vm_template` are independent — disabling VMs does not disable template sync.

### Bootstrap-only tag

The `bootstrap-only` tag (slug `bootstrap-only`) is auto-created by `netbox_proxbox/netbox_bootstrap.py`. The tag is attached to objects when they are first created in `bootstrap_only` mode. Removing the tag manually causes the next sync to treat the object as a normal `always`-mode resource.

### Key files

- `netbox_proxbox/choices.py` — `SyncModeChoices` (always / bootstrap_only / disabled)
- `netbox_proxbox/constants.py` — `SYNC_MODE_FIELDS`, `SYNC_MODE_RESOURCE_TYPES`
- `netbox_proxbox/models/plugin_settings.py` — global `sync_mode_*` fields
- `netbox_proxbox/models/proxmox_endpoint.py` — per-endpoint nullable `sync_mode_*` fields + `effective_sync_mode(resource_type)` method
- `netbox_proxbox/models/vm_template.py` — `ProxmoxVMTemplate` model
- `netbox_proxbox/migrations/0046_sync_modes.py` — migration for sync mode fields
- `netbox_proxbox/migrations/0047_proxmox_vm_template.py` — migration for ProxmoxVMTemplate table
- `netbox_proxbox/sync_stages.py` — `_vm_resource_allowed_by_sync_mode()`, `_has_bootstrap_only_tag()`, `_bootstrap_only_should_skip_existing()`, `_add_bootstrap_only_tag()`
- `netbox_proxbox/netbox_bootstrap.py` — `ensure_proxbox_tags()`, `ensure_bootstrap_only_tag()`
- `netbox_proxbox/services/sync_vm_template.py` — `sync_vm_templates()` service
- `docs/configuration/sync-modes.md` — user-facing documentation

## CI/CD Workflows

### Gitea-to-GitHub mirror (`.gitea/workflows/mirror-github.yml`)

Gitea is the source of truth for normal branch work. The mirror workflow runs
from Gitea Actions and mirrors only the approved branches to the equivalent
GitHub repository: `develop` and `main`. `main` is a future trigger only; do
not create a missing `main` branch just for mirroring.

The job requires the Gitea Actions secrets `GH_MIRROR_TOKEN` for GitHub and
`SOURCE_MIRROR_TOKEN` for authenticated Gitea source fetches, plus the
dedicated `mirror-host` runner label. It installs `gh` when missing,
authenticates with `gh`, validates the GitHub repo, configures GitHub git
credentials with `gh auth setup-git`, and pushes only
`HEAD:refs/heads/${{ gitea.ref_name }}`. It must never sync tags, use
`git push --all`, or use `git push --mirror`.

### Gitea Package Registry publish (`.gitea/workflows/publish-gitea.yml`)

Added to `develop` in v0.0.19. Handles `push: tags:`, `create`, and `workflow_dispatch`.
Due to Gitea 1.26.2 limitations, packages are published via direct upload until the
trigger issues are resolved. See `proxbox-api/CLAUDE.md` for the exact upload command.
Secret name: `PKG_TOKEN` (GITEA_ prefix is reserved by Gitea, cannot be used).
Branch creation events must skip this workflow at the job level; only tag
creation or tag push events should reach the version validation job.

### E2E Docker workflow (`e2e-docker.yml`)

Accepts four main inputs:

| Input | Values | Default | Effect |
|-------|--------|---------|--------|
| `install_source` | `local`, `pypi`, `testpypi`, `container`, `both` | `both` | How netbox-proxbox is installed inside the NetBox container |
| `dependency_mode` | `dev`, `published`, `testpypi-package`, `pypi-package` | `dev` | How the separate proxbox-api container is built or installed |
| `proxbox_api_version` | version string | `PROXBOX_API_RELEASE_VERSION` fallback | Exact proxbox-api version for package-index E2E modes |
| `netbox_image` | full image ref | NetBox matrix | NetBox image override for focused runs |

**`dependency_mode: dev`** — clones `emersonfelipesp/proxbox-api` at HEAD and builds the `raw` Docker target locally. Use this for pre-publish E2E to verify against the latest source.

**`dependency_mode: published`** — pulls `emersonfelipesp/proxbox-api:<PROXBOX_API_RELEASE_VERSION>` from Docker Hub. Use this for post-publish E2E to verify the released image works end-to-end.

**`dependency_mode: testpypi-package`** — builds a temporary proxbox-api container by installing `proxbox-api==<proxbox_api_version>` from TestPyPI.

**`dependency_mode: pypi-package`** — builds a temporary proxbox-api container by installing `proxbox-api==<proxbox_api_version>` from PyPI.

### Release pipeline (`publish-testpypi.yml`)

```
prepare-release
├── TestPyPI lane
│   ├── publish-testpypi
│   ├── validate-testpypi
│   └── e2e-docker-testpypi (install_source=testpypi, dependency_mode=testpypi-package)
└── PyPI lane
    ├── validate-pypi-candidate
    ├── e2e-docker-pypi-candidate (install_source=local, dependency_mode=pypi-package)
    ├── publish-pypi
    ├── validate-pypi
    └── e2e-docker-pypi (install_source=pypi, dependency_mode=pypi-package)
```

`rcN` tag pushes (pattern `v*rc*`) publish to TestPyPI for release-candidate validation. **Official releases (`vX.Y.Z`, `vX.Y.Z.postN`) are triggered exclusively by GitHub release creation (`release: published`) — non-rc plain tag pushes no longer trigger the publish workflow.** Manual dispatch with `publish_target=pypi` also publishes to PyPI.

TestPyPI validation installs both `netbox-proxbox` and the configured `proxbox-api` from TestPyPI. PyPI candidate/final validation uses PyPI `proxbox-api` for backend package-index E2E.

Package uploads intentionally do not use `twine --skip-existing`; if a version is consumed by TestPyPI/PyPI and validation later fails, fix forward with the next `.postN` or `rcN`.

For public docs, keep [`docs/developer/ci-e2e-workflows.md`](./docs/developer/ci-e2e-workflows.md) and [`docs/developer/release-publishing.md`](./docs/developer/release-publishing.md) aligned with this section.

### Release Procedure (manual steps around the workflow)

**Two trigger rules — official releases are always cut from `develop` via
GitHub release creation.**

| Trigger | Use for | Publishes to |
|---------|---------|--------------|
| `push: tags: v*rc*` (plain tag push) | Release candidates `vX.Y.ZrcN` | TestPyPI |
| `release: published` (GitHub release) | Official `vX.Y.Z` and `vX.Y.Z.postN` | PyPI (Created automatically by `.gitea/workflows/publish-gitea.yml` for future releases) |

Plain non-rc tag pushes (`vX.Y.Z`, `vX.Y.Z.postN`) **do not** trigger the
publish workflow — the trigger pattern is `v*rc*`, so only rc tags fire it.
This makes the GitHub release creation the **single, authoritative trigger**
for official PyPI publishing and eliminates the duplicate-run problem the
old dual-trigger flow created.

For future releases, `.gitea/workflows/publish-gitea.yml` (Gitea Actions) pushes
the tag to GitHub **and** creates the non-draft GitHub release automatically via the
`push-to-github` → "Create GitHub Release" step, which fires `release: published`
and triggers the GitHub Actions publish workflow. Manually running `gh release create`
is only needed if `publish-gitea.yml` was not yet added, or for hotfix releases done
directly on GitHub.

**RC flow (TestPyPI gate, repeatable):**

1. From an rc branch, bump to `X.Y.ZrcN` in `pyproject.toml`,
   `netbox_proxbox/__init__.py`, and `uv.lock`. Local verify:
   ```bash
   python -m compileall netbox_proxbox tests
   rtk ruff check .
   rtk pytest tests/
   ```
2. Annotated tag, push:
   ```bash
   git tag -a vX.Y.ZrcN -m "Release vX.Y.ZrcN"
   git push origin vX.Y.ZrcN
   gh run watch <run-id> --repo emersonfelipesp/netbox-proxbox
   ```
3. If anything fails, fix-forward with `rcN+1` — never `twine --skip-existing`.

**Official-release flow (cut from `develop`):**

1. **Merge the validated rc line into `develop`.** Once `rcN` is green on
   TestPyPI + the full E2E matrix + Page Coverage, bump versions on the rc
   branch to the final `X.Y.Z`, commit, then merge that branch into
   `develop` with a normal merge commit (`git merge --no-ff`). Push
   `develop`. The released version's commits MUST be on `develop` before
   the GitHub release is created.
2. **Verify `develop` has the version bumps you intend to release:**
   ```bash
   git log --oneline origin/develop | head -5
   grep '^version' pyproject.toml
   grep 'version = ' netbox_proxbox/__init__.py
   ```
3. **Create the GitHub release pointing at `develop`.** This is the only
   step that fires the publish workflow:
   ```bash
   gh release create vX.Y.Z \
     --repo emersonfelipesp/netbox-proxbox \
     --target develop \
     --verify-tag \
     --title vX.Y.Z \
     --notes-file docs/release-notes/version-X.Y.Z.md
   ```
   - Use `--verify-tag` when the tag already exists at the right commit
     (e.g. from a prior rc → final tag move). Otherwise omit it and
     `gh release create` will create the tag at the tip of `--target develop`.
   - Use `--notes-file` to point at the curated release notes; fall back to
     `--generate-notes` only for posts that have no curated file.
4. **Watch the publish run:**
   ```bash
   gh run list --repo emersonfelipesp/netbox-proxbox --event release \
     --limit 3 --json databaseId,name,status,conclusion
   gh run watch <run-id> --repo emersonfelipesp/netbox-proxbox
   ```
5. **Verify the dist is live on PyPI:**
   ```bash
   curl -s https://pypi.org/pypi/netbox-proxbox/json | jq '.releases | keys'
   ```
6. **Delete the rc branch** (local + remote) once PyPI is green. Only
   `develop` and `gh-pages` should remain on `origin`.

**Do not:**

- Do not push a non-rc tag with `git push origin vX.Y.Z` and expect publish
  to fire. The trigger pattern is `v*rc*`; the tag push will succeed on
  GitHub but no workflow runs. Use `gh release create` instead.
- Do not cut official releases from a `release/*` or `vX.Y.Z` branch and
  then merge into `develop` afterwards. The new policy is the reverse:
  land on `develop` first, then create the GitHub release pointing at
  `develop`.
- Do not add `twine --skip-existing`. Fix forward with `.postN` per PEP 440.
- Do not force-push to a published tag. Tags on the remote are immutable.

What was done for v0.0.17 (first release under the develop-first policy):

- `0.0.17rc1` → `0.0.17rc10` cycled on TestPyPI via `push: tags: v*rc*`
  fix-forward until Page Coverage + full E2E matrix (NetBox v4.5.8 / v4.5.9
  / v4.6.0 × pve/pbs/pdm) + TestPyPI validate all went green.
- Merged `release/v0.0.17` into `develop` with a normal merge commit
  resolving the firewall.py conflict (took the `_choices_2tuple` helper
  side, the validated rc10 fix). Pushed `develop`.
- Created the GitHub release with
  `gh release create v0.0.17 --repo emersonfelipesp/netbox-proxbox
  --target develop --verify-tag --title v0.0.17 --notes-file
  docs/release-notes/version-0.0.17.md`. That single command fired the
  `release: published` event and the publish workflow. **No duplicate run
  to cancel** — the workflow trigger had already been narrowed to
  `v*rc*` plus `release: published`, so the tag itself (which existed at
  the rc10 commit before `gh release create`) did not re-fire publish.
- Deleted the `release/v0.0.17` branch locally and on the remote.

What was done for v0.0.16 / v0.0.16.post3 (legacy dual-trigger flow):

- Released `0.0.16`, `0.0.16.post1`, `0.0.16.post2`, and `0.0.16.post3`
  in sequence (PEP 440 fix-forward — never `twine --skip-existing`). Final
  PyPI dist is `netbox-proxbox 0.0.16.post3`.
- After PyPI was green, merged the `v0.0.16` branch into `develop` via a
  two-parent merge commit (`merge --no-ff`, parents `[136966c, 934fd8a]`).
  Pushed the resulting commit (`4eec556`) as a fast-forward of `develop`.
- Created the GitHub release with
  `gh release create v0.0.16.post3 --repo emersonfelipesp/netbox-proxbox
  --title v0.0.16.post3 --generate-notes`.
- Cancelled the duplicate `Release validation and publish` run that the
  GitHub release spawned with `gh run cancel`. **This duplicate-run cancel
  step is no longer needed under the v0.0.17+ workflow trigger config.**
- Deleted the `v0.0.16` branch locally and on the remote. Only `develop`
  and `gh-pages` remain on origin.

What was done for v0.0.16.post4 → v0.0.16.post6 (fix-forward series):

- **v0.0.16.post4** — migration squash: folded migrations 0038–0047 into
  `0038_v0_0_16_release` so fresh installs run one squashed migration instead of
  ten incremental ones. Added companion-plugins documentation (netbox-pbs,
  netbox-pdm, netbox-ceph, netbox-packer) in `docs/companion-plugins/`.
- **v0.0.16.post5** — migration fix-forward: dropped `replaces` from
  `0037_v0_0_15_release` and `0038_v0_0_16_release` to resolve post-squash
  migration graph errors that appeared on upgrades from 0.0.15.
- **v0.0.16.post6** — security: upgraded `idna` to 3.15 to resolve
  CVE-2024-3651 (domain label validation bypass). Published with
  `gh release create v0.0.16.post6 --repo emersonfelipesp/netbox-proxbox
  --title v0.0.16.post6 --generate-notes`.

Sibling-plugin releases (`netbox-pbs`, `netbox-pdm`, `netbox-ceph`,
`netbox-packer`) should adopt the same develop-first + GH-release-triggered
policy when their next release cycle begins. Until they do, the older
"cancel duplicate" step still applies on those repos.

What was done for v0.0.19:

- Fixes database and API compatibility issues between the plugin and proxbox-api:
  `FastAPIEndpoint` token-drift fix (re-register on explicit token change),
  `PBSEndpoint`/`PDMEndpoint` `host` and `timeout_seconds` bridging properties.
- **Gitea-first publish pipeline**: added `.gitea/workflows/publish-gitea.yml` to
  `develop`. The workflow handles `push: tags:`, `create`, and `workflow_dispatch`
  events but Gitea 1.26.2's dispatch API returns 500 and tag triggers don't fire on
  this instance. Until resolved, packages are published via direct `uv build` +
  `twine upload` to `https://git.nmulti.cloud/api/packages/emersonfelipesp/pypi`
  using the `PKG_TOKEN` secret (GITEA_ prefix is reserved by Gitea, cannot be used).
  See `proxbox-api/CLAUDE.md` for the full upload command.
- Paired backend: `proxbox-api v0.0.16`.
- **GitHub release**: The draft GitHub release `v0.0.19` was published via `gh release edit v0.0.19 --repo emersonfelipesp/netbox-proxbox --draft=false` (one-time cleanup for releases created as drafts before `publish-gitea.yml` was added). For future releases, `.gitea/workflows/publish-gitea.yml` creates the non-draft GitHub release automatically via the `push-to-github` → "Create GitHub Release" step, which fires `release: published` and triggers the GitHub Actions publish workflow.

### Automatic Production Deployment (`.gitea/workflows/publish-gitea.yml`)

**Starting with v0.0.19**, non-release-candidate (`vX.Y.Z`, `vX.Y.Z.postN`) releases automatically deploy to `netbox.nmulti.cloud` after successful Gitea package registry publish and GitHub release creation.

**Deploy job:**
- Runs after `push-to-github` job completes (requires validated tag and GitHub Release created)
- Condition: only for non-RC releases (`is_rc == false`)
- Runs on a `prod-deploy` runner (the repo's Gitea Actions runner must carry the
  `prod-deploy:host` label in addition to `mirror-host:host`, or the deploy job
  stays queued forever)
- Executes the deploy with the **short** plugin name `proxbox` (the deploy
  script's whitelist maps `proxbox` → module `netbox_proxbox` / package
  `netbox-proxbox`; passing `netbox-proxbox` fails validation). It prefers the
  local script when the runner is on the prod host, falling back to ssh for a
  remote runner: `/opt/nmulticloud/deploy/bin/deploy-netbox-plugin proxbox "$TAG"`
  else `ssh nmc-prod-207 -- deploy-plugin proxbox "$TAG"`

**Security hardening:**
- TAG is passed via environment variable, not direct GitHub Actions context interpolation
- Bash case statement validates tag format before SSH (accepts `v<X>.<Y>.<Z>` patterns)
- StrictHostKeyChecking=accept-new prevents MITM attacks
- Quoted variable interpolation prevents shell injection

**Deployment flow:**
1. Git fetch/checkout of the released tag in the plugin submodule
2. pip install -e to refresh editable install
3. manage.py migrate to apply any pending migrations
4. manage.py collectstatic to collect new/updated static files
5. systemctl reload netbox-production (graceful gunicorn reload)
6. systemctl restart netbox-rq (RQ worker restart for code changes)
7. Health check: curl -sf http://127.0.0.1:18001/api/ to verify

**Monitoring deployment:**
- Watch the `publish-gitea.yml` workflow run in Gitea Actions
- Check the `deploy` job logs for SSH output and health check results
- Verify production health: `ssh nmc-prod-207 -- health netbox`
- Check service logs: `ssh nmc-prod-207 -- logs netbox`

**Manual deployment for hotfixes or rollbacks:**
```bash
# Deploy a specific tag or branch (short name "proxbox", not "netbox-proxbox")
ssh nmc-prod-207 -- deploy-plugin proxbox v0.0.19.post1

# List recent deploys (check system journal)
ssh nmc-prod-207 -- journalctl -u netbox-production -n 50 --no-pager
```

For detailed production deployment infrastructure and cross-plugin coordination, see `/root/personal-context/nmulticloud-context/CLAUDE.md` "Automatic Plugin Deployment to Production" section.

---

## Software Engineering Life Cycle Requirements

This section establishes project-wide quality standards derived from industry-standard software engineering practices. All changes must conform to these requirements before release.

### Requirements Traceability and Design Documentation

**Architectural Design:** The plugin's architecture is defined across:
- **Plugin models** (`netbox_proxbox/models/`) — subsystem decomposition
- **Service layers** (`netbox_proxbox/services/`) — dependency definitions and evolution rules
- **API contracts** (`netbox_proxbox/api/`, `netbox_proxbox/schemas/`) — interface specifications
- **Integration surface** (backend proxy routes, sync job contracts) — cross-subsystem dependencies

Changes to plugin models, service APIs, or backend contracts MUST include an updated architecture note in the closest CLAUDE.md explaining:
- What subsystem or interface changed
- Why the change is necessary (traceability to an issue or feature)
- What downstream systems are affected
- Any breaking changes or migration steps

**Derived Requirements:** All plugin features must support the derived requirement that NetBox remains the source of truth for sync data. Features that mutate Proxmox directly (intent workflows) must be explicitly gated and safety-locked.

**Verification:** Before opening a PR, confirm that:
1. Models and schemas match their CLAUDE.md documentation
2. All new public methods have docstrings explaining purpose and contracts
3. Integration points (backend proxies, SSE contracts, webhook handlers) are documented in the nearest CLAUDE.md

### Code Coverage and Quality Metrics

**Coverage Target:** Maintain ≥85% code coverage for the `netbox_proxbox/` package. Coverage is measured by `pytest-cov` and reported in CI.

**Coverage Reporting:** 
- `rtk pytest tests/ --cov=netbox_proxbox --cov-report=term-missing` runs locally
- GitHub Actions CI enforces coverage thresholds on every push
- Uncovered code MUST be documented with a rationale (e.g., "except: pass for legacy API compatibility")

**Exclusions:** The following are exempt from coverage requirements:
- `netbox_proxbox/static/` (JavaScript), `netbox_proxbox/templates/` (Django templates)
- Database migration files (`netbox_proxbox/migrations/`)
- Unreachable exception handlers and platform-specific branches

### Testing and Regression Requirements

**Test Suite:** All changes must include unit and integration tests:
- **Unit tests** (`tests/test_*.py`) — verify individual functions and models in isolation
- **Integration tests** (`tests/integration/`) — verify plugin + NetBox + proxbox-api workflows end-to-end
- **Regression tests** — always include a test that would fail on the pre-fix code

**Regression Testing:** Before release, run:
```bash
rtk pytest tests/integration/ -v --timeout=30
rtk pytest tests/ -v --cov=netbox_proxbox --cov-report=term-missing
```
This verifies that no previously passing test was broken by the change.

**E2E Validation:** Changes to sync workflows, backend integration, or Proxmox VM models must be validated against the full E2E Docker stack:
```bash
docker compose -f e2e/docker/docker-compose.yml up --build -d
bash e2e/docker/wait-for-stack.sh
bash e2e/docker/smoke.sh
```

### Static Analysis and Quality Gates

**Linting:** All code must pass `ruff` static analysis:
```bash
rtk ruff check .          # Detect errors, style violations, unused imports
rtk ruff format --check . # Enforce code formatting
```

**Type Checking:** All Python files MUST pass `ty` (Pyright strict):
```bash
rtk ty check proxbox_cli
```

**Defect Categories Detected:**
- Undefined variables and imports
- Incorrect method/attribute access
- Unused imports and dead code
- Security issues (SQL injection, unsafe eval, XSS vectors)
- Type mismatches (via Pyright strict mode)

**Pre-commit Enforcement:** The pre-commit checklist at the top of this file MUST pass before committing ANY change:
```bash
python -m compileall netbox_proxbox tests
rtk ruff check .
rtk pytest tests/
rtk ty check proxbox_cli
```

### Configuration Control and Change Management

**Configuration Items:** The following are managed under strict change control:
- Plugin version (`netbox_proxbox/__init__.py` `__version__`, `pyproject.toml` version field)
- NetBox compatibility floor (`netbox_proxbox/__init__.py` `min_version` and `max_version`)
- Backend service minimum version (`proxbox_api` version floor in `pyproject.toml` dependencies and CI matrix)
- Plugin models and migrations (all changes require `makemigrations --check --dry-run` validation)
- Backend integration contracts (sync routes, job queue names, SSE payload schemas)

**Change Control Process:**
1. **Before changing a configuration item**, post a comment on the related GitHub issue or PR explaining the change and impact.
2. **After merging**, update the relevant CLAUDE.md file to document the new floor or requirement.
3. **Release notes** MUST include breaking changes to configuration items (e.g., "requires proxbox-api ≥0.0.14").

**Version Management:** Follow PEP 440:
- Use `X.Y.ZrcN` for release candidates (TestPyPI validation only)
- Use `X.Y.Z` for official releases
- Use `X.Y.Z.postN` for bug-fix releases (never `X.Y.Z.devN` or `twine --skip-existing`)

### Pre-Release Verification Checklist

**Before opening a release PR, verify ALL of the following:**

- [ ] All requirements are implemented and verified in code
- [ ] Code passes pre-commit checklist (syntax, lint, tests, type checking)
- [ ] Coverage is ≥85% (`pytest-cov --cov-report=term-missing`)
- [ ] Regression testing passes against E2E Docker stack
- [ ] Changelog (`docs/release-notes/version-X.Y.Z.md`) is complete
- [ ] Architecture documentation (CLAUDE.md files) is updated
- [ ] Backend compatibility (proxbox-api version floor) is documented
- [ ] NetBox compatibility matrix is current (`min_version`, `max_version`)
- [ ] All CI checks are green (GitHub Actions)
- [ ] Integration with latest NetBox official release is confirmed

**After merging to develop**, before creating GitHub release:

- [ ] RC cycle is complete (all TestPyPI validation passed)
- [ ] Merged commit is on `develop` branch
- [ ] Version bumps are finalized (`X.Y.Z`, not `rcN`)
- [ ] Release notes are approved
- [ ] No uncommitted changes remain in the working tree

**During release publishing**:

- [ ] Only use `gh release create` to trigger the publish workflow
- [ ] Never manually push tags with `git push origin vX.Y.Z` (use GitHub release)
- [ ] Monitor CI/CD for successful PyPI and Docker Hub publication
- [ ] Verify dist is live on PyPI before declaring success

---

## How To Navigate

- Start with [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md) for the package-level map.
- Go to `models`, `views`, and `api` first when changing behavior.
- Use `forms`, `filtersets`, and `tables` when changing how plugin objects are edited or listed in NetBox.
- Use `templates` and `static` together when adjusting UI behavior, page structure, or browser-side interactions.
- Check `migrations` before changing any model field or constraint.
- For sync streaming changes, see `views/CLAUDE.md` (SSE proxy), `static/netbox_proxbox/js/CLAUDE.md` (browser SSE parsing), and `templates/netbox_proxbox/CLAUDE.md` (stream URL wiring).

## Index

- [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/api/CLAUDE.md`](./netbox_proxbox/api/CLAUDE.md)
- [`netbox_proxbox/forms/CLAUDE.md`](./netbox_proxbox/forms/CLAUDE.md)
- [`netbox_proxbox/management/CLAUDE.md`](./netbox_proxbox/management/CLAUDE.md)
- [`netbox_proxbox/management/commands/CLAUDE.md`](./netbox_proxbox/management/commands/CLAUDE.md)
- [`netbox_proxbox/migrations/CLAUDE.md`](./netbox_proxbox/migrations/CLAUDE.md)
- [`netbox_proxbox/models/CLAUDE.md`](./netbox_proxbox/models/CLAUDE.md)
- [`netbox_proxbox/schemas/CLAUDE.md`](./netbox_proxbox/schemas/CLAUDE.md)
- [`netbox_proxbox/services/CLAUDE.md`](./netbox_proxbox/services/CLAUDE.md)
- [`netbox_proxbox/static/CLAUDE.md`](./netbox_proxbox/static/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md)
- [`netbox_proxbox/tables/CLAUDE.md`](./netbox_proxbox/tables/CLAUDE.md)
- [`netbox_proxbox/templates/CLAUDE.md`](./netbox_proxbox/templates/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md)
- [`netbox_proxbox/templatetags/CLAUDE.md`](./netbox_proxbox/templatetags/CLAUDE.md)
- [`netbox_proxbox/views/CLAUDE.md`](./netbox_proxbox/views/CLAUDE.md)
- [`netbox_proxbox/views/endpoints/CLAUDE.md`](./netbox_proxbox/views/endpoints/CLAUDE.md)
- [`netbox_proxbox/views/sync_now/CLAUDE.md`](./netbox_proxbox/views/sync_now/CLAUDE.md)
- [`proxbox_cli/CLAUDE.md`](./proxbox_cli/CLAUDE.md)
- [`tests/CLAUDE.md`](./tests/CLAUDE.md)

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
