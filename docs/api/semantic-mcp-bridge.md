# Semantic MCP Bridge

The Proxbox semantic MCP bridge defines how a compatible `netbox-sdk` client
will discover and invoke a small, versioned set of Proxbox operations through
the existing NetBox REST API. The bridge is intentionally a descriptor, not
another server: Proxbox publishes metadata, while `netbox-sdk` owns MCP
registration and sends ordinary authenticated HTTP requests to the declared
plugin-local routes.

!!! warning "Consumer activation is currently blocked"
    Proxbox publishes the producer-side descriptor, but no released
    `netbox-sdk` version has passed the immutable paired gate for this payload.
    The currently documented `netbox-sdk 0.0.10` pairing belongs only to the
    separate proxbox-api REST runtime and does **not** provide this MCP bridge.
    Do not expose these tools to an agent until
    `tests/fixtures/netbox_sdk_bridge_activation.json` names an exact compatible
    released version or commit, the paired gate passes that exact module
    origin, and committed CI explicitly provisions and validates the same
    artifact.

## Architecture

```mermaid
sequenceDiagram
    participant Agent as MCP client / agent
    participant SDK as netbox-sdk MCP bridge
    participant Root as Proxbox API root
    participant Manifest as Proxbox bridge-v1 manifest
    participant DRF as Existing DRF target view
    participant RQ as NetBox RQ job

    Agent->>SDK: Connect with the configured NetBox principal
    SDK->>Root: GET /api/plugins/proxbox/
    Root-->>SDK: mcp.schema_version + manifest URL
    SDK->>Manifest: GET /api/plugins/proxbox/mcp/
    Manifest-->>SDK: Strict tool schemas and fixed local paths
    SDK->>SDK: Validate schemas, confine paths, register tools
    Agent->>SDK: plugin_list_tools or plugin_call_tool
    SDK->>DRF: GET or POST /api/plugins/proxbox/sync/schedule/
    DRF->>DRF: Authenticate and require core.add_job
    alt schedule_sync accepted
        DRF->>RQ: Enqueue ProxboxSyncJob
        DRF-->>SDK: HTTP 201 job envelope
    else validation or authorization failure
        DRF-->>SDK: HTTP 400/401/403; no job enqueued
    end
    SDK-->>Agent: Schema-validated result or structured error
```

Ownership is deliberately split:

| Layer | Responsibility |
|---|---|
| Proxbox API root | Advertise bridge schema version `1` and the manifest URL only after exact SDK activation |
| Proxbox manifest | Describe tool names, fixed relative routes, effects, annotations, and strict JSON Schemas |
| Existing Proxbox DRF views | Enforce NetBox authentication, `core.add_job`, validation, visibility, and job dispatch |
| Compatible future `netbox-sdk` | Discover the manifest, validate it, confine paths to the plugin API root, expose the generic `plugin_list_tools` / `plugin_call_tool` MCP surface, hold the existing NetBox credential, validate inputs/outputs, and keep mutations disabled by default |
| MCP host / agent | Preserve operator intent, honor the mutation gate, and treat tool annotations as safety metadata rather than authorization |

Proxbox does **not** embed FastMCP, open an MCP listener, import `netbox-sdk` at
runtime, or store a second credential. The HTTP request made by the SDK is the
same request a REST client would make to the existing scheduling API.

## Discovery

After an exact SDK is activated, start at the authenticated plugin API root:

```text
GET /api/plugins/proxbox/
```

The root then contains the following member. An absolute manifest URL is
returned at runtime; the relative URL below is the portable representation.

<!-- mcp-example:api-root-discovery -->
```json
{
  "mcp": {
    "schema_version": "1",
    "manifest": "/api/plugins/proxbox/mcp/"
  }
}
```

While activation is blocked, the root deliberately omits `mcp` and direct
`GET /api/plugins/proxbox/mcp/` returns HTTP 503 with the checked activation
record. This prevents descriptor presence from being mistaken for consumer
compatibility.

The SDK then reads the descriptor:

```text
GET /api/plugins/proxbox/mcp/
```

The descriptor is static and read-only. Reading it never schedules a job. The
manifest declares relative paths such as `sync/schedule/`; a conforming SDK
must resolve them below `/api/plugins/proxbox/` and reject path or origin
escape. Do not concatenate a path supplied by a model or user.

