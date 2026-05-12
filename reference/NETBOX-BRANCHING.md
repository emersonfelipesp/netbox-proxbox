# NetBox Branching — Reference

A deep reference on the `netboxlabs-netbox-branching` plugin (v1.0.2). The
plugin adds git-like branching to NetBox: each branch is an isolated
PostgreSQL schema copy of the main database, where users can stage edits
and then merge or revert them.

Source repository checked out at: `/root/personal-context/netbox-branching/`

---

## 1. Overview

| Attribute | Value |
|---|---|
| PyPI name | `netboxlabs-netbox-branching` |
| Python package | `netbox_branching` |
| Version | `1.0.2` |
| NetBox compatibility | `>= 4.4.1, <= 4.6.99` |
| Python | `>= 3.10` (CI also runs 3.12, 3.13, 3.14) |
| License | NetBox Limited Use License 1.0 |
| Maintainer | NetBox Labs, Inc. (`support@netboxlabs.com`) |
| Repository | <https://github.com/netboxlabs/nbl-netbox-branching> |
| Plugin URL prefix | `/branching/` (`base_url = 'branching'`) |

The plugin solves the problem of staging and reviewing changes against the
NetBox source-of-truth without polluting the live database. Users create a
branch, switch into it, make edits as if they were editing main, then sync
(pull from main), merge (push to main), or revert (undo a merge).

Critical install constraint: `netbox_branching` MUST be the **last** entry
in NetBox's `PLUGINS` list. Plugins listed after it will not have their
models enrolled into branching.

---

## 2. Package Metadata

Source: `/root/personal-context/netbox-branching/pyproject.toml`

