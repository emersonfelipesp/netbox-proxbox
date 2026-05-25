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

The current plugin config lives in [`netbox_proxbox/__init__.py`](./netbox_proxbox/__init__.py). It declares plugin version `0.0.18.post1` and NetBox compatibility `4.5.8` through `4.6.99` (validated against `4.5.8`, `4.5.9`, `4.6.0`, and official `4.6.1`). The `0.0.18.post1` release is prepared for certification with the separate `proxbox-api` backend release `0.0.14` and adds certification evidence on top of the `0.0.18` PVE 9.2 line: `ProxmoxSdnFabric`, `ProxmoxSdnRouteMap`, `ProxmoxSdnPrefixList`, and `ProxmoxDatacenterCpuModel` models via migration `0041_pve_9_2.py`; automated sync services; completed per-node and per-VM firewall sync; HA arm/disarm action views; and `ProxmoxNode.location`. The previous `0.0.17` release pairs with backend `0.0.13`. `proxbox-api` is not a Python dependency of this plugin; the services communicate over HTTP.

**Companion repos (cross-link map):**

- Backend service: [`emersonfelipesp/proxbox-api`](https://github.com/emersonfelipesp/proxbox-api) — the full v0.0.17 feature set (firewall model scaffolding, intent tag helpers at `PUT /intent/tag-pending-deletion` and `PUT /intent/untag-pending-deletion`, HA REST shim) requires `proxbox-api >= 0.0.13`. HA endpoints alone require `>= 0.0.12`. Firecracker Cloud provisioning uses proxbox-api `/cloud/firecracker/provision` and `/cloud/firecracker/provision/stream` after this plugin creates or exposes the NetBox-side `FirecrackerMicroVM` record. See its [`docs/api/cluster-ha.md`](https://github.com/emersonfelipesp/proxbox-api/blob/main/docs/api/cluster-ha.md) for the upstream HA contract this plugin proxies.
- Workspace context: [`personal-context/claude-reference/netbox-proxbox.md`](https://github.com/emersonfelipesp/personal-context/blob/main/claude-reference/netbox-proxbox.md) — N-MultiCloud workspace-level notes (cross-repo deps, NetBox compatibility rotation policy).

## Architecture Summary

- `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `ProxmoxCluster`, `ProxmoxNode`, `ProxmoxStorage`, `BackupRoutine`, `Replication`, `VMBackup`, `VMSnapshot`, `VMTaskHistory`, and `ProxboxPluginSettings` are the plugin's core Proxmox reflection models.
- Firecracker Cloud uses separate `FirecrackerHostPool`, `FirecrackerHost`, `FirecrackerImageTemplate`, and `FirecrackerMicroVM` models. A micro-VM is not a NetBox core `VirtualMachine`; API clients identify it with `kind="firecracker"` and `instance_ref="firecracker:<id>"`.
- **`NetBoxEndpoint` and `FastAPIEndpoint` are singletons** — the backend proxy and dashboard always use the first row of each, so only one should exist. Their bulk-import views enforce this by prompting for confirmation before replacing an existing record.
- NetBox UI routes live in [`netbox_proxbox/urls.py`](./netbox_proxbox/urls.py) and are implemented primarily in `netbox_proxbox/views/`.
- The plugin also exposes a NetBox plugin API under `netbox_proxbox/api/`, using serializers, filtersets, and standard `NetBoxModelViewSet` classes.
- Sync actions enqueue NetBox background jobs (`ProxboxSyncJob`) on NetBox's default RQ queue and call the external ProxBox FastAPI SSE endpoints to record progress/result on the Job row.
- The dashboard and Job detail pages are extended by template extensions so Proxbox jobs get run-now/cancel controls and live stream/log helpers.
- Browser updates can flow over SSE streams or the existing WebSocket channel.
- Templates and static assets are conventional Django plugin assets under `netbox_proxbox/templates/` and `netbox_proxbox/static/`.
- All three endpoint types support **CSV/JSON/YAML export** (safe and sensitive modes) and **bulk import** with IP auto-creation and id-stripping. See [`netbox_proxbox/views/endpoints/CLAUDE.md`](./netbox_proxbox/views/endpoints/CLAUDE.md).

## Backend integration notes

- **Single FastAPI row:** HTTP and WebSocket helpers such as `get_fastapi_request_context()` in [`netbox_proxbox/services/backend_proxy.py`](./netbox_proxbox/services/backend_proxy.py), `websocket_client`, and several dashboard views resolve the backend via `FastAPIEndpoint.objects.first()` (or the first row from a restricted queryset). If multiple FastAPI endpoints exist, whichever row sorts first is used; plan automation and operator docs accordingly.
- **Background Proxbox sync jobs (RQ):** `ProxboxSyncJob` enqueues on NetBox’s **`default`** RQ queue (`RQ_QUEUE_DEFAULT`) so a stock **`manage.py rqworker`** (no queue arguments) picks them up. NetBox’s default worker only listens to **`high`**, **`default`**, and **`low`**; the extra django-rq queue **`netbox_proxbox.sync`** is legacy only. Older Job rows may still show **`netbox_proxbox.sync`** in **Queue**; cancel/RQ lookup uses the stored name. Jobs call proxbox-api **SSE** via [`run_sync_stream`](./netbox_proxbox/services/backend_proxy.py) until a terminal `complete` event.
- **RQ timeout vs HTTP stream:** NetBox’s default **`RQ_DEFAULT_TIMEOUT`** (often **300s** via `configuration.py`) applies to RQ jobs unless overridden. Long syncs were previously killed by RQ while `requests` was still reading the SSE body. The plugin sets a default **`job_timeout`** of **`PROXBOX_SYNC_JOB_TIMEOUT`** (7200s) in [`ProxboxSyncJob.enqueue`](./netbox_proxbox/jobs.py); pass a larger `job_timeout=` to `enqueue()` if needed. That is separate from the HTTP **between-chunk read** timeout (3600s) inside [`run_sync_stream`](./netbox_proxbox/services/backend_proxy.py).
- **When a job looks “stuck”:** **pending** usually means **no RQ worker** is running (or it does not listen to **`default`**). **running** for a long time usually means proxbox-api is still syncing or the stream is slow/buffered; **errored** with **`JobTimeoutException`** means RQ’s wall-clock limit was hit—increase `job_timeout` or `PROXBOX_SYNC_JOB_TIMEOUT`. Inspect the job **log** and **error** fields before changing code.
- **Cancel on Job detail:** For Proxbox Sync rows in **pending**, **scheduled**, or **running** state, the plugin adds **Cancel job** (POST to `proxbox-cancel`). It requires **delete** permission on the core **Job** model, cancels or stops the linked RQ job when possible, then marks the NetBox job **failed** with a “Cancelled by user.” message. Stopping a **running** job is best-effort (RQ stop + long HTTP reads may not abort instantly).
- **Run now on Job detail:** Shown only when the job is in a **terminal** state (**completed**, **errored**, or **failed**), including after **Cancel** (failed). It is **not** shown for **pending**, **scheduled**, or **running**—use **Cancel** first if a queued run should be abandoned, then **Run now** on the finished row to queue a new sync with the same parameters.
- **Full update (UI vs jobs):** The plugin home may still use non-streaming helpers such as [`sync_full_update_resource`](./netbox_proxbox/services/backend_proxy.py) for JSON/redirect flows. Scheduled or immediate **Proxbox Sync** jobs use **`full-update/stream`** on proxbox-api and execute the full stage chain in one stream: devices, storage, virtual machines, virtual disks, backups, snapshots, network interfaces, IP addresses, VM interfaces, backup routines, and replications.

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
[`0037_pluginsettings_runtime_tunables.py`](./netbox_proxbox/migrations/0037_pluginsettings_runtime_tunables.py)
show the pattern (`SeparateDatabaseAndState` + `IF NOT EXISTS` for production-safe
additive schema changes).

## CI/CD Workflows

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
| `release: published` (GitHub release) | Official `vX.Y.Z` and `vX.Y.Z.postN` | PyPI |

Plain non-rc tag pushes (`vX.Y.Z`, `vX.Y.Z.postN`) **do not** trigger the
publish workflow — the trigger pattern is `v*rc*`, so only rc tags fire it.
This makes the GitHub release creation the **single, authoritative trigger**
for official PyPI publishing and eliminates the duplicate-run problem the
old dual-trigger flow created.

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