Agents do not receive `list_sync_jobs` or `schedule_sync` as standalone MCP
tools. Discover the Proxbox descriptors through the generic MCP tool:

<!-- mcp-example:plugin-list-tools-input -->
```json
{
  "plugin": "proxbox"
}
```

Then invoke a descriptor through `plugin_call_tool`, passing the manifest input
inside its `arguments` member. The examples below show that complete envelope.
This invocation flow is a contract for the future activated SDK pair; the
read-only HTTP descriptor by itself does not prove that the installed SDK is
compatible.

## Authentication and authorization

Use the normal NetBox principal already configured in `netbox-sdk`. Do not put a
token in a prompt, tool argument, manifest cache, source file, log, or Proxbox
model. Proxbox never asks for an MCP-specific token.

The manifest view follows NetBox's `LOGIN_REQUIRED` setting through
`IsAuthenticatedOrLoginNotRequired`. A deployment with `LOGIN_REQUIRED=False`
may expose the descriptor anonymously. That does not authorize either tool:
both `GET` and `POST` on `sync/schedule/` independently require the caller to
hold `core.add_job`. Tool annotations are advisory metadata and never replace
that server-side permission check.

Expected authorization outcomes after consumer activation:

| Condition | Manifest | `list_sync_jobs` | `schedule_sync` |
|---|---:|---:|---:|
| Authenticated principal with `core.add_job` | 200 | 200 | 201 or validation 400 |
| Authenticated principal without `core.add_job` | 200 | 403 | 403 |
| Anonymous, `LOGIN_REQUIRED=True` | 401/403 | 401/403 | 401/403 |
| Anonymous, `LOGIN_REQUIRED=False` | 200 | 403 unless the effective principal is authorized | 403 unless the effective principal is authorized |

## Tool catalog

| Tool | HTTP target | Effect | Idempotent | Open-world | Purpose |
|---|---|---|---|---|---|
| `list_sync_jobs` | `GET sync/schedule/` | read | yes | no | List visible active, failed, and recurring Proxbox sync jobs |
| `schedule_sync` | `POST sync/schedule/` | destructive | no | yes | Queue an immediate, future, or recurring Proxbox synchronization |

### `list_sync_jobs`

The input is a strict empty object. Query fields and additional properties are
not part of bridge v1.

<!-- mcp-example:list-sync-jobs-input -->
```json
{
  "plugin": "proxbox",
  "tool": "list_sync_jobs",
  "arguments": {},
  "dry_run": false
}
```

The result uses the existing schedule-list envelope:

<!-- mcp-example:list-sync-jobs-output -->
```json
{
  "plugin": "proxbox",
  "tool": "list_sync_jobs",
  "effect": "read",
  "status": 200,
  "headers": {"Content-Type": "application/json"},
  "body": {
    "count": 1,
    "scheduled_jobs": [
      {
        "id": 42,
        "pk": 42,
        "name": "nightly-inventory",
        "sync_types": ["all"],
        "schedule": "2099-01-15T03:00:00Z",
        "interval": 1440,
        "status": "scheduled"
      }
    ]
  }
}
```

The list is generated through the existing request-aware helper. The NetBox
principal's visibility remains authoritative; the manifest does not create a
separate job index.

### `schedule_sync`

This tool queues work. It is destructive and non-idempotent: reconciliation
may remove stale records from **NetBox inventory**, and retrying the same call
may enqueue a second job. This bridge does not delete Proxmox guests, disks,
snapshots, backups, or infrastructure, but clients must still use the SDK's
disabled-by-default mutation gate and preserve the operator's scheduling intent.

#### Input fields

