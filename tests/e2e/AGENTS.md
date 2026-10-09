# Local Proxmox mock guidance

The local mock uses `create_app(*, telemetry=None)` and a shared APIRouter.
Preserve every route, operation identity, response envelope, query filter and
shared VM state. The standalone launcher retains its host and port arguments.

Native telemetry is opt-in. Set no collector endpoint or service identity by
default. SDK disable overrides enabled factory flags without changing caller
configuration. Privacy processors protect selected SDK providers without
replacing them or taking ownership. A caller exporter attached before log
privacy requires caller-controlled redaction; late-only privacy is not a
blanket claim about pre-existing exporters.

Preserve the ten-mode native loopback contracts, separate global and explicit
SDK-disabled controls, and normal/error excluded nested-context regressions.
Native lifespan flushing and observer provider teardown have different owners.
These tests do not certify production delivery or the real NetBox database.

Install the E2E extra and regenerate the current canonical composed locks before
running the complete mocked suite. Keep all eight real-Django profiles and
exact companion identities. Read the parent `tests/CLAUDE.md` and the operator
guide in `docs/developer/proxmox-mock-local.md`.

Native automatic telemetry setup requires `FASTAPI_OTEL_AUTO_CONFIGURE=true` (case-insensitive)
unless the explicit `auto_configure` dictionary value overrides it. Do not add
collector, service identity, or automatic setup environment defaults. SDK-disabled
regressions construct enabled caller providers first and require positive caller
exports after the actual application lifespan while SDK disablement stays set.
