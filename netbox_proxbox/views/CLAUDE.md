# `netbox_proxbox.views`

> **Repository destination guardrail:** This guide inherits the hard rule in
> the repository-root `CLAUDE.md`. EdgeUno and the local EdgeUno vendor
> submodule are read-only reference sources, never change destinations. All
> development writes must target exactly
> `https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox.git`; approved
> public promotion may target only
> `https://github.com/emersonfelipesp/netbox-proxbox.git`. Never mutate EdgeUno
> issues, PRs, branches, commits, tags, releases, packages, mirrors, or
> deployments, and never configure EdgeUno as a writable remote, upstream,
> fallback, or PR base.

This directory implements the plugin's NetBox UI behavior, including dashboard pages, endpoint CRUD views, sync actions, job integration, and status utilities.

The storage detail page routes live per-node content discovery through one
process-wide four-thread/four-slot pool in `storage_content.py`. A slot is
reserved before submission and is released only by the worker after the HTTP
call actually exits, so page deadlines never turn abandoned requests into an
unbounded collection of authenticated sockets or threads. A page waits only
until its absolute eight-second deadline; if the shared pool remains full, the
unstarted nodes use the existing partial-result notice. Each node response is
streamed under the same absolute deadline and capped at 1 MiB of decoded bytes
before JSON parsing. The deadline watchdog never closes a Requests/urllib3
response object: buffered response closure can wait behind the read it is meant
to cancel. Each request instead owns a dedicated urllib3 pool whose connection
hook duplicates the TCP socket immediately after connect, before TLS and
response-header reads. At the deadline the watchdog performs only raw
`socket.shutdown(SHUT_RDWR)` plus `socket.close()` on that duplicate, which
interrupts header and body reads without letting one cancellation block later
deadlines. The worker closes the response and pool only after the interrupted
read returns. The page still fetches at most 64 membership nodes, and a node
counts as successful only when the outer payload is a list/object and every
flattened content record has a non-empty `volid`; error envelopes and
permissive-schema dictionaries are partial failures. Large storage memberships
must produce explicit partial/truncation context rather than serially occupying
a web worker for `node_count * request_timeout` seconds, allocating one future
per node, or issuing an authenticated request for every membership entry.

## Files And Ownership

- [`jobs.py`](./jobs.py): `ProxboxJobListView` / `ProxboxJobTable` — the
  Proxbox-only view of core `Job`, mounted at `/plugins/proxbox/jobs/` and
  targeted by the **Sync Jobs** menu entry. It subclasses core's `JobListView`
  and `JobTable` rather than rebuilding them, so NetBox's own filterset, filter
  form, and export action stay in step; the only overrides are the queryset
  (`Job.objects.defer("data").filter(proxbox_sync_job_q())`), the added
  `bug_report` column, and dropping `BulkDelete` (its success redirect returns
  to `core:job_list`, bouncing the operator off the plugin page).

  Two constraints are easy to undo. `defer("data")` composes with the filter's
  `data__has_key` lookup — deferral shapes the `SELECT`, the lookup is a `WHERE`
  — so the JSON payload stays queryable without being fetched per row; and the
  `bug_report` column **links to the job detail page instead of rendering the
  modal**, because `build_bug_report_context()` needs `data` and `log_entries`,
  which would defeat the deferral and emit one modal plus one inline script for
  every row on the page.