| Field | Value |
|---|---|
| Build backend | `setuptools` |
| Runtime dependencies | `Django` only (rest comes from NetBox's environment) |
| Dev extras | `check-manifest`, `mkdocs`, `mkdocs-material`, `ruff==0.15.2` |
| Test extras | `coverage`, `pytest`, `pytest-cov` (the suite actually uses Django's runner) |
| Lint config | `/root/personal-context/netbox-branching/ruff.toml` (line length 120, single quotes, `preview = true`) |

`COMPATIBILITY.md` carries the per-release matrix (the 1.0.x line covers
NetBox 4.4.1–4.6.x; older 0.x lines covered NetBox 4.1.0–4.4.x).

---

## 3. Plugin Architecture

Source: `/root/personal-context/netbox-branching/netbox_branching/__init__.py`

```python
class AppConfig(PluginConfig):
    name = 'netbox_branching'
    verbose_name = 'NetBox Branching'
    description = 'A git-like branching implementation for NetBox'
    version = '1.0.2'
    base_url = 'branching'
    min_version = '4.4.1'
    max_version = '4.6.99'
    middleware = ('netbox_branching.middleware.BranchMiddleware',)
    default_settings = { ... }
```

`AppConfig.ready()` performs four startup tasks:

1. **Validate `DATABASES`** is wrapped with `DynamicSchemaDict`; raises
   `ImproperlyConfigured` otherwise.
2. **Validate `DATABASE_ROUTERS`** contains
   `'netbox_branching.database.BranchAwareRouter'`; raises
   `ImproperlyConfigured` otherwise.
3. **Connect connection-cleanup signal handlers**:
   `close_old_branch_connections` is wired to both `request_started` and
   `request_finished` — Django's built-in `close_old_connections()` only
   knows about aliases in `DATABASES.keys()`, which excludes the
   dynamically-synthesised `schema_<id>` aliases (issue #358).
4. **Register the `'branching'` model feature** via
   `register_model_feature('branching', supports_branching)` — this is how
   models opt into branching support.
5. **Load and register branch action validators** declared in
   `PLUGINS_CONFIG['netbox_branching']['<action>_validators']` via
   `Branch.register_preaction_check()`.

`BRANCH_ACTIONS` (from `netbox_branching/constants.py`) drives validator
registration: `sync`, `merge`, `migrate`, `revert`, `archive`.

---

## 4. Core Concept: Branch Lifecycle

A branch is a PostgreSQL schema named `{schema_prefix}{schema_id}`
(default: `branch_<8-char-id>`, e.g. `branch_td5smq0f`). The Django
database alias is `schema_branch_<id>`.

### State machine

```
NEW → PROVISIONING → READY ─┬─ SYNCING ─┐
                            ├─ MIGRATING┤
                            ├─ MERGING  ├─→ READY (back)
                            └─ REVERTING┘
                            
READY → MERGED   (after merge completes)
READY → ARCHIVED (schema dropped)
*     → FAILED   (job failure)
*     → PENDING_MIGRATIONS (after main migrations applied without branch)
```

### Operations

| Operation | What happens |
|---|---|
| **Provision** | Create PostgreSQL schema; for each branchable model, copy the table from main with `CREATE TABLE … LIKE main.<table> INCLUDING INDEXES` and bulk insert with `INSERT INTO … SELECT *`. The `core_objectchange` table is created empty but shares main's ID sequence. The `django_migrations` table is also copied. Indexes are renamed to match main. |
| **Sync** | Replay every `core.ObjectChange` recorded on main since the branch's `last_sync` into the branch schema, in chronological order. DELETEs are handled specially to capture cascade deletions of branch-only child rows. |
| **Merge** | Replay the branch's `core.ObjectChange` log into main using the configured merge strategy. Each replayed change becomes an `AppliedChange` row mapping the change to the branch. |
| **Revert** | Re-apply previously-merged changes in reverse chronological order, calling `ObjectChange.undo()` for each. |
| **Migrate** | Apply pending Django migrations to the branch schema. Migrations for non-branchable models are faked. |
| **Archive** | `DROP SCHEMA … CASCADE` and set status to `ARCHIVED`. |
| **Delete** | Triggers `deprovision()` then model deletion. The currently-active branch cannot be deleted (`validate_branch_deletion` signal receiver). |

### Stale branches

A branch becomes **stale** when its `last_sync` is older than NetBox's
`CHANGELOG_RETENTION` setting. Once stale, the historical
`core.ObjectChange` rows it would need to sync no longer exist, so sync
fails. The plugin setting `stale_warning_threshold` (default 7 days)
surfaces a warning before the cliff is reached.

---

## 5. Database Mechanism

The plugin's two pillars are `DynamicSchemaDict` and `BranchAwareRouter`.

### 5.1 `DynamicSchemaDict`

Source: `/root/personal-context/netbox-branching/netbox_branching/utilities.py`

```python
class DynamicSchemaDict(dict):
    def __getitem__(self, item):
        if type(item) is str and item.startswith('schema_') and (schema := item.removeprefix('schema_')):
            track_branch_connection(item)
            default_config = super().__getitem__('default')
            return {
                **default_config,
                'OPTIONS': {
                    **default_config.get('OPTIONS', {}),
                    'options': f'-c search_path={schema},{self.main_schema}'
                },
            }
        return super().__getitem__(item)
```

It is a `dict` subclass wrapping the `DATABASES` setting. When Django asks
for any alias starting with `schema_`, the dict synthesises a config on
the fly: copies `default`, then sets PostgreSQL `search_path` to
`<branch_schema>,<main_schema>`. Branch aliases never need to be
pre-registered.

`track_branch_connection(item)` records the alias in thread-local storage
so `close_old_branch_connections()` can sweep stale connections beyond
`CONN_MAX_AGE` on `request_started` / `request_finished`.

### 5.2 `BranchAwareRouter`

Source: `/root/personal-context/netbox-branching/netbox_branching/database.py`

```python
class BranchAwareRouter:
    connection_prefix = 'schema_'

    def _get_db(self, model, **hints):
        if not supports_branching(model):
            return None
        if branch := active_branch.get():
            return f'{self.connection_prefix}{branch.schema_name}'
        return None

    def db_for_read(self, model, **hints):
        if model._meta.label == 'core.ObjectChange':
            if branch := active_branch.get():
                return self._get_connection(branch)
            return None
        return self._get_db(model, **hints)

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'netbox_branching':
            return False
        ...
```

Responsibilities:

- Route reads/writes for branchable models to the branch schema when an
  `active_branch` is set; otherwise let Django use `default`.
- `core.ObjectChange` is always routed to the active branch (changelog
  isolation).
- `allow_migrate()` keeps `netbox_branching`'s own migrations off branch
  schemas and gates which models may have migrations applied.

---

## 6. Middleware & Context Variables

### 6.1 ContextVar

Source: `/root/personal-context/netbox-branching/netbox_branching/contextvars.py`

```python
from contextvars import ContextVar
active_branch = ContextVar('active_branch', default=None)
```

A single `ContextVar` propagates the active `Branch` through the request
lifecycle and across `asyncio` chains automatically.

### 6.2 `BranchMiddleware`

Source: `/root/personal-context/netbox-branching/netbox_branching/middleware.py`

For every request not in `EXEMPT_PATHS` (currently just `/api/status/`):

1. Determine the active branch via `get_active_branch(request)`:
   - **UI requests** look at `?_branch=<schema_id>` (sets/changes the
     active branch) and the `active_branch` cookie.
   - **API requests** look at the `X-NetBox-Branch: <schema_id>` header.
2. Attach `request.active_branch` for downstream views.
3. After the response, set, update, or delete the `active_branch` cookie
   (mirroring `SESSION_COOKIE_DOMAIN`, `SESSION_COOKIE_SAMESITE`, etc.).
4. If a branch switch results in a 404 (the object exists in one branch
   but not the other), redirect to the dashboard with an explanatory
   flash message instead of a hard 404.

### 6.3 `ActiveBranchContextManager`

Registered as a NetBox request processor (`utilities.py`):

```python
@register_request_processor
def ActiveBranchContextManager(request):
    if request and request.path not in EXEMPT_PATHS and (branch := get_active_branch(request)):
        return activate_branch(branch)
    return nullcontext()
```

This sets the `active_branch` ContextVar for the duration of the request
so `BranchAwareRouter` routes ORM queries correctly.

### 6.4 Programmatic activation

Source: `utilities.py`

```python
@contextmanager
def activate_branch(branch):
    token = active_branch.set(branch)
    try:
        yield
    finally:
        active_branch.reset(token)
```

`activate_branch()` / `deactivate_branch()` are used by jobs, signal
receivers, and tests to switch branch context outside an HTTP request.

---

## 7. Models

Source: `/root/personal-context/netbox-branching/netbox_branching/models/`

### 7.1 `Branch` (`models/branches.py`)

Inherits `JobsMixin` + `PrimaryModel`.

| Field | Type | Notes |
|---|---|---|
| `name` | `CharField(100)` | Unique |
| `owner` | `FK(User)` | Nullable; `SET_NULL` |
| `schema_id` | `CharField(8)` | Unique, auto-generated, read-only |
| `status` | `CharField` | `BranchStatusChoices` (see § 4) |
| `applied_migrations` | `ArrayField` | Migrations already applied to the branch schema |
| `last_sync` | `DateTimeField` | When the branch was last synced from main |
| `merged_time` | `DateTimeField` | When the branch was merged |
| `merged_by` | `FK(User)` | Who merged the branch |
| `merge_strategy` | `CharField` | `iterative` (default) or `squash` |

Custom permissions (added in migration `0008`): `sync_branch`,
`merge_branch`, `migrate_branch`, `revert_branch`, `archive_branch`.

Key properties: `ready`, `merged`, `is_active`, `schema_name`,
`connection_name`, `is_stale`, `stale_warning`, `pending_migrations`,
`can_sync`, `can_merge`, `can_merge_now`, `can_revert`, `can_archive`,
`can_delete`.

Key methods: `provision()`, `sync()`, `merge()`, `revert()`, `migrate()`,
`archive()`, `deprovision()`, `get_changes()`, `get_unsynced_changes()`,
`get_unmerged_changes()`, `get_merged_changes()`,
`register_preaction_check()`.

### 7.2 `BranchEvent` (`models/branches.py`)

| Field | Type | Notes |
|---|---|---|
| `time` | `DateTimeField` | `auto_now_add` |
| `branch` | `FK(Branch)` | `CASCADE`, `related_name='events'` |
| `user` | `FK(User)` | Nullable |
| `type` | `CharField` | `BranchEventTypeChoices`: `provisioned`, `synced`, `migrated`, `merged`, `reverted`, `archived` |

### 7.3 `ObjectChange` proxy (`models/changes.py`)

Proxies NetBox's built-in `core.ObjectChange`. Adds three methods used by
the merge strategies:

- `apply(branch, using, logger, skip_missing)` — replay a change.
  CREATE → deserialize + save; UPDATE → load + apply diff; DELETE → load
  + delete.
- `undo(branch, using, logger)` — reverse a change. CREATE → delete;
  UPDATE → restore pre-state; DELETE → restore object.
- `migrate(branch, revert)` — run data migrators for schema evolution.

### 7.4 `ChangeDiff` (`models/changes.py`)

Records three-way diffs per object for conflict detection.

| Field | Type | Notes |
|---|---|---|
| `branch` | `FK(Branch)` | `CASCADE` |
| `object_type` | `FK(ContentType)` | `PROTECT` |
| `object_id` | `PositiveBigIntegerField` |  |
| `action` | `CharField` | `create` / `update` / `delete` |
| `original` | `JSONField` | Object state at branch creation |
| `modified` | `JSONField` | Current state in the branch |
| `current` | `JSONField` | Current state in main |
| `conflicts` | `ArrayField` | Field names where branch and main diverge |

A field is in `conflicts` when `original`, `modified`, and `current` all
differ from each other (true three-way conflict).

### 7.5 `AppliedChange` (`models/changes.py`)

One-to-one mapping of `core.ObjectChange` → `Branch`. Used to exclude
already-applied changes from sync.

---

## 8. Merge Strategies

Source: `/root/personal-context/netbox-branching/netbox_branching/merge_strategies/`

### 8.1 Abstract base — `strategy.py`

```python
class MergeStrategy(ABC):
    revert_changes_ordering = '-time'

    @abstractmethod
    def merge(self, branch, changes, request, logger, user): ...
    @abstractmethod
    def revert(self, branch, changes, request, logger, user): ...

    def _clean(self, models):
        # Rebuild MPTT trees for hierarchical models post-merge.
```

### 8.2 `IterativeMergeStrategy` — `iterative.py` (default)

Replays each `ObjectChange` row one at a time in chronological order.
Simple, easy to debug, but can fail on duplicate-object conflicts. Revert
applies `undo()` in reverse chronological order.

### 8.3 `SquashMergeStrategy` — `squash.py`

Collapses all per-object changes into a single `CollapsedChange` before
applying:

- `CREATE + DELETE = SKIP` (object created and deleted within the branch
  → nothing to merge).
- `CREATE + UPDATE+ = CREATE` (final state).
- `UPDATE+ + DELETE = DELETE`.

Then uses **Kahn's algorithm** to topologically sort `CollapsedChange`s
respecting FK dependencies:

1. DELETEs first.
2. UPDATEs next.
3. CREATEs last.

Bidirectional FK cycles are broken by splitting a CREATE into a CREATE
with the cyclic FK set to NULL plus a follow-up UPDATE that fills the FK.
Revert applies `undo()` in reverse dependency order.

---

## 9. Migrations

Source: `/root/personal-context/netbox-branching/netbox_branching/migrations/`

| File | Purpose |
|---|---|
| `0001_initial.py` | Create `Branch`, `BranchEvent`, `ChangeDiff`, `AppliedChange` |
| `0002_branch_schema_id_unique.py` | Unique constraint on `Branch.schema_id` |
| `0003_rename_indexes.py` | Index naming consistency fix |
| `0004_copy_migrations.py` | Provisioning now also copies the `django_migrations` table |
| `0005_branch_applied_migrations.py` | Add `Branch.applied_migrations` `ArrayField` |
| `0006_tag_object_types.py` | Register branch models with NetBox's ObjectType system |
| `0007_branch_merge_strategy.py` | Add `Branch.merge_strategy` |
| `0008_branch_custom_permissions.py` | Add `sync/merge/migrate/revert/archive_branch` permissions |

Migrations are sequential (no squashing). Data migrations use
`apps.get_model(...)` and `get_or_create(...)` because `ContentType`
rows may not exist at migration time.

---

## 10. REST API

Source: `/root/personal-context/netbox-branching/netbox_branching/api/urls.py`,
`netbox_branching/api/views.py`

Mounted at `/api/plugins/branching/`.

| Endpoint | ViewSet | Description |
|---|---|---|
| `branches/` | `BranchViewSet` | Full CRUD for `Branch` |
| `branches/<id>/sync/` | `@action POST` | Enqueue `SyncBranchJob` |
| `branches/<id>/merge/` | `@action POST` | Enqueue `MergeBranchJob` |
| `branches/<id>/revert/` | `@action POST` | Enqueue `RevertBranchJob` |
| `branches/<id>/archive/` | `@action POST` | Synchronously archive a merged branch |
| `branch-events/` | `BranchEventViewSet` | Read-only list / retrieve |
| `changes/` | `ChangeDiffViewSet` | Read-only list / retrieve |
| `branchable-models/` | `BranchableModelViewSet` | List models that support branching |

Body conventions:

- `"acknowledge_conflicts": true` — required to merge or sync when
  unacknowledged conflicts exist; otherwise the endpoint returns
  HTTP 409 with a `conflicts` list of three-way diffs.
- `"commit": false` — dry-run; the underlying transaction is rolled back
  at the end of the job.

To target a branch with any standard NetBox API request, send the header:

```
X-NetBox-Branch: <schema_id>
```

---

## 11. UI Views & Templates

Source: `/root/personal-context/netbox-branching/netbox_branching/views.py`,
`netbox_branching/urls.py`,
`netbox_branching/templates/netbox_branching/`

Main URL prefix: `/branching/`.

Top-level views:

- `BranchListView` — `/branching/branches/`
- `BranchEditView` — `/branching/branches/add/`
- `BranchBulkImportView` — `/branching/branches/import/`
- `BranchBulkEditView` — `/branching/branches/edit/`
- `BranchBulkDeleteView` — `/branching/branches/delete/`
- `BranchBulkMigrateView` — `/branching/branches/migrate/`
- Per-branch: detail, edit, delete (registered through
  `get_model_urls()`)
- `ChangeDiffListView` — `/branching/changes/`
- `ChangeDiff` detail view (registered through `get_model_urls()`)

Templates of note (under `templates/netbox_branching/`):

| Template | Purpose |
|---|---|
| `branch.html` | Branch detail |
| `branch_action.html` | Generic action confirmation (sync/merge/revert) |
| `branch_archive.html` | Archive confirmation |
| `branch_bulk_migrate.html` | Bulk migrate form |
| `branch_job_report.html` | Post-action job result |
| `branch_migrate.html` | Single-branch migrate form |
| `changediff.html` | Three-way diff display |
| `buttons/branch_*.html` | Per-action buttons (sync, merge, revert, archive, migrate) |
| `inc/branch_selector.html` | Branch selector widget injected globally |
| `inc/modified_notice.html` | Banner shown on objects modified in the active branch |
| `inc/share_button.html` | Copy a branch-aware URL |
| `inc/script_alert.html` | Script execution warning |

`netbox_branching/template_content.py` registers
`PluginTemplateExtension` hooks that inject the branch selector and
modification-notice banners into NetBox's base templates.

---

## 12. Jobs & Signals

### 12.1 Background jobs

Source: `/root/personal-context/netbox-branching/netbox_branching/jobs.py`

All inherit NetBox's `JobRunner` base class and run in Redis-backed RQ
workers.

| Job | Trigger | Honours `job_timeout` |
|---|---|---|
| `ProvisionBranchJob` | `Branch.save()` for new branches | No |
| `SyncBranchJob` | UI / API sync action | Yes (default 3600 s) |
| `MergeBranchJob` | UI / API merge action | Yes |
| `RevertBranchJob` | UI / API revert action | Yes |
| `MigrateBranchJob` | UI / API migrate action | No |

`SyncBranchJob` temporarily disconnects NetBox's `handle_changed_object`
signals so synthetic sync changes don't pollute the changelog.
`MergeBranchJob` snapshots a `changes_summary` (per-model
create/update/delete counts) before running and stashes it on the job for
the post-action report UI.

### 12.2 Lifecycle signals

Source: `/root/personal-context/netbox-branching/netbox_branching/signals.py`

Plain `django.dispatch.Signal` instances for every operation, available
to third-party plugins:

`pre_provision` / `post_provision`, `pre_deprovision` / `post_deprovision`,
`pre_sync` / `post_sync`, `pre_migrate` / `post_migrate`,
`pre_merge` / `post_merge`, `pre_revert` / `post_revert`.

### 12.3 Signal receivers

Source: `/root/personal-context/netbox-branching/netbox_branching/signal_receivers.py`

| Receiver | Connected to | Purpose |
|---|---|---|
| `record_change_diff` | `post_save` on `core.ObjectChange` | Maintain `ChangeDiff` rows for conflict tracking |
| `validate_branching_operations` | `post_clean` | Block edits to objects that have been deleted in main |
| `validate_branch_deletion` | `pre_delete` on `Branch` | Block deletion of branches in transitional status |
| `check_pending_migrations` | `post_migrate` | Mark branches as `PENDING_MIGRATIONS` after main migrations apply |
| `handle_branch_event` | `post_provision/sync/merge/revert/deprovision` | Fire NetBox `EventRule` rules for branch lifecycle |

### 12.4 Custom event types

Source: `/root/personal-context/netbox-branching/netbox_branching/events.py`

Registers NetBox `EventType` objects: `BRANCH_PROVISIONED`,
`BRANCH_DEPROVISIONED`, `BRANCH_SYNCED`, `BRANCH_MERGED`,
`BRANCH_REVERTED`. Also exports `add_branch_context()` — a function
suitable for `EVENTS_PIPELINE` that injects the active branch into event
payloads.

---

## 13. Plugin Settings

Configured in NetBox's `PLUGINS_CONFIG['netbox_branching']`. Defaults
come from `default_settings` in
`/root/personal-context/netbox-branching/netbox_branching/__init__.py`.

| Key | Default | Description |
|---|---|---|
| `max_working_branches` | `None` | Max non-merged/non-archived branches at once |
| `max_branches` | `None` | Max simultaneously provisioned branches |
| `exempt_models` | `[]` | Other-plugin models to exclude from branching |
| `main_schema` | `'public'` | PostgreSQL schema for the main database |
| `schema_prefix` | `'branch_'` | Prefix prepended to `schema_id` for the schema name |
| `job_timeout` | `3600` | Max seconds for sync / merge / revert jobs |
| `sync_validators` | `[]` | Import paths of pre-sync validator callables |
| `merge_validators` | `[]` | Import paths of pre-merge validator callables |
| `migrate_validators` | `[]` | Import paths of pre-migrate validator callables |
| `revert_validators` | `[]` | Import paths of pre-revert validator callables |
| `archive_validators` | `[]` | Import paths of pre-archive validator callables |
| `stale_warning_threshold` | `7` | Days before staleness at which to show a warning |

A validator is a callable
`def my_validator(branch) -> BranchActionIndicator` where
`BranchActionIndicator` is a dataclass with `permitted: bool` and
`message: str`.

### Required NetBox configuration

In `netbox/netbox/configuration.py`:

```python
from netbox_branching.utilities import DynamicSchemaDict

DATABASES = DynamicSchemaDict({
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'netbox',
        # ...
    },
})

DATABASE_ROUTERS = ['netbox_branching.database.BranchAwareRouter']

# Optional but recommended for event-rule integration:
EVENTS_PIPELINE = [
    'netbox_branching.events.add_branch_context',
    'extras.events.process_event_queue',
]
```

The plugin entry must be the last item in `PLUGINS`.

---

## 14. Compatibility & Limitations

### 14.1 Hard-coded exempt models

Source: `/root/personal-context/netbox-branching/netbox_branching/constants.py`

Branching is disabled for these models even if they use
`ChangeLoggingMixin`:

- All `core.*` models
- `extras.branch`, `extras.customfield`, `extras.customfieldchoiceset`,
  `extras.customlink`, `extras.eventrule`, `extras.exporttemplate`,
  `extras.notificationgroup`, `extras.savedfilter`, `extras.webhook`
- All `netbox_branching.*` and `netbox_changes.*` models

### 14.2 Always-replicated non-changelogged models

These tables don't use `ChangeLoggingMixin` but are still copied during
provisioning so referential integrity holds inside a branch:

- `dcim.cablepath`, `dcim.portmapping`, `dcim.porttemplatemapping`
- `extras.cachedvalue`, `extras.taggeditem`
- `tenancy.contactgroupmembership`

### 14.3 Known incompatibilities

From `docs/plugin-development.md`:

- **Multi-table inheritance** is not supported and will fail during
  provisioning.
- **Models that don't use `ChangeLoggingMixin`** are silently excluded
  from branching; changes to them in a branch leak into main.
- **Plugin order matters**: any plugin listed after `netbox_branching`
  in `PLUGINS` will not have its models enrolled in branching.
- **Plugin upgrades** while open branches exist can leave those
  branches missing new migrations. Merge or remove branches before
  upgrading other plugins.

### 14.4 Known limitations

From `docs/index.md`:

- Branches may not survive minor NetBox version upgrades because schema
  migrations are not always applied to branch schemas.
- Open branches do not reflect newly installed plugins.

### 14.5 Unrecoverable merge scenario

Editing an object in a branch that has been deleted in main produces an
unrecoverable merge — the UPDATE cannot apply to a non-existent row.
`validate_branching_operations` blocks the interactive case, but a sync
that pulls in a delete from main while the branch already has an edit
puts the branch in this state. Recovery options are revert or archive.

---

## 15. Tests

Source: `/root/personal-context/netbox-branching/netbox_branching/tests/`

The suite uses Django's `TestCase` (not pytest) and a real PostgreSQL
database — no mocking. Run from a NetBox checkout that has this plugin
installed and `testing/configuration.py` linked in:

```bash
python netbox/manage.py test netbox_branching.tests --keepdb
```

`--keepdb` keeps the test DB and provisioned branch schemas between runs,
which is important for speed.

| Module | Coverage |
|---|---|
| `test_api.py` | REST CRUD, sync/merge/revert/migrate/archive actions, conflict 409 |
| `test_branches.py` | Branch model lifecycle and status transitions |
| `test_changediff.py` | Three-way diff and conflict detection |
| `test_config.py` | Plugin configuration validation |
| `test_connection_lifecycle.py` | Branch DB connection cleanup |
| `test_events.py` | `BranchEvent` creation across operations |
| `test_filtersets.py` | `BranchFilterSet`, `BranchEventFilterSet`, `ChangeDiffFilterSet` |
| `test_iterative_merge.py` | Iterative merge (creates, updates, deletes, conflicts) |
| `test_query.py` | Branch-aware ORM query routing |
| `test_related_models.py` | FK / M2M handling across branch and main schemas |
| `test_request.py` | Request-level branch activation (header / cookie / query) |
| `test_squash_merge.py` | Squash merge (dependency ordering, FK cycles) |
| `test_sync.py` | Sync (cascade deletes, stale branches, conflict recording) |
| `test_upgrade.py` | NetBox upgrade scenarios |
| `test_views.py` | UI HTTP responses |

Test fixtures live in `tests/fixtures/`; shared helpers in `tests/utils.py`.

---

## 16. Docs Layout

Source: `/root/personal-context/netbox-branching/docs/`

Built with `mkdocs` + `mkdocs-material` (preview with `mkdocs serve`).

| File | Content |
|---|---|
| `index.md` | Introduction, terminology, full installation guide, known limitations |
| `using-branches/creating-a-branch.md` | UI walkthrough |
| `using-branches/syncing-merging.md` | Sync / merge workflows, conflicts, squash recovery |
| `using-branches/reverting-a-branch.md` | Revert workflow |
| `best-practices.md` | Architecture rationale, recoverable / unrecoverable scenarios |
| `plugin-development.md` | Other-plugin author guide: model compatibility, `exempt_models`, validators, migration `fake_on_branch` flag, install order |
| `netbox-docker.md` | NetBox Docker-specific instructions |
| `rest-api.md` | API guide with curl examples and conflict handling |
| `configuration.md` | Every plugin setting documented |
| `event-rules.md` | EventRule integration and `EVENTS_PIPELINE` |
| `models/branch.md` | `Branch` model reference |
| `models/branchevent.md` | `BranchEvent` reference |
| `models/changediff.md` | `ChangeDiff` reference |
| `models/objectchange.md` | `ObjectChange` proxy reference |
| `changelog.md` | Version history |

---

## 17. Agent Guidance

`/root/personal-context/netbox-branching/CLAUDE.md` is a single-line shim
(`@./AGENTS.md`). The authoritative agent guide is
`/root/personal-context/netbox-branching/AGENTS.md`. It covers:

- Repository overview, tech stack, full repo map
- Architecture (database isolation, context management, branch lifecycle,
  merge strategies, change tracking, signals, validators)
- Development commands and reproducible setup steps (mirrors CI)
- Testing guidance (`TestCase`, real PostgreSQL, `--keepdb`)
- CI/CD workflows (`lint-tests.yaml`, `release.yaml`, `claude.yaml`)
- Common-task recipes: add a model / API endpoint / validator, bump
  NetBox version, cut a release
- Conventions and patterns
- Troubleshooting guide for common errors

When working in this repo, prefer `AGENTS.md` over reverse-engineering the
codebase.

---

## 18. Why This Reference Lives in `netbox-proxbox/reference/`

The Proxbox stack (`netbox-proxbox` + `proxbox-api`) writes large numbers
of objects into NetBox during sync. Branching is interesting to Proxbox
in two ways:

1. **Staging sync runs in a branch** — provisioning a branch before a
   bulk Proxmox→NetBox sync would let operators review the proposed
   diffs (`ChangeDiff`) before merging into main. This requires that all
   Proxbox plugin models use `ChangeLoggingMixin` (they do) and are not
   listed in `exempt_models`.
2. **Plugin install order** — `netbox_branching` must be the **last**
   entry in `PLUGINS`, so any deployment running `netbox_proxbox`
   alongside `netbox_branching` must keep `netbox_proxbox` listed
   first.

If Proxbox ever pursues branch-staged sync, the Proxbox-side work would
likely consist of: ensuring its singletons (`NetBoxEndpoint`,
`FastAPIEndpoint`, `ProxboxPluginSettings`) are listed in `exempt_models`
(they are not branch-meaningful), and verifying that bulk-sync jobs
respect `request.active_branch` end-to-end (currently they call NetBox
through `proxbox-api` which uses its own session, so a branch header
would have to be plumbed through deliberately).

---

## Quick Reference: File Anchors

| Concern | File |
|---|---|
| Plugin config | `netbox_branching/__init__.py` |
| Schema dict | `netbox_branching/utilities.py` (`DynamicSchemaDict`) |
| Database router | `netbox_branching/database.py` (`BranchAwareRouter`) |
| Active branch context | `netbox_branching/contextvars.py` |
| Request middleware | `netbox_branching/middleware.py` |
| Branch / BranchEvent | `netbox_branching/models/branches.py` |
| ObjectChange / ChangeDiff / AppliedChange | `netbox_branching/models/changes.py` |
| Merge strategies | `netbox_branching/merge_strategies/{strategy,iterative,squash}.py` |
| Background jobs | `netbox_branching/jobs.py` |
| Lifecycle signals | `netbox_branching/signals.py` |
| Signal receivers | `netbox_branching/signal_receivers.py` |
| Event types / pipeline | `netbox_branching/events.py` |
| REST routing | `netbox_branching/api/urls.py` |
| UI views | `netbox_branching/views.py` |
| Hard-coded exempt models | `netbox_branching/constants.py` |
| Migrations | `netbox_branching/migrations/0001…0008` |
| Test config | `testing/configuration.py` |
| Agent guide | `AGENTS.md` (`CLAUDE.md` shims to it) |
| Compatibility matrix | `COMPATIBILITY.md` |
| Package metadata | `pyproject.toml` |