| Field | Required | Contract |
|---|---:|---|
| `sync_stages` | yes | Nonempty, unique list of the 13 concrete manifest-declared slugs. Bridge v1 does not advertise the legacy `"all"` sentinel. A full sync is the exact complete list shown below. |
| `job_name` | no | String of at most 200 characters. Whitespace at the edges is removed before enqueue; an empty value uses the default job name. |
| `schedule_at` | no | Strict RFC 3339 date-time with an explicit `Z` or numeric offset, and it must resolve to a future representable instant. A `:60` value is accepted only when the normalized UTC instant crosses a month boundary; arbitrary-minute leap seconds and normalization overflow are HTTP 400. For example, `2100-01-01T00:59:60+01:00` is the same accepted instant as `2099-12-31T23:59:60Z`, while `2026-08-12T12:34:60Z`, `9999-12-31T23:59:60Z`, and `9999-12-31T23:59:59-23:59` reject. Omit or send `null` for immediate execution unless recurrence is requested. |
| `recurrence` | no | Object containing exactly one of `minutes`, `hours`, `days`, or `weeks`, with a positive JSON Schema integer bounded so the converted minute count is at most `2147483647`. A finite mathematically integral JSON number such as `6.0` is an integer and is normalized to Python `int`; booleans, strings, nonintegral numbers, and non-finite numbers are rejected. Omit for a one-shot job. |
| `proxmox_endpoint_ids` | no | Nonempty, unique list of positive signed-64-bit NetBox PKs (`1..9223372036854775807`). Integer JSON literals retain the full range. Decimal/exponent forms such as `7.0` normalize only within the exact IEEE-754 safe range `1..9007199254740991`; larger float/Decimal values reject before ORM lookup because a JSON parser may already have rounded their identity. Booleans, strings, nonintegral/non-finite values, and signed-64 overflow also reject. Every requested row must exist and be enabled or the whole request fails. Omit for all enabled Proxmox endpoints. |

`sync_types`, `interval_value`, `interval_unit`, and `netbox_endpoint_ids` are
legacy REST fields, not bridge-v1 arguments; `additionalProperties: false`
rejects them before dispatch. An explicit empty Proxmox endpoint list is also
rejected; it never degrades into the wider all-endpoints operation. Omission is
the only way to request that behavior.

The exact recurrence maxima are `2147483647` minutes, `35791394` hours,
`1491308` days, or `213044` weeks. Each maximum converts to no more than the
NetBox Job `PositiveIntegerField` ceiling of `2147483647` minutes; the next
integer for any unit is HTTP 400 and enqueues nothing.

#### Stage selection and invariant reconciliation

`sync_stages` selects only the 13 dependency-ordered backend SSE stages. Every
job scheduled through this bridge first performs endpoint preflight, which may
push current NetBox and Proxmox endpoint configuration/credentials to
proxbox-api. It then reconciles cluster/node inventory, datacenter firewall
objects, and datacenter CPU models for the job's endpoint scope before the
selected SSE stages. VM-template inventory is also reconciled before those
stages unless `sync_mode_vm_template=disabled`. These invariant passes can
create, update, or remove stale **NetBox** inventory even when their names are
absent from `sync_stages`; a narrow stage selection does not isolate them.

The exact complete unique 13-stage public list is translated internally to the
legacy `["all"]` job identity after validation. This keeps recurring-job hints
and repair debounce correct without advertising or accepting the `"all"`
sentinel through MCP. Every proper subset remains an explicit stage list.

#### Immediate all-endpoint sync

Use the smallest request when the operator explicitly asks for an immediate
full synchronization across enabled endpoints:

<!-- mcp-example:schedule-immediate-input -->
```json
{
  "plugin": "proxbox",
  "tool": "schedule_sync",
  "arguments": {
    "sync_stages": [
      "virtual-machines",
      "storage",
      "vm-disks",
      "vm-backups",
      "vm-snapshots",
      "devices",
      "network-interfaces",
      "vm-interfaces",
      "ip-addresses",
      "sdn",
      "backup-routines",
      "replications",
      "task-history"
    ],
    "job_name": "operator-requested-full-sync"
  },
  "dry_run": false
}
```

#### Future scoped sync

Proxmox endpoint IDs are NetBox primary keys, not cluster IDs, node IDs, or the
backend's wire IDs. Discover and verify them through the normal NetBox API
before presenting or invoking this request. Bridge v1 intentionally exposes no
NetBox-endpoint scope because the producer does not implement that scope
end-to-end.

<!-- mcp-example:schedule-future-scoped-input -->
```json
{
  "plugin": "proxbox",
  "tool": "schedule_sync",
  "arguments": {
    "sync_stages": ["virtual-machines", "storage"],
    "job_name": "maintenance-window-inventory",
    "schedule_at": "2099-01-15T03:00:00Z",
    "proxmox_endpoint_ids": [7, 9]
  },
  "dry_run": false
}
```