- [`__init__.py`](./__init__.py): top-level page views and re-exports for endpoint views, cluster views, dashboard pages, sync enqueue actions, status checks, settings/storage views, backup/replication views, snapshot/task views, and job integration helpers.
- [`backend_sync.py`](./backend_sync.py): shared helper that ensures a Proxmox endpoint is synchronized to proxbox-api before live reads, including TLS verification and concrete request tuning resolved by `ProxmoxEndpoint.effective_connection_tuning()`; nullable inheritance markers must never cross this wire boundary as JSON `null`. Also exposes `list_backend_netbox_endpoints()`, whose return type is deliberately **three-way**: `(rows, None)` on success (an empty list is a real, trustworthy answer — the backend holds nothing), and `(None, error)` when the call itself failed. Callers must not collapse those two cases — `None` means *unknown*, and the sync-job preflight only escalates to a fatal error on a confirmed empty list. `list_backend_proxmox_endpoints()` is its Proxmox-side twin with the same contract; the preflight calls it **once** and feeds the rows to every push through `sync_proxmox_endpoint_to_backend(..., existing_endpoints=…)`, so a slow backend is not re-listed per endpoint. All four helpers share the same `BACKEND_ENDPOINT_PUSH_TIMEOUT` default so a cold backend cannot fail one call and pass another. `PREFLIGHT_ENDPOINT_PUSH_BUDGET` (600 s) is a **soft** wall-clock cap: past it the preflight only skips endpoints whose backend row is already **current**, decided by `backend_holds_proxmox_endpoint(endpoint, existing_endpoints)`. "Held" alone is not the question — skipping is only free when the push would have been a no-op refresh, so that helper locates the row by `proxmox_backend_name()` (the same name the push itself matches on, so the two cannot drift) and then runs `_proxmox_row_is_current()`: the resolved connection target must match, and the eight pushed fields the backend both stores and returns (`username`, `enabled`, `access_methods`, `allow_packer_template_builds`, `verify_ssl`, `timeout`, `max_retries`, `retry_backoff`) must agree, and finally the **credentials** must still match the fingerprint the last successful push recorded. That last comparison is local, because `ProxmoxEndpointPublic` withholds `password`/`token_name`/`token_value`: a secret rotated *in place* — same host, same username, same access methods — produces a backend row byte-identical to a current one, and skipping that push would leave proxbox-api authenticating with the credential the operator has just revoked. `proxmox_credential_fingerprint(payload)` is the NetBox fingerprint's Proxmox twin — same `salted_hmac` construction over the three credential keys the push payload carries, under a **distinct salt** so the two namespaces can never compare equal — recorded on `ProxmoxEndpoint.pushed_credential_fingerprint` (migration 0074) by `_record_pushed_proxmox_credential_fingerprint()` with the same `queryset.update()`-never-`save()` and caught-`DatabaseError` rules as the NetBox writer. `proxmox_push_credentials_unchanged(endpoint, payload)` takes the already-materialised payload rather than deriving one, because its sole caller has just built it for the field comparisons — no reason to decrypt the same secrets twice. **It fails closed in the opposite direction from the NetBox twin, deliberately**: the NetBox fingerprint gates a *fatal* preflight case, so unknown there blocks the run; this one gates only whether the soft budget may *skip* a push, so an empty or stale fingerprint reads as "push again" — one extra request, bounded by the hard ceiling, which self-clears because that push records the fingerprint. A row whose target or configuration has drifted is **not** skipped, because the soft budget would otherwise preserve exactly the stale row `resolve_backend_endpoint_ids()` then refuses to sync against — turning a merely slow backend into a blocked endpoint. `timeout` / `max_retries` / `retry_backoff` are included because `ProxmoxEndpointPublic` returns them as canonical `int` / `int` / `float` values and drift changes live request behavior; a globally inherited timeout change must remain push-required after the soft budget. Only site/tenant display metadata is excluded. A false "not current" costs one extra push, bounded by the hard ceiling. `None` (the listing call itself failed) is treated as *not held* — unknown must never be the reason an endpoint is skipped into a fatal error. An endpoint the backend has never seen is pushed **regardless** of the budget, because skipping it leaves it without a backend wire id and the stage loop then fails the whole job. `PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING` (1800 s) is the real stop: past it every remaining endpoint is skipped, held or not. `backend_holds_netbox_endpoint(endpoint, existing_endpoints)` is the NetBox-side identity check, and it is **not** a name match like its Proxmox twin: proxbox-api stores the NetBox endpoint as a *singleton* updated by position, and the NetBox payload's `name` is free text with no embedded pk, so a stored row's name says nothing about whose credentials it holds. It compares the **resolved connection target** instead — `_netbox_connection_target()` returns `(domain or ip_address)` (case-folded, trailing dot stripped, mask stripped on `/`), mirroring proxbox-api's own `NetBoxEndpoint.url` property (`host = domain if domain else ip_address`) — plus `port`, which **both** sides must report and which must be equal. Both sides must resolve a target, and the two targets must be equal. Comparing the *resolved target* rather than each field in turn is what makes this exact in both directions; the earlier field-by-field rule ("every field both sides declare must agree, and at least one must positively match") was wrong twice over. It **accepted** rows it should not: a stored row blank on `domain` at our IP is a NetBox reached *by address*, which is a different service from ours reached by vhost name at that address — a blank stored field is data, not a gap — and the mirror case, a stored row naming *another* domain at our IP while we are IP-only, dials their vhost. It also **rejected** rows it should not: with a domain set the backend never dials the address, so our own record whose stored IP has since changed is still ours. `port` is required rather than best-effort because proxbox-api declares it non-optional on `NetBoxEndpointResponse` and `GET /endpoint` returns `list[NetBoxEndpointResponse]` — a row without one is not something this backend produced. It returns `False` for an empty/`None` list, a list holding **more than one** row, a row with no resolvable host, a different target, or a missing/unparseable port. **The wanted values come from `_netbox_endpoint_identity()`, which reads the model — deliberately *not* from `_netbox_endpoint_backend_payload()`.** That payload substitutes `"127.0.0.1"` when the row has no linked IP so the backend still has something to dial, so every domain-only NetBox pushes the same loopback string; treating it as identity let one domain-only instance match another's stored record on the fallback alone. Only an explicitly configured IP is evidence here. **Identity is not currency, and the helper requires both.** `_netbox_row_is_current()` additionally compares `verify_ssl` and `token_version` — two of the fields the push body carries — so a row that names this NetBox but predates a TLS hardening or a token-scheme rotation is *not held*: continuing would let proxbox-api write with the posture the operator has since replaced. Those wanted values are also read straight off the model rather than through `_netbox_endpoint_backend_payload()`, which warns and materialises the API token merely to answer a comparison. A **missing** `verify_ssl` or `token_version` reads as drifted, unlike the Proxmox-side twin: a `False` here blocks the run, so unknown must fail closed. The comparable set is bounded by `NetBoxEndpointResponse`, which returns `id, name, ip_address, domain, port, token_version, verify_ssl, enabled` and withholds `token`/`token_key` — so a token rotated **in place**, under an unchanged `token_version`, is invisible to a comparison against what the backend gives back. **That residual is closed locally instead**, by `netbox_push_credentials_unchanged()`: every push that proxbox-api *accepts* records `netbox_credential_fingerprint(payload)` — a `salted_hmac(…, algorithm="sha256")` over `token_version`/`token_key`/`token` encoded length-prefixed by `_fingerprint_material()` (injective for any field content — a plain separator can be defeated by a field that contains it), keyed off NetBox's `SECRET_KEY`, so it is non-reversible and not comparable across installs — into `NetBoxEndpoint.pushed_credential_fingerprint` (migration 0073). A later *failed* push can then tell "the backend holds the credentials we last sent" from "the backend holds credentials NetBox has since replaced", with no secret ever leaving this install and nothing new asked of proxbox-api. Three details are load-bearing. It fingerprints the **payload**, not the model fields, because the payload is literally what the backend was handed (same reasoning as locating the Proxmox row by `proxmox_backend_name()`). It writes with `type(endpoint).objects.filter(pk=pk).update(...)`, never `save()` — `NetBoxEndpoint` has a `post_save` handler that pushes to the backend, so saving from inside the push would re-enter it — and a write failure is logged, not raised, since the push itself succeeded and a missing fingerprint only makes the *next* failed push fail closed (`DatabaseError` is caught specifically, which covers the `ProgrammingError` from an unapplied 0073). And an empty stored fingerprint reads as **changed**, covering both a never-pushed endpoint and the upgrade window where the column exists but nothing has written it yet; the operator clears that by re-running once proxbox-api is reachable. Unlike `_netbox_row_is_current()` it *must* materialise the token to answer at all, which is why it runs only on the already-failed push path. `name` is returned but not compared: it is free text, and a rename must not hard-fail a safe run. **The singleton is positional, so more than one row is refused outright** — whatever those rows say. The push overwrites entry `[0]` and entry `[0]` is what proxbox-api dials, so a match found further down would vouch for a row the backend is not using while a stale record ahead of it, possibly another NetBox's, drives the sync: the same cross-instance write the identity check exists to stop, reached by counting rows instead of by reading the wrong one. Reduced to the one position the backend dials, the loop asks identity and currency of the row that actually matters, and a current row belonging to a *different* NetBox cannot rescue our own drifted one. The sync-job preflight uses this to tell a *transient refresh failure over our own current credentials* (warn, continue) from *proxbox-api is pointed at a different NetBox, or at ours under superseded trust settings* (block). See the preflight blockquote in [`../CLAUDE.md`](../CLAUDE.md).

