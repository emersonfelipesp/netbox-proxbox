# `netbox_proxbox` Package

This package contains the NetBox plugin itself. It defines the plugin config, URL registration, navigation, models, forms, tables, API layer, background jobs, sync helpers, dashboard views, template hooks, and bundled static assets.

## Files And Ownership

- [`__init__.py`](./__init__.py): plugin registration via `PluginConfig`, plugin metadata, and supported NetBox version range.
- [`urls.py`](./urls.py): plugin URL map for UI pages, model views, sync routes, keepalive checks, card hydration, and the WebSocket test endpoint.
- [`navigation.py`](./navigation.py): NetBox plugin menu groups and buttons.
- [`choices.py`](./choices.py): `ChoiceSet` definitions for endpoint modes, sync types/statuses, token versions, and VM backup metadata.
- [`fields.py`](./fields.py): custom model/form field helpers used by the endpoint models.
- [`filtersets.py`](./filtersets.py): NetBox filtersets backing list views and API query filtering.
- [`jobs.py`](./jobs.py): `ProxboxSyncJob` background job class, enqueue helpers, and concurrent-run ownership guards.

> **The preflight blocks what provably cannot work, and hints at the rest.**
> `_ensure_backend_endpoints()` pushes the `NetBoxEndpoint` and `ProxmoxEndpoint`
> rows into proxbox-api before any stage runs. That NetBox push is what installs
> the credentials the backend writes NetBox objects with. **Six** conditions
> are fatal and raise `ProxboxPreflightError` immediately:
>
> 1. **No usable backend.** `get_fastapi_request_context()` returns nothing —
>    no enabled `FastAPIEndpoint`, or the selected one is unusable. Every stage
>    runs through that backend, so there is nothing left to try. The message
>    names the *selected* endpoint id when the job pinned one, and points at
>    Proxbox → Endpoints → FastAPI.
> 2. **No enabled `NetBoxEndpoint` in this NetBox.** Zero enabled rows is not a
>    failed push — it is this NetBox declining to be written to at all, i.e. the
>    documented disabled-endpoint no-connection gate. It blocks **unconditionally**,
>    and the backend's stored rows are deliberately **not** consulted:
>    `list_backend_netbox_endpoints()` is never even called. proxbox-api may still
>    hold credentials issued before the row was disabled, or credentials for an
>    entirely different NetBox instance; honouring either would let the sync keep
>    writing with exactly the authorization the operator revoked. Do **not**
>    "improve" this by falling back to the backend's own state when it happens to
>    hold a row — that is the bug this gate exists to close.
> 3. **Confirmed-empty backend.** The NetBox push failed **and** a follow-up
>    `list_backend_netbox_endpoints()` read confirms the backend holds **zero**
>    NetBox endpoints. Only reachable with at least one *enabled* local row, so
>    the backend's stored configuration is a legitimate fallback for a genuinely
>    *transient* push failure here — which is precisely why case 2 must return
>    before it.
> 4. **Stored rows that point at a *different* NetBox.** The push failed, the
>    backend does hold rows, but `backend_holds_netbox_endpoint()` cannot match
>    any of them to this instance. **Presence of a row proves nothing about whose
>    credentials it carries:** the backend NetBox endpoint is a *singleton* on
>    proxbox-api — `sync_netbox_endpoint_to_backend()` updates the first (and
>    only) entry by **position**, never by name — and unlike the Proxmox payload
>    (`"<name> (nb:<pk>)"`) the NetBox payload's `name` is free text with no
>    embedded pk. Identity is therefore the **resolved connection target**:
>    `(domain or ip_address)` plus `port` — literally what proxbox-api's own
>    `NetBoxEndpoint.url` property dials (`host = domain if domain else
>    ip_address`) — with `domain`/`ip_address` read from the *model* by
>    `_netbox_endpoint_identity()`. Both sides must resolve a target, and the two
>    targets must be equal.
>
>    **Compare the resolved target, not each field in turn.** Field-by-field
>    matching ("every field both sides declare must agree, and at least one must
>    positively match") was the earlier rule and it is wrong in *both* directions.
>    It **accepts** rows it should not: a stored row blank on `domain` at our IP
>    is a NetBox reached *by address*, a different service from ours reached by
>    vhost name at that same address — a blank stored field is data, not a gap.
>    The mirror case is a stored row naming *another* domain at our IP while we
>    are IP-only; that row dials their vhost. And it **rejects** rows it should
>    not: with a domain set the address is never dialled, so our own record whose
>    stored IP has since changed is still ours.
>
>    `port` is **required on both sides**, not "checked when present".
>    proxbox-api declares it non-optional on its `NetBoxEndpointResponse` and
>    `GET /endpoint` returns `list[NetBoxEndpointResponse]`, so every row this
>    backend produces carries one; a row without it is not from this backend, and
>    a port we cannot parse is a service we cannot identify. Same host, different
>    port is a different service.
>
>    **Do not read identity off `_netbox_endpoint_backend_payload()`** — that is
>    the push body, and it substitutes `"127.0.0.1"` when the row has no linked
>    IP so the backend still has something to dial. *Every* domain-only NetBox
>    therefore pushes the same loopback string, and matching on it let one
>    domain-only instance identify as another's stored record. Only an explicitly
>    configured IP is evidence; an absent one contributes nothing.
>
>    **Identity selects a candidate row; currency is what accepts it.** Proving a
>    stored row describes *this* NetBox does not prove it still describes this
>    NetBox *correctly*. The push body carries `verify_ssl` and `token_version`
>    alongside the target, so an operator who hardens TLS verification or rotates
>    the token scheme and then hits a transient push failure would otherwise
>    continue the run with proxbox-api writing under the **superseded** posture —
>    the same defect class as the stale-Proxmox-row case below.
>    `_netbox_row_is_current()` therefore also requires `verify_ssl` and
>    `token_version` to match, read from the **model** (not from
>    `_netbox_endpoint_backend_payload()`, which logs and materialises the secret
>    just to answer a comparison). An **absent** field reads as drifted: this
>    check gates the whole run, so unknown must fail closed here even though the
>    Proxmox-side twin can afford to treat an unknown as merely "push again".
>
>    The comparable set is bounded by what proxbox-api gives back.
>    `NetBoxEndpointResponse` returns `id, name, ip_address, domain, port,
>    token_version, verify_ssl, enabled` and deliberately withholds
>    `token`/`token_key`, so the *secret* cannot be compared against the stored
>    row at all — it is checked separately, and **locally**, by case 6 below.
>    `name` **is** returned and is deliberately **not** compared: it is free
>    text, and a rename is not a reason to hard-fail an otherwise safe run.
>
>    **The listing must hold exactly one row.** proxbox-api's NetBox endpoint is
>    a *positional* singleton — the push overwrites entry `[0]`, and entry `[0]`
>    is what the backend dials — so a listing returning **more than one** row
>    means the contract this check rests on no longer describes the backend, and
>    nothing in the response says which row wins. Matching anywhere in the list
>    would then vouch for a row found at index 1 while a stale record at index 0,
>    possibly another NetBox's, is the one actually driving the sync — the same
>    cross-instance write this check exists to stop, reached by counting rows
>    instead of by reading the wrong one. More than one row is therefore refused
>    outright, whatever those rows say. With exactly one row the loop is asking
>    identity and currency of the row that actually matters, so a current row
>    belonging to a *different* NetBox never rescues our own drifted one.
>
>    A match means a *transient refresh* failure over still-ours (possibly stale)
>    credentials → warn and continue. No match means proxbox-api holds another
>    NetBox's credentials, or our own under a configuration we have since
>    replaced, and continuing would sync this estate's Proxmox data **into someone
>    else's NetBox** or under revoked trust settings. The check is fail-closed at
>    every step (empty/`None` list, a list longer than the positional singleton,
>    row with neither host field, conflicting field, unparseable port, missing
>    currency field → *not held*).
> 5. **Nothing pushed and nothing readable.** The NetBox push failed for *every*
>    enabled row **and** `list_backend_netbox_endpoints()` itself failed, so
>    there is no evidence at all that the backend's credentials belong to this
>    NetBox — only that it may hold somebody's. This is the one place "unknown"
>    must not read as "ours": the branch is reachable only after a failed push,
>    and continuing would reintroduce exactly the cross-instance write case 4
>    blocks, just through an ambiguous read instead of a mismatched row. The
>    exception is a run where *some* enabled row pushed successfully — that push
>    wrote this NetBox's credentials into the singleton, so the unreadable
>    listing has nothing left to add and the run continues with a warning.
> 6. **A stored row that is ours, but was written with credentials we have since
>    replaced.** The push failed, a stored row *does* pass case 4's identity and
>    currency checks — and the API token behind it has been rotated in place
>    since the last successful push. "This row describes this NetBox" and "this
>    row carries the credential this NetBox currently issues" are different
>    questions, and case 4 can only answer the first: the response model withholds
>    `token`/`token_key`, so there is nothing on the wire to compare a secret
>    against. Continuing would let proxbox-api keep writing with the token the
>    operator has just revoked — and the entire point of rotating is that the old
>    value stops working.
>
>    The comparison is therefore **local**: every successful push records
>    `netbox_credential_fingerprint(payload)` — a keyed HMAC-SHA256 over
>    `token_version`, `token_key` and `token` — on
>    `NetBoxEndpoint.pushed_credential_fingerprint` (migration 0073), and
>    `netbox_push_credentials_unchanged()` re-derives it from the endpoint as it
>    stands now and compares with `hmac.compare_digest`. It is not a credential:
>    `salted_hmac` keys off NetBox's `SECRET_KEY`, so the digest is
>    non-reversible and is not even comparable across installs. An **empty**
>    stored fingerprint reads as *changed* — never pushed, or a first run after
>    upgrading into this check — which is the fail-closed reading, and one
>    successful push clears it permanently. The three-way is
>    `vouched` → warn and continue, `held` but not vouched → **fatal (this
>    case)**, neither → **fatal (case 4)**; see
>    [`views/CLAUDE.md`](./views/CLAUDE.md) for why the fingerprint is taken from
>    the *payload* and written with `queryset.update()`.
>
> Every other preflight problem — a failed key registration, a failed *Proxmox*
> push, or a listing call that errored *after* a successful NetBox push — stays
> non-fatal and is returned on `PreflightResult.hint`, which
> `sync_stages.py` appends to any later stage error. Do not widen the
> confirmed-empty case: a run that could have worked must never be blocked on an
> ambiguous read *about which endpoints exist*. Do not narrow it either — before this existed, a fresh install
> with no backend credentials burned ~83 s of retries and then reported `Error
> ensuring Proxbox tag` on the `devices` stage, sending operators to debug tags
> instead of connectivity (netbox-proxbox issue #624). Guarded by
> `tests/test_preflight_diagnosis.py` and the preflight section of
> `tests/test_jobs.py`.
>
> **The selected-object batch path runs the same preflight.** A "sync selected
> objects" run (`batch_object_type` + `batch_object_ids`) reaches proxbox-api
> through `sync_individual()` instead of the SSE stage loop, but the *writes land
> in NetBox exactly the same way* — so the batch branch of `run()` calls
> `_ensure_backend_endpoints()` and raises on `blocking_error` **before**
> `_run_batch_selected_sync()`. It previously returned before the preflight
> entirely, which meant a NetBox that had disabled its own endpoint could still be
> written to with whatever credentials the backend happened to still hold — the one
> thing the disabled-endpoint gate exists to prevent. The batch branch also threads
> `fastapi_endpoint_id` all the way down (`_run_batch_selected_sync` →
> `sync_individual_with_dependencies` → `sync_individual` →
> `get_first_fastapi_context(endpoint_id=…)`, recursive dependency syncs included),
> because each per-object call resolves its own backend; without the pin a
> multi-backend install validates one proxbox-api and then syncs against whichever
> row sorts first. Its response carries `endpoint_runtimes` built from the
> preflight phases, same as a staged run.
>
> **…and it resolves the same *Proxmox* scope, for a sharper reason.** The
> preflight settles the NetBox side; it does not decide which Proxmox endpoints a
> run may touch. Every `sync/individual/*` route on proxbox-api resolves its
> Proxmox sessions through the **same** `ProxmoxSessionsDep` the stage routes use,
> and that dependency reads a *missing* `proxmox_endpoint_ids` as **"use every
> endpoint I hold"**. An unscoped selected-object sync is therefore not a narrower
> request than a staged one — it is the *widest* request the backend accepts,
> reaching endpoints this NetBox has disabled and endpoints from a previous
> deployment. So `run()` calls `_batch_wire_endpoint_scope()` right after the
> preflight and raises `ProxboxPreflightError("Selected-object sync did not
> run: …")` when no scope resolves, reusing `_no_endpoint_scope_reason()` so the
> staged and batch paths refuse in the *same words* — including the sentence
> saying an unfiltered sync is not the safe degradation. The resolved
> comma-separated backend ids are then threaded down as
> `proxmox_wire_endpoint_ids=`, landing both in each call's `query_params` **and**
> as an explicit `proxmox_endpoint_ids=` argument on
> `sync_individual_with_dependencies()` → `_sync_dependency()` →
> `sync_individual()`, for the same `_CONTEXT_KEYS` reason the branch schema id
> travels that way (see [`services/CLAUDE.md`](./services/CLAUDE.md)).
>
> **A partial resolution narrows the scope; it does not fail the run.**
> `_batch_wire_endpoint_scope()` returns `(scope, skipped_plugin_pks, error,
> wire_id_by_plugin_pk)`, and unresolved endpoints are reported in
> `skipped_plugin_pks` and logged as a `warning` naming them, not raised. Failing
> outright because one *unrelated* endpoint drifted would be a regression, and the
> narrowed scope is still strictly safer than the unscoped request it replaces.
>
> **But a narrowed job-wide scope is not by itself enough, and the earlier note
> here claiming an object on a skipped endpoint "fails loudly at the backend" was
> wrong.** It only fails loudly when *no other in-scope endpoint can answer* — and
> Proxmox identifiers are unique **per endpoint**, not across the estate. A
> selected-object request names a cluster, a node and a VMID and nothing else, so
> two unrelated Proxmox installations each holding a `cluster01/pve1/100` both
> answer it, and whichever the backend picked would be written into this object's
> NetBox row with no error anywhere. The fourth return value closes that: it maps
> **plugin `ProxmoxEndpoint` pk → backend wire id**, and
> `_run_batch_selected_sync()` resolves each object's owner through
> `ProxmoxCluster.netbox_cluster` / `ProxmoxCluster.endpoint` (one grouped query
> for the whole batch, beside the object fetch — not one per object in front of a
> per-object HTTP call) and then:
>
> - **owner resolved and in the map** → the call is pinned to that *single* wire
>   id, in both `query_params` and the `proxmox_endpoint_ids=` argument;
> - **owner resolved but absent from the map** (its endpoint drifted and was
>   skipped) → that object alone fails with HTTP **424** and a message naming the
>   endpoint id, because asking the *remaining* endpoints is exactly the
>   duplicate-identifier case above;
> - **owner claimed by more than one endpoint** → that object alone fails with
>   HTTP **424** naming every claimant. Two endpoints reflecting the same core
>   cluster is *proof* the duplicate-identifier namespace exists in this estate,
>   so widening to the job-wide scope would ask both and keep whichever answered
>   — precisely the failure being fixed — while picking one arbitrarily would be
>   a *guess* about where the object lives;
> - **owner not resolvable at all** — no cluster, or nothing has reflected a
>   `ProxmoxCluster` for it yet → fall back to the job-wide scope, but **only
>   while that scope names a single endpoint**. A first-ever sync is precisely the
>   run with nothing to resolve an owner from, and refusing there would make the
>   object unsyncable forever — but that argument only pays for itself where
>   widening is free. With one endpoint in scope, "the job-wide scope" and "that
>   one endpoint" are the same request, so the fallback is already pinned and no
>   duplicate-identifier hazard exists. With **two or more** in scope it is a
>   guess, made with identifiers (cluster/node/VMID) that are unique only *per*
>   endpoint, so the wrong estate can answer and its data lands in this row with
>   no error raised — the exact defect this whole section removes, reached by the
>   one branch that still widened. So a multi-endpoint run refuses that object
>   with HTTP **424** instead, saying how many endpoints are in scope and how to
>   proceed. Refusing is recoverable and widening is not: a staged sync reflects
>   the clusters, ownership becomes resolvable, and the retry pins — whereas the
>   wrong data, once written, is already in NetBox. `job_scope_wire_ids` is
>   counted **once** per batch, not re-split per object. **Unknown and ambiguous
>   are still deliberately different states** — ambiguous never widens at any
>   scope size, and collapsing it back into unknown restores the widening this fix
>   removes.
>
> All five batch types converge on a core `virtualization.Cluster` id by different
> routes (`_batch_object_core_cluster_id()`): a VM and a `ProxmoxStorage` carry it
> directly — `ProxmoxStorage.cluster` FKs to `virtualization.Cluster`, **not** to
> `ProxmoxCluster` — while a backup resolves through its *storage* (the cluster
> its own sync parameters are built from) and snapshots/task-history through their
> VM. This mirrors `views/vm_sync_now.py::_endpoint_ids_for_vm()`.
>
> Guarded by `test_batch_selected_sync_blocks_when_no_proxmox_endpoint_is_enabled`,
> `test_batch_selected_sync_blocks_when_no_endpoint_resolves_to_a_backend_id`,
> `test_batch_wire_endpoint_scope_narrows_rather_than_failing_on_partial_drift`,
> `test_run_batch_selected_sync_passes_the_proxmox_scope_to_dependency_syncs`, and
> the five duplicate-identifier tests plus the
> `_batch_object_core_cluster_id` table in `tests/test_jobs.py`.
>
> **The preflight is scoped to the backend the stages will use.** `run()` threads
> its own `fastapi_endpoint_id` into `_ensure_backend_endpoints()`, which passes
> it to both `get_fastapi_request_context(endpoint_id=…)` and
> `ensure_backend_key_registered(endpoint_id=…)`, and on into
> `_resolve_wire_endpoint_ids()`. With two enabled backends, resolving without
> the id checks the *wrong* one — hard-failing a sync that works, or passing one
> that cannot. The plugin's `ProxmoxEndpoint` pk is also **not** proxbox-api's own
> endpoint id; wire ids are resolved per backend, never assumed equal.
>
> **The backend pin round-trips through `job.data`, so a replay keeps it.**
> `ProxboxSyncJob.enqueue()` normalises `fastapi_endpoint_id` with
> `_coerce_fastapi_endpoint_id()` (int or absent — `job.data` is a JSONField, and
> a half-parsed pk would silently select a *different* backend than the caller
> meant) and persists it in `job.data['proxbox_sync']['params']`;
> `proxbox_sync_params_from_job()` reads it back on **both** return paths — the
> normal one and the legacy targeted-VM name inference, which rebuilds the params
> from scratch and would otherwise drop it. `views/job_run.py` splats those params
> straight back into `enqueue()`, and a recurring schedule re-enqueues itself the
> same way. `_serialize_sync_params()` always wrote the key, but nothing read it,
> so every **Run now** silently fell back to "first enabled backend" — re-electing
> a different proxbox-api for the preflight, key registration, wire-id lookup, and
> the four pre-SSE passes than the original run was pinned to. Guarded by the
> `fastapi_endpoint_id` section of `tests/test_jobs.py`.
>
> **The same id is threaded into the four pre-SSE service passes.** Cluster/node
> sync, firewall sync, datacenter CPU-model sync, and VM-template sync all run
> before the SSE stages and each resolves its own backend. `run()` passes
> `fastapi_endpoint_id=` to every one of them, and each forwards it to
> `get_fastapi_request_context(endpoint_id=…)`. Without it, a multi-backend
> install certifies one backend in the preflight and then syncs against another.
> Note the parameter is only consulted **when `fastapi_url` is falsy** — that
> branch is also where each service reads `verify_ssl` off the resolved context,
> so passing a `fastapi_url` instead would silently pin `verify_ssl=True` and
> break self-signed installs. Pass the id, never the URL.
>
> **The preflight push loop is time-boxed — with a *soft* budget and a hard
> ceiling, and the difference is load-bearing.** Each push carries its own request
> timeout, so an estate with many Proxmox endpoints and a hung backend would
> serialize into (endpoints × timeout) seconds *before the first stage runs* —
> the preflight could consume the whole `PROXBOX_SYNC_JOB_TIMEOUT`. Past
> `PREFLIGHT_ENDPOINT_PUSH_BUDGET` (600 s, from `views/backend_sync.py`) the loop
> skips only endpoints whose backend row is already **current** — for those the
> push is a no-op refresh, so skipping costs nothing at all.
> `backend_holds_proxmox_endpoint()` decides, and "held" alone is not the
> question: it locates the row by `proxmox_backend_name()` (the same name the
> push itself matches on, so the check cannot drift from
> `sync_proxmox_endpoint_to_backend()`) and then requires
> `_proxmox_row_is_current()` — same resolved connection target, same `username` /
> `access_methods` / `verify_ssl`. Skipping a **drifted** row would preserve
> exactly the stale row `resolve_backend_endpoint_ids()` then refuses to sync
> against, turning a merely slow backend into a blocked endpoint, so a drifted row
> is pushed regardless of the budget. `timeout` / `max_retries` /
> `retry_backoff` and the site/tenant metadata are deliberately **excluded**:
> drift there is the "slightly stale row" the budget already accepts, and
> comparing values that normalise unpredictably risks a budget that never skips
> anything — reintroducing the (endpoints × timeout) stall it exists to prevent.
> A false "not current" costs one extra push, bounded by the hard ceiling. An
> endpoint the backend has never seen — or one whose listing call failed, since
> "unknown" must never be the reason an endpoint is skipped into a fatal error —
> is **always** pushed, and the extra push is logged: skipping it strands the
> endpoint with no backend id, and the run then fails on exactly the endpoint the
> budget "saved" time on. Only `PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING` (1800 s —
> 25% of the job timeout) skips everything, because past that the backend is not
> slow, it is hung. Skipped endpoints still get a `status="warning"` runtime phase
> and are named in a job-log warning and the preflight hint, so the run is visibly
> incomplete rather than silently partial. The loop also lists the backend's
> Proxmox rows **once** and reuses them via `existing_endpoints=`, instead of
> paying a fresh listing per endpoint.
>
> **A stored Proxmox row is only usable once it is confirmed to still dial the
> same host.** The push loop *warns* on failure and continues, so a retargeted
> `ProxmoxEndpoint` whose push failed leaves the backend holding the **previous**
> host under this endpoint's name — and syncing through that id reflects the old
> Proxmox host's inventory into NetBox under the new endpoint. Name-matching alone
> cannot see that, so `resolve_backend_endpoint_ids()` (and the singular
> `resolve_backend_endpoint_id()` behind the Templates tab and the create-instance
> wizard) compare the row's **resolved connection target** — `(domain or
> ip_address)` plus `port`, mirroring proxbox-api's own `ProxmoxEndpoint.host`
> property — and refuse a mismatch. Unregistered, unresolvable on either side,
> mismatched, or carrying no usable id all fail closed with a message naming the
> host the backend actually points at. The wanted values are read from the
> **model**, never from `_proxmox_backend_payload()`, whose `127.0.0.1` fallback
> every domain-only endpoint sends identically. In the batch path a refused
> endpoint is omitted and its reason logged, which feeds the endpoint-scope
> failure below rather than silently syncing the wrong estate.
>
> **Endpoint-scope failures fail the job — after `job.data` is saved.** If no
> endpoint could be resolved to a wire id, the job fails with "No sync stage
> ran"; if some resolved, it fails naming how many were skipped. Persisting
> `job.data` first keeps the per-endpoint runtime breakdown readable on a failed
> run. A stage recorded as `skipped` does **not** count as having run — counting
> it would make "No sync stage ran" unreachable as soon as any endpoint
> contributed a sync-mode skip.
>
> **A selected-object run that did not sync everything fails the job too.** Every
> object in a batch was named by an operator, so there is no "partial success"
> reading of a list somebody typed out — a `batch_result["failed"] > 0` therefore
> raises `RuntimeError` rather than returning normally. It used to record the
> per-object failures in `job.data` and finish **completed**, leaving the errors
> visible only to whoever already suspected something was wrong; the
> per-object 424 refusals above would have been invisible that way. Two orderings
> are load-bearing: `self.job.save(update_fields=["data"])` runs *before* the
> raise, so the failed row still carries the per-object detail, and the raise
> happens *before* the branch merge, so a partial result is never promoted into
> main. The message names up to `BATCH_FAILURE_DETAIL_LIMIT` failed objects with
> their status and error (`_failed_batch_object_detail()`, read off the same
> `results` list that is persisted, so log and record cannot disagree) and
> summarises the remainder — and says so explicitly when `failed` was non-zero
> but no result row explains it, so the job never fails wordlessly. Guarded by
> `test_batch_selected_sync_fails_the_job_when_selected_objects_failed`, which
> deliberately enables branching so "the merge did not run" is an assertion about
> ordering rather than about branching being off.
>
> **Zero enabled Proxmox endpoints means *no scope*, never the empty scope.** An
> empty scope is not a narrower request than a scoped one — it is a *wider* one.
> `_build_stage_query_params()` only sets `proxmox_endpoint_ids` when a scope is
> truthy, so an empty scope reaches proxbox-api as a request carrying no endpoint
> filter at all, which the backend reads as **"sync every endpoint you hold"** —
> including endpoints disabled in NetBox, and endpoints from a previous
> deployment. `_proxmox_endpoint_scopes()` therefore returns `[]` (not `[[]]`)
> when nothing is enabled, and `_run_all_stages_sync()` returns early with a
> fail-loud `endpoint-scope` record instead of entering a stage loop that would
> never iterate — an empty `stages_out` finishes the job **completed** having
> synced nothing, the silent no-op this whole preflight effort exists to
> eliminate. The message distinguishes "every endpoint *selected for this run* is
> disabled or gone" from "no enabled Proxmox endpoint exists at all", and the
> latter says explicitly that an unscoped sync is not the safe degradation. Both
> strings live in `_no_endpoint_scope_reason()` and are shared with the
> selected-object batch path, so the two paths cannot drift into refusing for the
> same reason in different words.
> Guarded by `test_proxmox_endpoint_scopes_returns_no_scope_when_every_endpoint_disabled`
> and `test_run_all_stages_fails_loud_when_no_proxmox_endpoint_is_enabled`.
>
> **An unresolvable endpoint whose every selected stage is mode-disabled is a
> skip, not a failure.** Wire-id resolution happens *before* the stage loop, and
> the stage loop is where sync modes are normally applied — so an endpoint missing
> from the backend used to hard-fail even when the run would have synced exactly
> zero objects anyway (`sync_types=[sdn]` against the default
> `sync_mode_sdn=disabled`, say). `_run_all_stages_sync()` now resolves that
> endpoint's modes in the unresolved branch and, when *every* selected stage is
> disabled, records `{"ok": True, "skipped": True, "reason": …}` per stage and
> moves on. Nothing was lost, so nothing is reported wrong. If even one stage
> would have run, the fail-loud `endpoint-scope` path is unchanged.

> **Job log messages must be pre-formatted.** NetBox persists job log entries via
> `core.dataclasses.JobLogEntry.from_logrecord`, which stores `record.msg` — the
> **raw** format string. Python only merges `record.args` inside
> `record.getMessage()`, which NetBox never calls. So
> `job.logger.info("... %s", value)` writes a literal `%s` to the job log and
> drops the value; users reporting sync problems pasted logs full of
> `Preflight: API key verified — %s` and `Running SSE sync for Proxmox endpoint
> %s (backend id %s)`, which made those reports much harder to diagnose. Always
> use an f-string for `job.logger` / `self.logger` calls. Module-level
> `logger.info("%s", x)` is unaffected and stays fine. Guarded by
> `tests/test_job_log_formatting.py`, which scans every plugin module.
- [`sync_types.py`](./sync_types.py): regex-based targeted VM job name parsing and sync-type expansion helpers used by `jobs.py`.

> **Targeted per-VM runs are scoped, not estate-wide.** When `netbox_vm_ids` is
> non-empty (the per-VM "Sync now" button), `ProxboxSyncJob.run()` sets
> `targeted_vm_run` and **skips** the datacenter-wide preflight passes —
> firewall sync, datacenter CPU-model sync, and VM template inventory. Those
> three take no scoping argument (firewall/datacenter take none at all; templates
> loop every endpoint) and are irrelevant to reconciling one VM, yet they
> dominated the wall-clock of a targeted run. Each skip is logged so it is
> visible, and a full/scheduled sync still runs all of them. Cluster/node sync
> stays, but is scoped: `views/vm_sync_now.py::_endpoint_ids_for_vm()` resolves
> the VM's own endpoint through `ProxmoxCluster.netbox_cluster` and passes only
> that id, falling back to all enabled endpoints when the VM has no reflected
> Proxmox cluster yet. Guarded by `tests/test_targeted_sync_scope.py` and
> `tests/test_vm_sync_now_view.py`.
- [`sync_params.py`](./sync_params.py): normalises and serialises sync parameters passed into `ProxboxSyncJob.enqueue`.
- [`sync_stages.py`](./sync_stages.py): runs a single named sync stage against the backend SSE stream.
> **Which failures get retried.** `_is_retryable_stage_failure()` retries 5xx and
> 429 outright, and retries a **400** only when the reported cause names a
> transport failure. It has to: proxbox-api's `ProxboxException` defaults to HTTP
> 400 for *every* uncaught error, so a refused connection and a rejected VMID
> arrive under the same status. The match runs over the payload's
> error-describing fields only (`_ERROR_CAUSE_KEYS` — including
> `python_exception`, which `_extract_backend_error_text()` does not read), never
> the stringified payload: a `"timeout": 30` config value or a VM named
> `connection-reset-lab` must not buy a genuine rejection two extra attempts.
> When adding a marker to `_TRANSPORT_FAILURE_MARKERS`, **prefer a phrase over a
> single word** for the same reason: a bare `"timeout"` also matched the genuine
> rejection `"timeout must be between 1 and 300"`, so the word alone is not
> usable. (`"request timeout"` is absent for the same reason — it can complete a
> sentence about a *field* of that name.)
>
> **Markers are written against the strings the transport layer actually
> emits**, not against how the failure is usually described: requests/urllib3,
> httpx, the `ssl` module, the glibc/BSD resolvers, and nginx. nginx spells its
> own 504 body `Gateway Time-out` — with a hyphen — so `"gateway timeout"` alone
> never matched it, and glibc's `EAI_AGAIN` reads `Temporary failure in name
> resolution`, which is precisely the cold-start case this fix exists for.
> `tests/test_preflight_diagnosis.py::…::test_real_transport_failure_texts_are_matched`
> pins each real emitter string, so a marker cannot be trimmed to a shape that
> only matches the paraphrase.
>
> FastAPI reports `detail` as a *list* of objects, so the cause is often one
> level down. `_iter_cause_strings()` descends into lists and into the keys named
> by `_NESTED_CAUSE_KEYS` (`_ERROR_CAUSE_KEYS` plus `msg`), bounded by
> `_CAUSE_RECURSION_LIMIT` so a cyclic or pathological body cannot stall the
> classifier. **`input` is deliberately excluded** from that walk: it echoes the
> submitted request body, so it is data, not a cause — scanning it would let a VM
> named `connection-refused` flip a rejection into a retry, and it is the same
> field that carries pushed credentials. Guarded by
> `tests/test_preflight_diagnosis.py::TestRetryableStageFailure`.
- [`sync_ownership.py`](./sync_ownership.py): helpers that claim and release RQ job ownership to prevent concurrent duplicate runs.
- [`schedule_hints.py`](./schedule_hints.py): quick-schedule heuristics and UI defaults for the home dashboard.
- [`github.py`](./github.py): fetches markdown content from GitHub for the contributing page.
- [`template_content.py`](./template_content.py): plugin template extensions for Job and VirtualMachine buttons/panels. `ProxboxJobTemplateExtension.buttons()` also renders a **Bug report** button on core Job detail pages for Proxbox sync jobs that ended in an error/unknown state (see `bug_report.py`).
- [`bug_report.py`](./bug_report.py): pure, read-only helper that assembles the failed-job **Bug report** modal context — plugin/NetBox versions, job metadata, formatted `log_entries`, a copy-to-clipboard `report_text`, and a prefilled netbox-proxbox GitHub *new issue* URL. Gated by `is_reportable_status(status)` (errored/failed or any unknown status).
- [`type_defs.py`](./type_defs.py): shared type aliases and lightweight protocol helpers used across the package.
- [`utils.py`](./utils.py): URL and host helpers, especially for the FastAPI backend and mkcert-aware local TLS handling.
- [`websocket_client.py`](./websocket_client.py): long-lived WebSocket client, message queue, and HTTP view used to stream backend messages into NetBox pages.
- [`signals.py`](./signals.py): Django signal handlers for automatic token generation and backend registration when enabled FastAPIEndpoint objects are created or updated.
- [`schemas/`](./schemas): Pydantic models and formatters for backend payloads, normalized sync context, and OpenAPI helpers.
- [`services/`](./services): backend proxy, schema caching, service status, and sync coordination helpers.
- [`management/`](./management): Django management commands package.
- [`templatetags/`](./templatetags): custom template tags for ProxBox templates.
- [`models/`](./models): persisted plugin models for Proxmox, remote NetBox, FastAPI, clusters, nodes, storage, backups, snapshots, task history, backup routines, replications, and settings.
- [`forms/`](./forms): create/edit, filter, and scheduling forms for plugin models and sync actions.
- [`tables/`](./tables): list-view table classes for endpoint, storage, backup, snapshot, replication, and cluster views.
- [`views/`](./views): dashboard pages, endpoint CRUD, sync actions, job helpers, status checks, and targeted sync buttons.
- [`api/`](./api): NetBox plugin API viewsets, serializers, filters, and URL wiring.
- [`migrations/`](./migrations): Django schema history for the plugin models.
- [`templates/`](./templates): bundled Django templates for plugin pages and template fragments.
- [`static/`](./static): bundled images, JS, CSS, SCSS, and generated theme assets.

## Data Flow

- Endpoint objects are created in NetBox through forms and model views.
- List and detail pages are rendered by classes in `views/` using tables, filtersets, and templates.
- Sync routes call the external ProxBox FastAPI backend using the configured `FastAPIEndpoint`. Two sync transport modes are available:
  - POST polling (traditional): the plugin waits for completion and returns a single JSON response.
  - GET SSE streaming: the plugin proxies `text/event-stream` from the FastAPI backend to the browser via `StreamingHttpResponse`. The browser JS parses SSE frames and renders granular per-object progress in real time.
- The API layer exposes the same main models through NetBox plugin API endpoints.
- Browser-side pages use templates plus JS from `static/netbox_proxbox/js/` for dashboard hydration, keepalive polling, SSE streaming, log rendering, and WebSocket updates.
- Operator recovery for missing Proxbox bootstrap/custom-field setup is exposed
  through `views/sync_state_repair.py` and the shared
  `partials/bootstrap_status_card.html`. The card appears on Home and Settings,
  loads proxbox-api `GET /extras/bootstrap-status` on demand through the
  session-gated `sync-state/bootstrap-status/` JSON endpoint for users with
  `view_fastapiendpoint`, and posts to `sync-state/repair/` for users with
  `core.add_job`. Both backend calls resolve the FastAPI endpoint through a
  request-user-restricted queryset before passing the endpoint ID to the backend
  proxy. The POST path calls
  `POST /extras/custom-fields/reconcile` through `services/backend_proxy.py`
  before queuing a normal full `ProxboxSyncJob`; it must remain a UI/session
  action with flash-message error handling, not a new sync transport.

## Import / Export

All three endpoint types support CSV, JSON, and YAML export via dedicated `ExportView` classes in `views/endpoints/`. Export comes in two modes:

- **Safe export** (no credentials): available to any user with `view` permission.
- **Sensitive export** (includes credentials): requires the user to supply a valid NetBox API token (v1 or v2) via the export-secrets modal. The token is validated server-side before the download is served.

Import uses NetBox's `BulkImportView`. All import forms auto-create missing `IPAddress` objects via `get_or_create` so data can move between NetBox instances without manual IPAM pre-population. Exported `id` columns are stripped before processing to prevent PK collisions.

**NetBoxEndpoint and FastAPIEndpoint are singleton-shaped.** If a record already exists when a bulk import is submitted, the import view intercepts the request and renders a confirmation page (`singleton_import_confirm.html`) before deleting the existing record and creating the replacement. Operational helpers use the first enabled FastAPI endpoint; disabled endpoints are inventory-only and must not trigger backend registration or HTTP probes. ProxmoxEndpoint allows multiple rows and has no singleton constraint.

For detailed implementation notes see [`views/endpoints/CLAUDE.md`](./views/endpoints/CLAUDE.md) and [`forms/CLAUDE.md`](./forms/CLAUDE.md).

## Dependencies

- Inbound: NetBox plugin loader imports `config`, NetBox route registration imports `urls.py`, and the menu system imports `navigation.py`.
- Outbound: Django/NetBox APIs, `requests`, `websockets`, the external ProxBox FastAPI service, GitHub raw content for the contributing page, and standard NetBox core models like `users.Token`, `ipam.IPAddress`, `virtualization.VirtualMachine`, and `virtualization.Cluster`.

## Optional netbox-rpc companion card (home dashboard)

The home dashboard renders an optional **netbox-rpc** companion card when that
plugin is installed. `integrations/rpc.py::rpc_dashboard_context()` is a soft,
best-effort helper (never imports `netbox_rpc` at module load; `try/except
ImportError`; never issues a network call) that returns
`{"rpc_integration": {installed, enabled, backend_name, backend_url, home_url,
settings_supported}}` — or `{}` when netbox-rpc is absent, so the card is simply
omitted. It reads `netbox_rpc.RpcPluginSettings.get_solo()` for the opt-in
`enabled` flag and configured backend when present, and degrades cleanly against
an older netbox-rpc that predates that model. `views/home_context.py`
(`_build_rpc_integration_context`) wires it into `build_home_dashboard_context`,
and `templates/netbox_proxbox/home.html` renders the card (config state +
"Configure & opt in" link to `/plugins/rpc/`). Live backend reachability is left
to the netbox-rpc landing page's own *Test connection* action, so the Proxbox
dashboard render stays fast. Guarded by `tests/test_rpc_integration.py`.

## Per-endpoint netbox-rpc enablement (optional companion)

`ProxmoxEndpoint.rpc_enabled` is a **tri-state** (`BooleanField(null=True)`)
per-endpoint override for netbox-rpc operations against that endpoint, mirroring
the `overwrite_*` pattern. `ProxmoxEndpoint.effective_rpc_enabled()` resolves it:
netbox-rpc installation is a precondition for all paths; after the
**function-local, guarded** `try/except ImportError` import succeeds, the
per-endpoint value wins when set (`is not None`, so an explicit `False` is
respected); otherwise it **inherits the global** netbox-rpc opt-in flag
(`netbox_rpc.RpcPluginSettings.enabled`). This is the allowed **optional**
proxbox→rpc integration; the model never imports netbox-rpc at load time and
**must never depend on the NMS stack**.

The field is editable on the endpoint **Settings tab** (new **RPC** pane,
`NullBooleanSelect`, `RPC_FIELD_GROUPS` in `constants.py`) and exposed over REST
(`ProxmoxEndpointSerializer.rpc_enabled` writable + read-only
`effective_rpc_enabled` `SerializerMethodField`) so external callers can read the
resolved value. Added by migration `0059_proxmoxendpoint_rpc_enabled`
(`add_field_idempotent`). Contract-tested in `tests/test_rpc_endpoint_override.py`
and `tests/test_frontend_contracts.py` (5-pane Settings tab).

**Non-enforcing here:** resolution + UI only. The fail-closed *gate* (block RPC
against a disabled endpoint) lives in the layer allowed to read the endpoint —
netbox-proxbox for RPC it initiates, and the NMS layer (nms-backend) for
dispatch — and ships separately once operators have enabled RPC.

## Configuration

`ProxboxPluginSettings` (see [`models/plugin_settings.py`](./models/plugin_settings.py))
is the singleton that holds runtime tunables for both this plugin and the companion
`proxbox-api` backend. **New runtime tunables belong here, not in proxbox-api's
`.env`** — the backend reads them through `proxbox_api.runtime_settings.get_*` which
resolves env > plugin settings > default with a 5-minute cache. See
[top-level `CLAUDE.md` → Plugin settings and configuration](../CLAUDE.md) for the full
policy and the short list of `.env`-only operator infrastructure variables.

Tenant assignment for Proxmox-synced NetBox `VirtualMachine` rows is plugin-side
post-sync behavior. Regex assignment is controlled by
`enable_tenant_name_regex` plus `tenant_name_regex_rules`; tag assignment is
controlled by `enable_tenant_tag_assignment`. The tag resolver requires both a
`cloud-customer` marker tag and exactly one `tenant-<slug>` tag, never overwrites
an existing VM tenant, and auto-creates missing `Tenant` rows under the
`cloud-customers` `TenantGroup`. Cluster inheritance is controlled by
`enable_tenant_from_cluster`; when enabled it runs after regex and tag assignment
and fills an empty VM tenant from `vm.cluster.tenant`, so explicit name/tag rules
win and existing VM tenants are never overwritten. Per-`ProxmoxEndpoint`
overrides inherit from the global plugin settings when left null.

Cloud-customer network discovery is also settings-backed. The plugin stores the
operator-designated IPAM Prefix ID, bridge, VLAN tag, gateway, and lock flag on
`ProxboxPluginSettings`; proxbox-api and nms-backend must resolve those fields
instead of hardcoding estate network values. Populate them with the idempotent
`python manage.py ensure_cloud_customer_network --prefix ... --vlan ... --gateway ... [--enable-lock]`
command.

## Installation Docs

- Docker-based NetBox installation guidance is documented at [`../docs/installation/3-installing-plugin-docker.md`](../docs/installation/3-installing-plugin-docker.md).
- Traditional host/venv installation remains documented in [`../docs/installation/2-installing-plugin-git.md`](../docs/installation/2-installing-plugin-git.md).

## Child Docs

- [`../CLAUDE.md`](../CLAUDE.md)
- [`api/CLAUDE.md`](./api/CLAUDE.md)
- [`forms/CLAUDE.md`](./forms/CLAUDE.md)
- [`management/CLAUDE.md`](./management/CLAUDE.md)
- [`management/commands/CLAUDE.md`](./management/commands/CLAUDE.md)
- [`migrations/CLAUDE.md`](./migrations/CLAUDE.md)
- [`models/CLAUDE.md`](./models/CLAUDE.md)
- [`schemas/CLAUDE.md`](./schemas/CLAUDE.md)
- [`services/CLAUDE.md`](./services/CLAUDE.md)
- [`static/CLAUDE.md`](./static/CLAUDE.md)
- [`tables/CLAUDE.md`](./tables/CLAUDE.md)
- [`templates/CLAUDE.md`](./templates/CLAUDE.md)
- [`templatetags/CLAUDE.md`](./templatetags/CLAUDE.md)
- [`views/CLAUDE.md`](./views/CLAUDE.md)