If either Proxmox endpoint is unknown or disabled, the server rejects the
entire request and enqueues nothing. It never silently filters `[7, 9]` down to
one endpoint.

#### Recurring sync

When recurrence is supplied without `schedule_at`, the server sets the first
run to its current local time. The interval is stored in minutes; this example
becomes `360` minutes.

<!-- mcp-example:schedule-recurring-input -->
```json
{
  "plugin": "proxbox",
  "tool": "schedule_sync",
  "arguments": {
    "sync_stages": ["devices", "network-interfaces"],
    "job_name": "six-hour-inventory",
    "recurrence": {"hours": 6},
    "proxmox_endpoint_ids": [7]
  },
  "dry_run": false
}
```

#### Success response

An accepted request returns HTTP 201 inside the generic MCP result. `job_id`
identifies the NetBox core Job.

<!-- mcp-example:schedule-sync-output -->
```json
{
  "plugin": "proxbox",
  "tool": "schedule_sync",
  "effect": "destructive",
  "status": 201,
  "headers": {"Content-Type": "application/json"},
  "body": {
    "ok": true,
    "job_id": 314,
    "message": "Sync job queued for immediate execution."
  }
}
```

Future or recurring jobs may instead return a message containing the resolved
schedule time. Treat `job_id`, not the human-readable message, as the stable
identifier.

## Safe agent interaction sequence

1. Require an activated exact SDK identity in
   `tests/fixtures/netbox_sdk_bridge_activation.json` and matching successful
   immutable CI evidence. A readable manifest is not activation.
2. Discover the plugin API root and require `schema_version == "1"`.
3. Fetch the manifest through the URL returned by the root; do not guess a
   cross-origin target.
4. Call `plugin_list_tools` with `{"plugin":"proxbox"}` and let the exact gated SDK
   validate the manifest. Do not create a second Proxbox MCP transport or credential.
5. Invoke `list_sync_jobs` only through `plugin_call_tool` with
   `plugin="proxbox"`, `tool="list_sync_jobs"`, and `arguments={}`.
6. Before invoking `schedule_sync` through the same generic envelope, preserve
   the user's requested sync stages, Proxmox scope,
   timing, and recurrence. Do not convert an informational request into a sync.
7. Keep the SDK mutation gate disabled unless the operator or host policy accepts
   the blast radius: `NETBOX_MCP_ALLOW_MUTATIONS=1` / `--allow-mutations` is a
   single server-wide switch that enables every MCP mutation, not only Proxbox
   `schedule_sync`. The flag is not per plugin or per tool.
8. Prefer explicit, verified Proxmox endpoint IDs for narrow work. Omit scope
   only when all enabled endpoints are truly intended; never send `[]` as a
   placeholder.
9. Submit once. A timeout, transport failure, invalid response, or 5xx after
   dispatch leaves a non-idempotent outcome ambiguous. The current list schema
   does not carry the submitted scope or a stable request identity, so listing
   jobs cannot prove absence: never auto-retry. Report the ambiguity and require
   an operator to reconcile the NetBox job records before a deliberate retry.
10. Never retry a 400 or 403 as a broader scope. A compatible SDK may turn
   a non-2xx write into an MCP error and may expose only its HTTP status, not the
   DRF body. Do not guess which field failed; let an operator inspect the
   authenticated REST response or NetBox logs before constructing a new call.

## Errors and fail-closed behavior

Validation failures use the existing DRF error envelope and enqueue no job. The
following is the target endpoint's direct HTTP body, not a successful
`plugin_call_tool` result. A compatible SDK may represent non-2xx writes as MCP
errors and retain only the status in the agent-visible message.

<!-- mcp-example:validation-error-output -->
```json
{
  "errors": {
    "proxmox_endpoint_ids": [
      "Unknown or disabled endpoint ID(s): [99]"
    ]
  }
}
```

| HTTP status | Meaning | Client action |
|---:|---|---|
| 200 | Manifest or job list returned | Validate the response against the declared output schema. |
| 201 | Sync job accepted | Record `job_id`; do not enqueue a duplicate. |
| 400 | Invalid schema, past time, bad recurrence, bad scope, or unavailable Proxmox endpoint | Do not resubmit automatically. If the generic MCP error omits the DRF body, require operator inspection; never guess by dropping fields or widening scope. |
| 401 | Authentication required or invalid | Repair the existing NetBox SDK authentication. Do not pass credentials as tool input. |
| 403 | Principal lacks `core.add_job` | Ask an administrator for the least privilege needed; do not bypass DRF. |
| 404 | Plugin or declared route unavailable | Treat the installed plugin as incompatible or not enabled; refresh discovery. |
| 5xx | NetBox-side failure after dispatch may be ambiguous | Report it and inspect NetBox/RQ health. Never auto-retry `schedule_sync`. |