> **Identity correction:** any earlier wording in this section that describes
> full `proxmox_backend_name()` equality is historical. Current code matches the
> immutable `(nb:<pk>)` suffix, requires exactly one claim, and treats missing
> `enabled` or `allow_packer_template_builds` currency fields as stale.
> Duplicate suffix claims are revoked best-effort across every identifiable
> row even when an earlier PUT fails; the aggregated refusal names all failed
> backend row IDs and still requires operator cleanup.
>
> **A located Proxmox row is not automatically a usable one.**
> `resolve_backend_endpoint_id()` and `resolve_backend_endpoint_ids()` both route
> through `_resolve_backend_row_id()`, which requires exactly one row ending in
> the immutable `(nb:<pk>)` suffix. Mutable display-name prefixes are ignored;
> duplicate claims fail closed. It then confirms the row still **dials the same
> service**. The suffix proves the row was created for this pk; it says nothing
> about where that row now points.
>
> That gap is reachable, not theoretical. The endpoint push happens in the sync
> preflight, where a *failure* is only warned about. Retarget a `ProxmoxEndpoint`
> in NetBox, have that push fail, and the backend still holds the **previous**
> host under this endpoint's name — so syncing through that id reflects the old
> Proxmox host's inventory into NetBox under the new endpoint. The singular
> resolver matters as much as the batch one: the Templates tab and the
> create-instance wizard both go through it, so a stale row would list one host's
> templates and provision onto another.
>
> Identity is the **resolved connection target**, `_proxmox_connection_target()` →
> `(domain or ip_address)` plus `port`, mirroring proxbox-api's own
> `ProxmoxEndpoint.host` property (`return self.domain or self.ip_address`). Once
> a domain is set the stored address is a field nobody dials, so comparing the two
> fields side by side would reject our own row whenever its address drifted and
> accept a row that merely shares an address while dialling somebody else's vhost.
> `port` is **required on both sides** — proxbox-api declares it non-optional on
> the `ProxmoxEndpointPublic` model returned by `GET /proxmox/endpoints`, so a row
> without a parseable one is not something this backend produced, and the same
> host on a different port is a different service.
>
> **Read the wanted values from the model, never from
> `_proxmox_backend_payload()`.** That payload runs the address through
> `get_ip_address_host()`, which substitutes `"127.0.0.1"` when no IP is linked so
> the backend always has something to dial — *every* domain-only endpoint pushes
> the identical loopback string, and comparing against it would make two unrelated
> endpoints look like the same host.
>
> Every failure mode is fail-closed and **named** in the returned message
> (unregistered, no resolvable host either side, target mismatch, unusable id), so
> the operator is told which host the backend actually points at instead of
> silently getting the wrong estate's inventory. `_proxmox_endpoint_target()`
> returning `None` reads as *not current* everywhere, which costs nothing in
> practice: `EndpointBase.clean()` requires a domain or an IP address, so a
> validly saved row always resolves one.
- [`dashboard_data.py`](./dashboard_data.py): assembles endpoint and cluster summary data for the dashboard page context.
- [`mixins.py`](./mixins.py): shared view mixins used across multiple view modules.
- [`resource_list_views.py`](./resource_list_views.py): list views for resource objects (nodes, VMs, LXC containers, virtual disks, clusters, interfaces, IP addresses). Every list table is paginated through the module-level `paginate_object_list()` helper, which wraps NetBox's `EnhancedPaginator` + `get_paginate_count` so the pages honour `?per_page=`, the saved per-page preference, and `PAGINATE_COUNT`/`MAX_PAGE_SIZE` — the same machinery NetBox object tables use. These views must never re-introduce a fixed `[:100]` slice; raising the visible count is done by paginating, not by capping. The two aggregate pages (interfaces, IP addresses) render two tables each and paginate them independently via the `vm_page` / `node_page` query parameters, with summary counts computed from the full querysets (`.count()`) rather than the current page.
- [`schedule_helpers.py`](./schedule_helpers.py): utility functions for scheduling logic shared between scheduling views.
- [`backup_routine.py`](./backup_routine.py): list/detail/edit/delete views and VM-related tab views for `BackupRoutine`.
- [`branch_intent.py`](./branch_intent.py): CRUD views for soft-referenced branch
  intent gates; the optional branch detail card is registered separately only
  while `netbox_branching` is enabled.
