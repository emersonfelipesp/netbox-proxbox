# Local Proxmox Mock

You can run the Proxmox mock API locally (without Docker) to test Proxbox routes and sync behavior.

The mock service is implemented at `tests/e2e/mock_proxmox_api.py`.

## 1) Install local dependencies

From the repository root:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[e2e]"
```

## 2) Start the mock API service

```bash
python tests/e2e/mock_proxmox_api.py --host 127.0.0.1 --port 8006
```

Alternative (same app, direct uvicorn module path):

```bash
uvicorn tests.e2e.mock_proxmox_api:app --host 127.0.0.1 --port 8006
```

## 3) Validate mock routes

```bash
curl -s http://127.0.0.1:8006/api2/json/version
curl -s http://127.0.0.1:8006/api2/json/cluster/status
curl -s http://127.0.0.1:8006/api2/json/cluster/resources
```

## 4) Change mock VM status (update-path testing)

You can mutate VM state to validate update sync behavior.

Set VM `101` to `stopped`:

```bash
curl -s -X POST http://127.0.0.1:8006/__admin/vm/101/status \
  -H 'Content-Type: application/json' \
  -d '{"status":"stopped"}'
```

Set it back to `running`:

```bash
curl -s -X POST http://127.0.0.1:8006/__admin/vm/101/status \
  -H 'Content-Type: application/json' \
  -d '{"status":"running"}'
```

## 5) Point Proxbox endpoint to local mock

When creating or editing the Proxmox endpoint in Proxbox/NetBox plugin, use:

- Host/domain: `127.0.0.1`
- Port: `8006`
- Username: `root@pam`
- Token name: `e2e`
- Token value: `e2e-secret`
- Verify SSL: disabled

If your backend runs in Docker and the mock runs on your host machine, use a host-reachable address (for example `host.docker.internal` where supported) instead of `127.0.0.1`.

## Native telemetry and qualification

The local fixture in `tests/e2e/mock_proxmox_api.py` preserves the Proxmox
response envelopes and shared VM state used by the stack tests. Its
`create_app(*, telemetry=None)` factory mounts the same router as the exported
module-level `app`. The standalone script retains its `--host` and `--port`
arguments. Install the project E2E extra to obtain FastAPI standard version
0.143.0 or later and its native OpenTelemetry dependencies.

Telemetry is public and opt-in. The application sets no collector endpoint,
service identity, credentials, or telemetry environment defaults. An operator
must set `FASTAPI_OTEL_AUTO_CONFIGURE=true` for native automatic setup and
can supply the standard OpenTelemetry environment or an explicit native
`TelemetryConfig`. The opt-in value is case-insensitive `true`; an explicit
`auto_configure` dictionary value takes precedence. Empty destinations and exporter values of `none` remain
authoritative. Explicit caller providers retain their identity and ownership.

`OTEL_SDK_DISABLED=true` disables all application signals and automatic
configuration, including when the caller supplies enabled configuration flags.
The factory copies that configuration rather than changing the caller's object.
Existing selected SDK trace and log providers still receive idempotent privacy
processors. The application creates no implicit provider while the SDK is
disabled. Caller providers can remain usable for a later caller-controlled
operation.

Privacy applies only to the `fastapi` instrumentation scope. Request paths and
queries are redacted before span export. Exception messages and stack traces
are removed from log attributes while exception classification remains.
Unrelated caller instrumentation is preserved. An exporter registered before
the log privacy processor can observe an earlier copy of a log record. The
caller must provide redaction for that pre-existing exporter. The tests do not
claim that a later processor retroactively protects an earlier exporter.

The native probe covers public defaults, explicit opt-in, empty destinations,
per-signal overrides, global and explicit providers, validation errors,
HTTP/WebSocket errors, repeated lifespans, and actual loopback OTLP protobuf
payloads. The separate SDK-disabled probe checks empty application records
before caller re-enablement, provider identity, idempotent privacy, caller-only
metrics, and late-exporter log privacy. The context regressions exercise both
normal and error paths of an excluded request nested inside an instrumented
request on the actual factory.

These are local fixture contracts. They do not prove production collector
delivery or NetBox database compatibility. Native application lifespan flushing
and explicit observer-owned provider shutdown are separate operations. Keep
the loopback receiver alive through provider shutdown. Do not interpret
observer teardown as evidence that the shipping application owns caller
providers or terminates all native exporters.

The Django matrix retains eight independent profiles and their exact companion
source identities. Its shared test input now includes the E2E dependencies.
Regenerate each composed hash lock through the project-pinned uv workflow and
update its reviewed checksums before running or publishing this source. Do not
reuse an older whole lock or companion workflow as the composed-source proof.