Common 400 cases include:

- an unknown property, because bridge v1 has `additionalProperties: false`;
- an empty or duplicate endpoint list, a boolean/string/nonintegral/non-finite
  endpoint ID, a decimal/exponent-form endpoint ID above `9007199254740991`, or
  an integer literal outside `1..9223372036854775807`;
- duplicate sync stages, an empty `sync_stages` list, or the legacy `"all"` sentinel;
- a missing, extra, nonpositive, non-integer, or too-large recurrence member;
- a timezone-less or otherwise invalid RFC 3339 `schedule_at`, including a leap
  second whose normalized instant overflows the supported datetime range;
- `schedule_at` in the past; and
- `job_name` longer than 200 characters.

## Trust boundary and security notes

- The descriptor can describe a destructive operation but cannot execute it.
- The global SDK mutation gate reduces accidental calls; it is not authorization
  and enabling it enables all mutation tools exposed by that MCP server.
- `core.add_job` on the target DRF view is the server-side authorization gate.
- Tool schemas are validation boundaries, not a source of credentials.
- Proxbox endpoint PKs are local NetBox identifiers. Never reinterpret an ID
  copied from another NetBox instance.
- An omitted Proxmox scope is intentionally broad. A disabled or missing local
  endpoint remains a hard operational gate during the job preflight.
- The scheduling bridge reaches the Proxmox-to-NetBox reflection pipeline. It
  does not opt into the separate NetBox-to-Proxmox intent/delete workflow and
  cannot bypass its five-lock deletion chain.
- Do not cache the manifest longer than the owning SDK's compatibility policy.
  Rediscover after plugin upgrades or a schema-version mismatch.

## Compatibility and versioning

Bridge schema version `"1"` at the API root and manifest identifies the generic
descriptor protocol: manifest/tool envelope shape, fixed plugin-local routing,
effects/annotations, and the supported JSON Schema processing rules. It is
**not** a frozen version number for every plugin's tool names or input payload.
`tests/fixtures/proxbox_bridge_v1.json` is a Proxbox-owned generated-contract
snapshot, not a second SDK authority or a fixture that both repositories must
copy.

Any Proxbox tool-name, path, effect, required-field, or meaning change still
needs explicit producer/consumer compatibility review and rediscovery. A
generic descriptor-protocol change requires a new bridge schema version;
plugin-specific payload evolution does not become safe merely because the
string remains `"1"`.

No released SDK identity is currently certified for this descriptor.
`tests/fixtures/netbox_sdk_bridge_activation.json` therefore remains
`state="blocked"` with no version or commit, and ordinary CI asserts that the
paired script is not presented as an active gate. In that state the API root
omits `mcp` and the direct manifest endpoint returns 503. Activation requires a later,
explicit change that provisions one immutable SDK release checkout, records its
exact released version, full commit, and module origin, adds the paired command to
committed CI, and changes the artifact only after every vector passes.

The manual paired gate also fails closed. It requires an explicit SDK root,
the fixed relative module origin, and one exact commit whose complete
`netbox_sdk/` package inventory matches the checkout. It materializes
the package from Git blob objects into a private temporary tree before import,
after bounded offline verification of the complete commit/tree/blob graph and
an explicit rehash of every imported blob;
dirty tracked package files, version spoofing, untracked package modules, ambient `PYTHONPATH`,
and arbitrary installed packages are not identity evidence. Run it as:

```bash
/path/to/netbox-sdk/.venv/bin/python -I tests/validate_paired_netbox_sdk_bridge.py \
  --sdk-root /path/to/netbox-sdk \
  --expected-commit <full-lowercase-commit-sha> \
  --expected-version <exact-released-version> \
  --expected-environment-root /path/to/netbox-sdk/.venv \
  --expected-module-origin netbox_sdk/plugin_bridge.py
```