- [`cards.py`](./cards.py): dashboard card hydration for Proxmox cluster/version data.
- [`cluster.py`](./cluster.py): cluster storage summary tab and Proxmox cluster summary tab.
- [`cluster_nodes_tab.py`](./cluster_nodes_tab.py): cluster/node tab for Proxmox endpoint detail pages.
- [`proxmox_templates_tab.py`](./proxmox_templates_tab.py): **Templates** tab for the Proxmox endpoint detail page (`.../endpoints/proxmox/<pk>/templates/`). Fetches templates live from proxbox-api for that endpoint via `get_fastapi_request_context()` + `resolve_backend_endpoint_id()` (the established backend boundary), classifies QEMU templates into **Cloud-Init** vs **plain QEMU/KVM** (derived from `cloud_init_drives`/`cicustom`, not the unreliable `cloud_init` flag) and lists **LXC** (`vztmpl`) images. Degrades gracefully (renders a message, no 500) when no FastAPI backend is configured, the endpoint is unresolved, or a request fails. Surfaces a "Create Cloud-Init template image" action wired to the optional `netbox-packer` plugin (via `integrations/packer.py`), enabled only when the packer route exists, the endpoint is enabled, and both `allow_writes` and `allow_packer_template_builds` are true; every translated refusal renders a stable tooltip. Also passes the endpoint write state and create-instance URL to the row-action wizard.
- [`../api/template_build_authorization.py`](../api/template_build_authorization.py): common local permission/gate check and immutable backend-ID resolver for the two REST template-build actions. No proxbox-api request may occur before `core.run_proxmox_action`, enabled, broad-write, and narrow-write checks pass.
- [`proxmox_create_instance.py`](./proxmox_create_instance.py): POST-only registered ProxmoxEndpoint action (`path="create-instance"`) for the Templates-tab wizard. Requires `core.run_proxmox_action`, validates JSON server-side, pre-checks `allow_writes`, calls proxbox-api directly for QEMU/LXC provisioning, retries QEMU VMID collisions, surfaces proxbox-api 403 reasons verbatim, and performs best-effort single-object VM sync-back.
- [`dashboard.py`](./dashboard.py): operational cluster and node summary dashboard.
- [`endpoints/`](./endpoints/): model views for the three endpoint models.
- [`error_utils.py`](./error_utils.py): helpers for rendering and normalizing user-facing error messages.

