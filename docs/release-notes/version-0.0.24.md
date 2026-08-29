# Version 0.0.24

> Historical behavior: this release admitted the wider 4.7 line. Current
> source narrows evaluation support to exact canonical `4.7.0-beta2`; see the
> latest release notes and compatibility matrix.

netbox-proxbox `0.0.24` pairs with `proxbox-api 0.0.20`,
`proxmox-sdk 0.0.13`, and the backend's REST dependency
`netbox-sdk 0.0.10`. The plugin now declares **two NetBox support tiers**: a
**stable** tier covering `4.5.8` through `4.6.99`, and a new **experimental**
tier covering `4.7.0` through `4.7.99`.

Current backend-runtime pairing: netbox-proxbox 0.0.24 <-> proxbox-api 0.0.20 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| >=4.5.8 | v0.0.24 | v0.0.20 | v0.0.10 | v0.0.13 |

## Experimental NetBox 4.7 support

This release is the first to load and run on NetBox `4.7`. It is deliberately
shipped as an **experimental** tier, not a certified one.

| NetBox line | Tier | Status |
|---|---|---|
| `4.5.8` - `4.6.99` | stable | certified and CI-gated |
| `4.7.0` - `4.7.99` | experimental | loads and runs; emits a startup warning |

- **What you get.** The plugin installs and runs on NetBox `4.7.0` - `4.7.99`.
  The version gate no longer rejects the 4.7 line outright.
- **How it announces itself.** Running on an experimental NetBox emits a Django
  system-check **`Warning`** (`netbox_proxbox.W001`), never an `Error`, so
  startup is not blocked. The `PLUGINS_CONFIG` opt-out silences that maturity
  notice only; it does not suppress unrelated checks.
- **What was required to get there.** View actions are declared as
  `ObjectAction` classes rather than the legacy attributes 4.7 removed,
  `from_db()` accepts the keyword arguments Django now passes, and the default
  VM-role seed migration was fixed for ltree-backed NetBox hierarchies. The
  shared compatibility contract moved to v2.
- **Evidence.** The Django test matrix runs `v4.7.0-beta1` as a **required**
  leg alongside `v4.5.8`, `v4.5.10`, `v4.6.0`, and `v4.6.6`, so admitting 4.7
  is demonstrated to be a pure widening rather than a regression trade.

### Known limitations of the experimental tier

- NetBox `4.7.0-beta1` is a pre-release. Its schema and internals can still
  drift before GA, so treat 4.7 as evaluation-grade rather than production.
- The 4.7 leg exercises netbox-proxbox itself. A combined cell covering every
  companion plugin at once is not possible yet, because released 4.7-capable
  companion artifacts do not exist.
- Production deployments should stay on the stable `4.5.8` - `4.6.99` tier.

## Compatibility and correctness

- Certifies NetBox `4.6.6`, including the PDM registry override required by its
  current plugin loading contract.
- Preserves serializer source identity and corrects storage-node capacity,
  detail-template, InfluxDB, and sync-state behavior against real Django/NetBox
  models.
- Treats an empty configured encryption key as uninitialized and safely creates
  the key when a primary endpoint secret is first stored.

## Release integrity

- Builds one wheel and one sdist from the exact tagged commit and publishes them
  to the Gitea Package Registry, which remains the artifact of record.
- Validates the tag against a strict version pattern before anything is built,
  and verifies the package is present in the registry after upload.
- Subscribes to the tag `push` event only. Gitea emits both `create` and `push`
  for a tag, and subscribing to both would start two immutable uploads for one
  version.
- Creates the public GitHub Release for final tags only. A release candidate
  never produces one, because that event is the sole trigger for the public PyPI
  upload and an rc must not reach PyPI as though it were final.
- Builds the public-index distributions from the same tagged commit, so what
  reaches TestPyPI and PyPI corresponds to the published source rather than a
  separately fetched copy. Uploads never use `--skip-existing`, so a failure
  always advances to a new immutable version rather than silently succeeding.
- Pushes tags and creates releases only against the single authorised GitHub
  repository.

### Known limitation: publication hardening is deferred

This release publishes through in-repository jobs on the existing shared
runners — the same path used by `0.0.23` and every currently published version.
The locked release control plane developed during this cycle is **not** in this
release, because the isolated runner fleet it requires does not exist yet.

Specifically, this version does **not** yet have: credential-free target builds,
an exact-byte sealed handoff to a separately administered isolated publisher,
supervisor-signed runner attestation, or egress-denied build isolation. Those
controls are implemented and reviewed in-tree, and re-land once the isolated
runners are provisioned.

This is a deliberate, tracked deferral rather than a regression: `0.0.24` ships
at the same publication posture as every release before it.

## Upgrade

Deploy `proxbox-api 0.0.20` first, then install `netbox-proxbox 0.0.24`, run
the normal NetBox migration and static-collection steps, restart NetBox and its
workers, and verify the Proxbox plugin API and synchronization health.