The release activation separately records the version belonging to that exact
commit; a mutable source tree whose `__version__` merely matches is never
accepted. Do not substitute a branch name, range, or unreleased version guess.
The required SDK behavior includes lossless large endpoint identity, rejection
of unsafe integral floats, and acceptance of `:60` only when the normalized UTC
instant crosses a month boundary without calendar overflow.

The manifest is generated from pure Python without Django state, network I/O,
or credentials. Its choices are cross-checked against the canonical DRF
ChoiceSets, and its response fields are cross-checked against the actual
serializer in the real-NetBox test matrix.

## Verification and traceability

| Requirement | Automated evidence |
|---|---|
| Exact bridge-v1 wire contract | `tests/test_mcp_bridge_contract.py` plus `tests/fixtures/proxbox_bridge_v1.json` |
| Documentation links, safety text, and executable examples | `tests/test_mcp_bridge_docs.py` |
| API root and manifest discovery | `tests/test_mcp_bridge_django.py` |
| `LOGIN_REQUIRED` and `core.add_job` boundaries | `tests/test_mcp_bridge_django.py` |
| Read envelope and response serializer parity | Pure and real-Django MCP bridge suites |
| Immediate, future, recurring, scoped, and omitted-scope dispatch | `tests/test_mcp_bridge_django.py` |
| Strict input, lossless integer identity, safe-float boundary, signed-64-bit bounds, normalized-UTC month-boundary leap semantics, leap/offset overflow, and no-enqueue failures | Pure serializer contract plus real-Django route matrix |
| Paired SDK activation remains blocked until exact identity exists | `tests/fixtures/netbox_sdk_bridge_activation.json` plus `tests/test_mcp_bridge_contract.py` |
| Exact paired SDK descriptor, argument, and response validation after explicit provisioning | `<locked-python> -I tests/validate_paired_netbox_sdk_bridge.py --sdk-root ... --expected-commit ... --expected-version ... --expected-environment-root ... --expected-module-origin netbox_sdk/plugin_bridge.py` |
| Full-stage recurring hint and repair-debounce identity | Real-Django bridge suite plus `tests/test_schedule_hints.py` and `tests/test_operator_migration_ux.py` |
| No FastMCP, SDK import, or duplicate credential | `tests/test_mcp_bridge_contract.py` |
| Documentation build and link/navigation integrity | MkDocs strict build in local/CI gates |

## Troubleshooting

### The manifest is 401 or 403

Authenticate through the normal NetBox SDK configuration. If NetBox requires
login, anonymous discovery is intentionally unavailable.

### The manifest works but both tools return 403

The principal lacks `core.add_job`. This permission is required for listing as
well as scheduling because both operations reuse the protected schedule view.

### The manifest exists but the SDK tools are unavailable

That is the expected fail-closed state while
`tests/fixtures/netbox_sdk_bridge_activation.json` says `blocked`. Do not infer
compatibility from descriptor discovery or from the proxbox-api runtime's
historical `netbox-sdk 0.0.10` dependency. Wait for an exact released SDK
identity, immutable paired-gate evidence, and explicit CI activation.

### A scoped schedule returns 400

Verify every Proxmox endpoint PK exists in this NetBox and is enabled. Correct
the explicit scope; do not omit it to make the request pass unless the operator
actually intends all enabled endpoints.

### A recurring request runs immediately

That is expected when `recurrence` is supplied without `schedule_at`: the
server chooses its current local time for the first run. Set
a future ISO 8601 `schedule_at` when the first run must wait.

### The client reports an output-schema failure

Refresh discovery and compare the installed manifest with bridge v1. A plugin
or SDK version mismatch should fail closed. Do not disable output validation.

### A schedule call times out

Do not replay it automatically. Scheduling is non-idempotent and the first
request may have been accepted before the response was lost. `list_sync_jobs`
does not expose the submitted endpoint scope or a stable request identity, so
even a read cannot prove that retrying is safe. Report the ambiguous outcome and
require an operator to reconcile the NetBox job records before a deliberate retry.

## Related documentation

- [API reference](index.md)
- [API integration flow](../features/api-integration.md)
- [Scheduled sync](../features/scheduled-sync.md)
- [Background jobs](../features/background-jobs.md)
- [Authentication](../developer/authentication.md)
- [Headless sync operations](../operations/headless-sync.md)