> **Backend error details are redacted before they are rendered.**
> `extract_backend_error_detail()` runs every parsed response body through
> `redact_sensitive()` first. It has to: the sync-job preflight pushes the
> `NetBoxEndpoint` (carrying an API `token`) and every `ProxmoxEndpoint`
> (carrying `password` / `token_value`) into proxbox-api, and FastAPI answers a
> schema mismatch with a 422 whose `input` echoes the submitted body **verbatim**
> — straight into job logs and the `Job.error` field, which are long-lived and
> readable by anyone with permission to view jobs. Redaction runs **three
> passes**, because key matching alone leaks:
>
> 1. **Keys** (the shared vocabulary in `netbox_proxbox/redaction.py`), not values — so the payload keeps its
>    shape and the operator still learns *which* field the backend rejected; a
>    value that merely mentions a password is not a secret and is left intact.
>    Keys are folded through `_normalize_key()` (lowercase, `-`/`_`/space
>    stripped) before matching, so the HTTP-header spellings
>    (`X-Proxbox-API-Key`, `Private-Key`, `SSH Keys`) match the same markers as
>    `api_key`; only the underscore form used to.
> 2. **The FastAPI `loc`/`input` echo.** A 422 reports
>    `{"loc": ["body", "token"], "msg": …, "input": "<the secret>"}` — the secret
>    lands in a **scalar** `input` whose own key is innocuous, so key matching
>    never sees it. When a sibling `loc` names a credential field, the values of
>    `_LOC_ECHO_KEYS` (`input`, `input_value`) are redacted while `msg` and the
>    field name survive.
> 3. **Prose.** `redact_sensitive_text()` sweeps every string for credential
>    assignments (`token='nbt_…'`, `Authorization: Bearer <jwt>`) that Pydantic
>    and proxbox-api render into `msg`/`python_exception` text, where no mapping
>    is left to match against. In `_SENSITIVE_ASSIGNMENT_RE` the
>    `(?:bearer|basic)\s+…` alternative **must stay first** in the value group:
>    otherwise `Authorization: Bearer <jwt>` matches with the value `Bearer`
>    alone, redacting the *keyword* and leaving the token in the clear — and then
>    hiding it from the `_BEARER_RE` sweep, which no longer has a scheme to
>    anchor on. The same sweep runs on transport errors that carry no response
>    body at all (`extract_backend_error_detail`'s `response is None` branch),
>    whose rendered text can still quote the request that failed.
>
> Depth is bounded by `_REDACTION_DEPTH_LIMIT` so a self-referential body
> terminates — and past the limit the value is replaced with `_REDACTED_DEEP`,
> **not returned raw**. Returning the original object was the hole: a payload
> nested one level deeper than the limit skipped redaction entirely.
> `_detail_to_text()` then renders the result, because a FastAPI `detail` is a
> *list*, not a string — returning it unconverted broke the `-> str` contract and
> pushed a raw `list` into f-strings and log records. Guarded by the redaction
> section of `tests/test_views_error_utils.py`.
- [`external_pages.py`](./external_pages.py): redirect or informational external community pages.
- [`home_context.py`](./home_context.py): home page context assembly and quick-schedule defaults. Also exposes `latest_sync_jobs` (the newest 5 visible Proxbox sync jobs, resolved via `is_proxbox_sync_job()` over restricted `core.Job` rows) and `sync_jobs_list_url` (the core job list filtered to Proxbox jobs via `?q=Proxbox Sync`), rendered as the "Latest Sync Jobs" table + "View all sync jobs" button at the bottom of `home.html`. See also `ProxmoxEndpointSyncJobsTabView` in `endpoints/proxmox.py` for the per-endpoint job list tab.
- [`job_run.py`](./job_run.py), [`job_cancel.py`](./job_cancel.py), and [`job_stream.py`](./job_stream.py): integrate rerun/cancel actions and SSE log streaming into NetBox core Job views for Proxbox sync jobs. The job observer stream must keep `X-Accel-Buffering: no`, emit bounded SSE comment heartbeats during idle periods, and signal its polling producer when the response closes; these three behaviors prevent disconnected browsers from stranding Gunicorn gthreads and exhausting NetBox availability. Its manually created producer thread must close old Django database connections at entry/exit and warn if it survives the bounded shutdown join.
- [`keepalive_status.py`](./keepalive_status.py): health and reachability checks for FastAPI, remote NetBox, and Proxmox services.
- [`logs.py`](./logs.py): backend log aggregation page and related rendering helpers.
- [`replication.py`](./replication.py): list/detail/edit/delete views and VM-related tab views for `Replication`.
- [`schedule_sync.py`](./schedule_sync.py): recurring/one-shot scheduler UI and quick-schedule flow from the home dashboard. Also exports `handle_endpoint_sync_routine_post(request, endpoint, post_data)` — the NetBox-independent core of the per-endpoint Sync Jobs tab "Create Sync Job" modal (permission gate → disabled-endpoint refusal → `ScheduleSyncForm` validation → **hard endpoint scoping** → enqueue → flash), returning an `(outcome, form)` tuple the tab view maps to a response. Kept here (not in the heavy `endpoints/proxmox.py`) so it is unit-loadable via the stubbed test harness.
- [`settings.py`](./settings.py): plugin settings page for runtime feature
  toggles plus secret-free encrypted-family status, atomic verified key
  rotation, and a separately permissioned selective destructive reset. Rotation
  requires normal settings-change permission; reset requires
  `netbox_proxbox.reset_encrypted_secrets` and is POST-only. Rotation marks all
  three submitted key fields sensitive for Django exception reports; both views
  provide actor/request metadata to the secret-free recovery audit trail.
- [`sync_state_repair.py`](./sync_state_repair.py): operator recovery surface
  for missing Proxbox bootstrap/custom-field setup. It builds the shared
  Home/Settings repair-card context without blocking page render, gates the
  on-demand `GET /extras/bootstrap-status` JSON endpoint with
  `view_fastapiendpoint`, and exposes the session-only `RepairSyncStateView`
  POST action requiring `core.add_job`. Bootstrap and repair backend calls use a
  request-user-restricted `FastAPIEndpoint` lookup, classify the proxy envelope
  plus inner proxbox-api body, and treat inner `ok=false` / `success=false` /
  error responses as failures. **The repair reconcile is non-fatal (issue
  #255):** `build_sync_state_repair_outcome()` calls
  `POST /extras/custom-fields/reconcile` but a failure — which is expected when
  proxbox-api holds a stale/invalid NetBox credential, since the reconcile
  authenticates with that same credential — is recorded on
  `SyncStateRepairOutcome.reconcile_warning` and the normal full `ProxboxSyncJob`
  is **still enqueued**, because the sync's preflight re-pushes the
  NetBox/Proxmox endpoint credentials to proxbox-api and rebuilds the sidecars
  from live Proxmox data (the actual recovery). The view surfaces a reconcile
  warning as `messages.warning` (still linking the job). Only `permission_denied`,
  `already_running`, and `enqueue_error` are hard failures; all outcomes are
  flash messages that never 500. The card is always visible on its dedicated
  page; included elsewhere it stays hidden for a view-capable user and only
  reveals on a genuine backend-reported bootstrap problem, while a repair-only
  user (can `core.add_job`, cannot view status) keeps the repair affordance —
  see `partials/bootstrap_status_card.html`.
- [`sync_state_repair_page.py`](./sync_state_repair_page.py):
  `SyncStateRepairPageView`, the login-required page at `sync-state/` that hosts
  the repair card. It is intentionally absent from `navigation.py` and reached
  only from the Home page footer link, and it passes `surface="repair"` so a
  repair POST redirects back to itself. It lives in its own module because
  `sync_state_repair.py` must stay free of `ConditionalLoginRequiredMixin` —
  combining it with `ContentTypePermissionRequiredMixin` there produced an
  invalid MRO (commit 39f8f9d9), and a contract test pins that.
- [`proxmox_cluster_node.py`](./proxmox_cluster_node.py): detail (`ObjectView`) views for `ProxmoxCluster` and `ProxmoxNode`, registered under the bare model names so `get_absolute_url()` resolves.
- [`storage.py`](./storage.py): CRUD list/detail/delete views for `ProxmoxStorage`.
- [`storage_content.py`](./storage_content.py): process-wide bounded worker pool,
  deadline-aware streamed JSON fetch, response-size ceiling, and shared
  partial/truncation notice formatter for storage-node content fan-out.
- [`sync.py`](./sync.py): POST endpoints that enqueue `ProxboxSyncJob` runs for devices, storage, virtual machines, virtual disks, backups, snapshots, network interfaces, IP addresses, backup routines, replications, and full update.
- [`sync_now/`](./sync_now/): targeted per-object sync handlers for plugin cluster, node, storage, backup, snapshot, and task-history actions. The core VM action remains in `vm_sync_now.py`.
- [`vm_backup.py`](./vm_backup.py): CRUD list/detail/delete views and the VirtualMachine tab for `VMBackup`.
- [`vm_config.py`](./vm_config.py): live Proxmox config tab for `VirtualMachine` records.
- [`vm_intent.py`](./vm_intent.py): CRUD list/detail/edit/delete views for
  operator-owned `ProxmoxVMIntent` rows. The VM template extension supplies the
  add/edit button and renders no intent card until a row exists.
- [`vm_snapshot.py`](./vm_snapshot.py): CRUD list/detail/delete views and the VirtualMachine tab for `VMSnapshot`.
- [`vm_sync_now.py`](./vm_sync_now.py): targeted per-VM sync action button handler.
- [`vm_task_history.py`](./vm_task_history.py): detail and VirtualMachine tab views for `VMTaskHistory`.

## Dependencies

- Inbound: `urls.py` routes here for all plugin UI behavior.
- Outbound: plugin models, forms, tables, filtersets, templates, `requests`, the external ProxBox FastAPI service, and `websocket_client.py`.

## Notes

- `HomeView` is the main dashboard entrypoint and assembles endpoint lists plus derived backend URLs for the templates.
- Most changes to user-visible behavior land here first, then cascade into templates, static assets, and tests.
- When adding or changing sync actions, update `urls.py`, `sync.py`, scheduling forms/views, template extensions, and relevant frontend/tests that assert button routes and job flow.
- **Registered detail views must resolve a real template.** Every
  `register_model_view`-registered `ObjectView` must either declare an explicit
  `template_name` pointing to an existing file or provide the fallback
  `netbox_proxbox/<model_name>.html` in the plugin template namespace.
  `tests/test_detail_view_templates.py` supplies the fast AST/filesystem
  contract. The merge gate is the complementary real-NetBox test in
  `tests/test_detail_view_templates_django.py`: it walks the populated runtime
  registry, asks each actual `ObjectView` for its template, compiles that name
  through Django's loader, and authenticated-GET smokes the 17 routes repaired
  by this bug across the supported NetBox matrix.
- **URL namespace for tabs registered on core models.** When `register_model_view`
  attaches a tab/view to a NetBox **core** model (e.g. `virtualization.Cluster`,
  `virtualization.VirtualMachine`, `core.Job`), NetBox names that URL under the
  **core** model's namespace, not the plugin namespace — `get_viewname` only
  prepends `plugins:` for models that belong to a `PluginConfig`. So reverse
  these as `virtualization:cluster_<name>` / `virtualization:virtualmachine_<name>`
  (e.g. `virtualization:cluster_proxbox-storages` for
  `register_model_view(Cluster, "proxbox-storages", ...)`), **never**
  `plugins:netbox_proxbox:cluster_<name>`. Only the plugin's *own* models use the
  `plugins:netbox_proxbox:` namespace. Using the wrong namespace raises
  `NoReverseMatch` at template-render time and returns HTTP 500 (this caused the
  cluster summary crash). `tests/test_frontend_contracts.py` guards the cluster
  summary template against this regression.
- **A model's `get_absolute_url()` target must actually be mounted (issue #618).**
  `ProxmoxCluster` and `ProxmoxNode` reversed
  `plugins:netbox_proxbox:proxmoxcluster` / `:proxmoxnode`, but `urls.py` never
  mounted `get_model_urls()` for either, so the name did not exist. The Sync-Now
  template extension previously called `get_absolute_url()` on **every core
  `virtualization.Cluster` and `dcim.Device` detail page**, which raised
  `NoReverseMatch` and rendered "An error occurred when loading content from
  plugin netbox_proxbox". The models later gained a `try/except NoReverseMatch →
  return ""` guard, which stopped the crash but silently produced dead links and
  a Sync-Now button posting to a relative `proxbox-sync-now/` that 404s. Both
  models now have a real `ObjectView` registered under the bare model name plus
  a `get_model_urls()` mount. Keep the guard **and** the mount:
  `tests/test_url_reverse_contracts.py` asserts every name reversed from
  `models/` is mounted, with an explicit `UNMOUNTED_BY_DESIGN` allowlist
  (`PBSEndpoint` pending #449; the four Firecracker models are API-managed and
  have no UI surface).
- **`views/sync_now/` only registers if something imports it.** That package
  exposes its views through a lazy `__getattr__`, so nothing ever executed the
  `@register_model_view` decorators in the individual modules. `urls.py` now
  imports cluster, node, storage, backup, snapshot, and task-history modules for
  their decorator side effect before the `get_model_urls()` calls are evaluated.
  If you add a module there, import it in `urls.py` too, and keep the contract
  test green.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`endpoints/CLAUDE.md`](./endpoints/CLAUDE.md)
- Child: [`sync_now/CLAUDE.md`](./sync_now/CLAUDE.md)
