# Proxbox

Proxbox is a NetBox plugin that synchronizes Proxmox infrastructure data into NetBox. It keeps your DCIM up-to-date with real Proxmox clusters, nodes, virtual machines, containers, backups, and Firecracker micro-VM inventory used by the NMS Cloud runtime.

![netbox-proxbox architecture](docs/assets/netbox-proxbox-architecture.svg)

## What It Does

Proxbox discovers and syncs the following from Proxmox into NetBox:

- **Clusters and Nodes** — Proxmox cluster name, mode (cluster/standalone), quorum status, node count, and Proxmox VE version. Each node includes online status, IP address, CPU usage, memory usage, and uptime at sync time. Optionally link to NetBox Cluster and Device objects.
- **Virtual Machines** — VM status, resources, and configuration
- **Containers (LXC)** — Container details and settings
- **Firecracker Cloud inventory** — Host pools, host-agent VMs, image templates, and provisioned micro-VMs exposed separately from QEMU/LXC for NMS Cloud provisioning
- **VM Snapshots** — Point-in-time snapshots for recovery
- **VM Backups** — Backup jobs and restore points
- **Storage** — Datastores and storage content
- **Network Interfaces and IPs** — Proxmox NICs (`net0`, `net1`) as core NetBox VM interfaces, optional guest-OS interfaces (`ens18`, `eth0`) as plugin `GuestVMInterface` rows, and IP addresses assigned to VMs and containers
- **Backup Routines** — Backup job definitions from Proxmox
- **Replications** — Replication job status and configuration
- **Opt-in service monitoring** — Proxmox endpoint systemd service state collected through the optional `netbox-rpc` procedure `os.linux.proxmox.show_systemctl_services`

> **Note:** All metrics (CPU, memory, uptime, etc.) are captured as point-in-time snapshots at sync time, not continuous monitoring.

Sync runs on-demand from the NetBox UI or scheduled automatically via NetBox's job system.

Backend API keys are adopted fail-closed without making the token field
mandatory. The exact URL/IP, port, and TLS policy saved in the NetBox UI is the
automatic-discovery allowlist: the plugin probes only that configured target,
never follows redirects, reuses an encrypted key only after the target accepts
it, and generates a key only for an empty backend's one-time bootstrap. With no
endpoint row, discovery is bounded to `PLUGINS_CONFIG` and same-site names
derived from NetBox's trusted public origin; it never scans the network. An
initialized backend whose key is not locally recoverable remains fail-closed
and pending. Disabled endpoint rows make no network calls. Operators can still
submit a key explicitly for manual rotation or recovery.

## Additional Optional Plugins

Proxbox can be extended with standalone companion plugins. Install only the
plugins you need; `netbox-proxbox` remains the base plugin and must be enabled
before any companion plugin. The infrastructure inventory plugins declare
`netbox-proxbox>=0.0.18` as a dependency, while `netbox-packer` and
`netbox-rpc` follow the same operational conventions for the Proxbox plugin
family. `netbox-rpc` is an *operational* companion: when it is installed,
netbox-proxbox can run audited SSH procedures against Proxmox hosts (for
example installing the proxbox-api cloud-image-build SSH key on a node, or
collecting systemd service status for an endpoint) through the netbox-rpc engine
instead of handling SSH itself. The integration is a soft dependency — see
`netbox_proxbox/integrations/rpc.py`.

A companion package being present in the virtual environment does not enable
its Django app. Proxbox registers branching signals and PDM URL overrides only
when `netbox_branching` or `netbox_pdm`, respectively, is listed in `PLUGINS`;
installed-but-disabled companions therefore remain inert. Once a companion is
enabled, its imports are mandatory and startup fails if the installation is
broken. Encryption recovery is the one fail-closed maintenance exception:
netbox-pbs older than `0.0.1.post1` may start so its migrations can run, but
recovery and key mutation remain blocked until its encrypted-field schema is
upgraded.

| Package | NetBox plugin | What it adds |
|---------|---------------|--------------|
| [`netbox-pdm`](https://github.com/emersonfelipesp/netbox-pdm) | `netbox_pdm` | Inventories Proxmox Datacenter Manager endpoints and the PVE/PBS remotes managed by PDM. It links PDM remotes back to Proxbox Proxmox endpoints and, when installed, `netbox-pbs` backup servers. |
| [`netbox-pbs`](https://github.com/emersonfelipesp/netbox-pbs) | `netbox_pbs` | Inventories Proxmox Backup Server infrastructure, including PBS servers, datastores, backup snapshots, and scheduled job history. |
| [`netbox-ceph`](https://github.com/emersonfelipesp/netbox-ceph) | `netbox_ceph` | Adds read-only Ceph cluster inventory for Proxmox-managed Ceph: clusters, daemons, OSDs, pools, filesystems, CRUSH rules, flags, and health checks. |
| [`netbox-packer`](https://github.com/emersonfelipesp/netbox-packer) | `netbox_packer` | Tracks HashiCorp Packer image definitions and build execution records for Proxmox VM templates and image-factory workflows. |
| [`netbox-rpc`](https://github.com/emersonfelipesp/netbox-rpc) | `netbox_rpc` | Audited SSH/RPC procedure engine. netbox-proxbox optionally uses it to install SSH keys on Proxmox hosts and to collect Proxmox endpoint systemd service status via `netbox_proxbox.integrations.rpc`. |

Cloud-Init template-image creation through `netbox-packer` is a separately
authorized endpoint capability. The selected `ProxmoxEndpoint` must be enabled
with both `allow_writes=True` and the default-off
`allow_packer_template_builds=True`; the latter grants only netbox-packer
template builds. The Templates-tab action remains disabled until both gates
pass, and the narrow value is pushed to proxbox-api for enforcement at its
final write boundary only when the endpoint is also enabled and the broad gate
is open. Disabling the endpoint or either gate revokes that backend capability;
the endpoint detail page displays the explicit narrow assertion for audit. The
save-time push runs only after the NetBox transaction commits and records the
last backend-confirmed grant. Endpoint deletion remains blocked after an
unsuccessful revocation until proxbox-api confirms the grant is false. The two
template-build REST actions also require `core.run_proxmox_action`, recheck all
three endpoint gates before backend access, and translate the NetBox primary key
to proxbox-api's independent endpoint ID.

For a standard NetBox virtualenv install, activate the NetBox environment and
install the packages you want:

```bash
source /opt/netbox/venv/bin/activate
pip install 'netbox-pbs>=0.0.1.post1' netbox-pdm netbox-ceph netbox-packer
```

Enable the selected plugins in `netbox/netbox/configuration.py`. Keep
`netbox_proxbox` first. If you enable `netbox_pdm`, enable `netbox_pbs` before
it because PDM can link to PBS server records.

```python
PLUGINS = [
    "netbox_proxbox",
    "netbox_pbs",
    "netbox_pdm",
    "netbox_ceph",
    "netbox_packer",
]
```

Run migrations for the selected plugins, preserving the same order:

```bash
cd /opt/netbox/netbox
python3 manage.py migrate netbox_proxbox
python3 manage.py migrate netbox_pbs
python3 manage.py migrate netbox_pdm
python3 manage.py migrate netbox_ceph
python3 manage.py migrate netbox_packer
python3 manage.py collectstatic --no-input
sudo systemctl restart netbox netbox-rq
```

For `netbox-docker`, add the selected packages to `plugin_requirements.txt`,
enable the matching plugin module names in `configuration/plugins.py`, rebuild,
and run migrations:

```txt
netbox-pbs
netbox-pdm
netbox-ceph
netbox-packer
```

```bash
docker compose build
docker compose up -d
docker compose exec netbox /opt/netbox/netbox/manage.py migrate
```

Full companion-plugin details live under
[docs/companion-plugins/](./docs/companion-plugins/).

### Endpoint Enablement

Endpoint records are inventory/configuration objects even when disabled. For
`ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `PBSEndpoint`,
`PDMEndpoint`, and companion endpoint objects that expose an `enabled` field,
`enabled=False` is a hard operational gate: netbox-proxbox keeps the row visible
in UI/API output, but status checks, backend registration, OpenAPI fetches,
sync scopes, keepalive probes, and startup/signal pushes must return before any
proxbox-api or remote-service connection attempt.

The Proxmox Endpoints list shows the `Enabled` column by default. Operators can
select multiple rows and use **Enable Selected** or **Disable Selected** to
toggle the local `ProxmoxEndpoint.enabled` flag in bulk; those list actions do
not call proxbox-api or Proxmox.

Disabled Proxmox endpoints render as a gray **Disabled** status badge on the
list, detail page, and dashboard card. These UI surfaces do not attach live
status polling metadata for disabled rows, so the browser does not repaint an
administratively disabled endpoint as a red error.

### Proxmox Endpoint Service Monitoring

Service monitoring is opt-in per `ProxmoxEndpoint`. An endpoint is eligible only
when `allow_writes=True`, `access_methods="api_ssh"`, and the endpoint has a
complete registered SSH credential. Collection is agentless from the Proxbox
plugin perspective: netbox-proxbox creates a `netbox-rpc` `RPCExecution` for the
read-only procedure `os.linux.proxmox.show_systemctl_services` with params
`{proxmox_endpoint_id, units}` and assigned object set to the endpoint. The RPC
backend uses the endpoint's own SSH credential; netbox-proxbox does not open SSH
sockets or run shell commands itself.

Execution is asynchronous. Phase 1 queues the RPC job and records a pending
`ProxmoxServiceCollection`. Phase 2 runs from the periodic service-monitoring
tick and from the endpoint **Services** tab render path: completed executions are
projected into raw `ProxmoxServiceSample` rows, latest `ProxmoxServiceStatus`
rows, and endpoint heartbeat fields. A `reachable=false` RPC result is recorded
as an unreachable node outcome, not as a projection error.

### Cloud Portal Endpoint Allowlists

`ProxmoxEndpoint.allowed_tenants` controls which Proxmox endpoint rows are
eligible for tenant-scoped NMS Cloud callers. An empty allow-list means the
endpoint stays in the default/global pool. A non-empty allow-list pins that
endpoint to the listed tenants.

The paired `nms-backend` contract is intentionally asymmetric: if a tenant has
no explicit endpoint grants, it may still see global/default endpoints; once
that tenant matches any explicitly granted endpoint, the backend hides the
global pool and returns only the explicit matches. Use this to pin a tenant
such as Confitec to a single cluster without changing the default pool for
other tenants.

## Maintenance hardening notes

- **Primary endpoint secrets are encrypted at rest.** `ProxmoxEndpoint.password`,
  `ProxmoxEndpoint.token_value`, `FastAPIEndpoint.token`,
  `PBSEndpoint.token_secret`, and `PDMEndpoint.token_secret` now write through
  Fernet-encrypted `*_enc` database columns. The upgrade migration encrypts
  existing values and creates `ProxboxPluginSettings.encryption_key` if it was
  blank, so new endpoint saves do not persist those primary secrets in
  plaintext columns.
- **Encryption-key recovery is atomic and companion-aware.** The Settings page
  verifies every registered ciphertext before rotating the shared plugin key,
  or lets separately authorized operators selectively clear unrecoverable
  families after explicit destructive confirmation. When netbox-pbs is
  installed, its encrypted fallback proxbox-api key participates in the same
  rotation and reset; an unloaded companion's dormant table ciphertext plus
  missing installed companion models/tables block recovery rather than silently
  orphaning ciphertext. Registered model saves lock the
  settings row before validating ciphertext and persistence, while recovery
  locks all registered PostgreSQL tables; together these reject a writer that
  prepared ciphertext with the superseded key. Rotation also requires every
  configured proxbox-api target to return the paired versioned attestation that
  its active independent key decrypts every backend ciphertext; legacy
  source-only responses stay blocked so the plugin-key fallback cannot strand
  backend SQLite credentials. Every attempt writes a
  secret-free NetBox changelog event, and reset disables affected endpoints (or
  marks Firecracker hosts offline) until credentials are re-entered and the
  operator explicitly restores service.
- **Dual VM interface sync.** The plugin model surface supports the new
  `guest_os_model` strategy: keep Proxmox-side NICs as core
  `virtualization.VMInterface` rows named `net0`/`net1`, and store guest-agent
  OS names such as `ens18` in `GuestVMInterface`. `GuestVMInterfaceAddress`
  links those guest interfaces to the same core `ipam.IPAddress` rows already
  assigned to the core VM interface. The older `use_guest_agent_interface_name`
  flag is deprecated and only applies when `vm_interface_sync_strategy` is set
  to `legacy_rename`.
- **Operator repair path.** If Proxbox custom fields or bootstrap setup vanish
  after an upgrade, use **Repair / Rebuild Proxbox sync-state** on the Proxbox
  Home or Settings page. It reconciles proxbox-api custom-field definitions,
  queues a normal full sync job, and shows `GET /extras/bootstrap-status` output
  for troubleshooting. See
  [Recovering / Regenerating Proxbox Data](docs/operations/recovering-proxbox-data.md).

## What's New in v0.0.25

Current backend-runtime pairing: netbox-proxbox 0.0.25 <-> proxbox-api 0.0.20 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

Paired with backend: `proxbox-api 0.0.20`.

- **NetBox 4.6.6 certification.** Real-Django and Docker matrices cover the
  certified 4.5/4.6 range through 4.6.6.
- **Compatibility fixes.** Settings serialization, storage capacity, detail
  templates, InfluxDB metrics, sync-state models, and empty encryption-key
  recovery follow current NetBox/Django behavior.
- **Immutable staged release.** The target workflow emits exactly six
  credential-free data files: one wheel, one sdist, `release-manifest.json`,
  `release-request.json`, `runner-completion-attestation.json`, and
  `runner-completion-attestation.sig`. The locked control plane verifies the
  supervisor completion signature and publishes those exact wheel/sdist bytes
  before they progress through TestPyPI, production, and PyPI without
  rebuilding.

Full notes: [Release Notes - v0.0.24](docs/release-notes/version-0.0.24.md).

## What's New in v0.0.23.post1

Backend-runtime pairing: netbox-proxbox 0.0.23.post1 <-> proxbox-api (guest-VM-interface writer build / next release) <-> proxmox-sdk 0.0.12 <-> netbox-sdk 0.0.10.

Paired with backend: guest-VM-interface writer build / next release.

- **Universal guest OS interface model default.** `vm_interface_sync_strategy=guest_os_model` is now the default for existing installs as well as new installs; migration `0060` supersedes the `0.0.23` upgrade backfill that kept configured installs on `legacy_rename`.
- **Upgrade behavior change.** Proxmox NICs stay as `net0`/`net1` core `VMInterface` rows, guest-agent names such as `ens18` are stored in `GuestVMInterface`, and operators who want the old renaming behavior can re-select `legacy_rename` in plugin settings.

Full notes: [Release Notes - v0.0.23.post1](docs/release-notes/version-0.0.23.post1.md).

## What's New in v0.0.23

Backend-runtime pairing: netbox-proxbox 0.0.23 <-> proxbox-api (guest-VM-interface writer build / next release) <-> proxmox-sdk 0.0.12 <-> netbox-sdk 0.0.10.

Paired with backend: guest-VM-interface writer build / next release.

- **Dual VM interface sync.** Proxmox NICs stay as core `VMInterface` rows named `net0`/`net1`, while guest-agent OS interfaces such as `ens18` are stored in `GuestVMInterface` rows.
- **Shared IP ownership.** `GuestVMInterfaceAddress` links guest interfaces to the same core `ipam.IPAddress` objects already assigned to the mapped core VM interface.
- **Strategy control.** `vm_interface_sync_strategy=guest_os_model` is the new default for fresh installs; existing configured installs are backfilled to `legacy_rename` during migration `0059` so upgrades do not silently rename interfaces differently. This 0.0.23 upgrade backfill is superseded by v0.0.23.post1.

Full notes: [Release Notes - v0.0.23](docs/release-notes/version-0.0.23.md).

## What's New in v0.0.22

Backend-runtime pairing: netbox-proxbox 0.0.22 <-> proxbox-api 0.0.19.post5 <-> proxmox-sdk 0.0.12 <-> netbox-sdk 0.0.10.

Paired with backend [`proxbox-api 0.0.19.post5`](https://github.com/emersonfelipesp/proxbox-api).

- **Per-endpoint access methods.** Proxmox endpoints now expose API-only vs API+SSH transport selection, with the selected `access_methods` value sent to the backend registration payload so backend SSH paths can enforce the same gate.
- **Endpoint operator controls.** The form includes the Proxmox-side write-permission toggle, SSH credential-source selection, and a **Fetch host key** flow for pinned SSH fingerprints.
- **Inventory and API coverage.** This release includes tenant allowlists, bulk endpoint enablement, PDM endpoint sync, SDN inventory, Firecracker serializer hardening, and REST coverage for PBS/PDM endpoints plus read-only DeletionRequest and ProxmoxApplyJob audit endpoints.
- **Certification refresh.** NetBox compatibility remains `4.5.8` through `4.6.99`, now validated through NetBox `v4.6.4`.

Full notes: [Release Notes - v0.0.22](docs/release-notes/version-0.0.22.md).

## What's New in v0.0.21

Paired with backend [`proxbox-api 0.0.18.post5`](https://github.com/emersonfelipesp/proxbox-api).

- **Sync-mode filtering at source.** Per-record VM and VM-template filtering is enforced by the paired backend through `sync_mode_vm` and `sync_mode_vm_template` query params, so disabled modes no longer create dependent NetBox objects for skipped VMs.
- **Batch and stream hardening.** VM sync uses two-phase batch processing, isolates per-VM dispatch failures, matches interface-dense guest aliases by name, and emits partial-failure stream frames for operator visibility.
- **Backend SDK pairing.** This release pairs with `proxmox-sdk 0.0.12` and `netbox-sdk 0.0.10` only through the separate proxbox-api REST runtime.

Full notes: [Release Notes - v0.0.21](docs/release-notes/version-0.0.21.md).

## What's New in v0.0.20.post3

Paired with backend [`proxbox-api 0.0.17.post1`](https://github.com/emersonfelipesp/proxbox-api).

- **Disabled endpoints never connect.** Endpoint-like rows with `enabled=False` remain visible as inventory/configuration records, but Proxbox status, keepalive, backend registration, OpenAPI, sync, startup, signal, PBS, PDM, and companion endpoint paths now return before any proxbox-api or remote-service connection attempt.
- **Maintenance guardrails.** LLM and developer docs now describe the all-endpoint enabled-field invariant, and the regression suite covers PBSEndpoint/PDMEndpoint shared `EndpointBase.enabled` behavior plus shared guard wiring.

Full notes: [Release Notes - v0.0.20.post3](docs/release-notes/version-0.0.20.post3.md).

## What's New in v0.0.20.post2

Paired with backend [`proxbox-api 0.0.17.post1`](https://github.com/emersonfelipesp/proxbox-api).

- **Latest Sync Jobs on the homepage.** The plugin homepage now includes a read-only table with the five latest Proxbox sync jobs and a **View all sync jobs** button after the additional plugin endpoint cards.

Full notes: [Release Notes - v0.0.20.post2](docs/release-notes/version-0.0.20.post2.md).

## What's New in v0.0.20.post1

Paired with backend [`proxbox-api 0.0.17.post1`](https://github.com/emersonfelipesp/proxbox-api).

- **VM-template sync job wiring.** `ProxboxSyncJob` now calls the existing `sync_vm_templates()` stage, so `ProxmoxVMTemplate` inventory is populated during full/scheduled syncs instead of staying empty.

Full notes: [Release Notes - v0.0.20.post1](docs/release-notes/version-0.0.20.post1.md).

## What's New in v0.0.20

Paired with backend [`proxbox-api 0.0.17`](https://github.com/emersonfelipesp/proxbox-api).

- **IP-address ownership safety.** The paired backend prevents VM-interface IP sync from taking over an address that already belongs to another interface.
- **Interface-batch settings persistence.** `interface_batch_size` and `interface_batch_delay_ms` entered on the plugin Settings page now persist to the database.

Full notes: [Release Notes - v0.0.20](docs/release-notes/version-0.0.20.md).

## What's New in v0.0.19

Paired with backend [`proxbox-api 0.0.16`](https://github.com/emersonfelipesp/proxbox-api).

- **Historical FastAPI endpoint token drift fix (superseded).** v0.0.19 added an explicit-token recovery path for proxbox-api key rotation. Current code replaces its former bootstrap bypass with the fail-closed adoption boundary described above.
- **Canonical FastAPI trust boundary.** Direct-model and REST paths validate the backend authority before any request, reject URL injection syntax, bracket IPv6 literals, preserve omitted secret ciphertext, and treat disabled WebSocket/storage consumers as absolute no-network paths.
- **PBS/PDM `host` compatibility property.** `PBSEndpoint` and `PDMEndpoint` now expose a `host` property bridging the field-name difference with proxbox-api's SQLite column.
- **PBS/PDM `timeout_seconds` compatibility property.** Both models now expose a `timeout_seconds` property to match the proxbox-api SQLite column name.

Full notes: [Release Notes — v0.0.19](docs/release-notes/version-0.0.19.md).

## What's New in v0.0.18

Paired with backend [`proxbox-api 0.0.14`](https://github.com/emersonfelipesp/proxbox-api).

- **Full PVE 9.2 support.** New models for SDN fabrics, route maps, prefix lists, and custom datacenter CPU models, plus automated sync services. Completed per-node firewall sync. HA arm/disarm action views. `ProxmoxNode.location` field.

Full notes: [Release Notes — v0.0.18](https://emersonfelipesp.github.io/netbox-proxbox/release-notes/version-0.0.18/).

## Compatibility Matrix

| NetBox | netbox-proxbox | proxbox-api | proxbox-api internal netbox-sdk (REST only) | proxmox-sdk |
|--------|----------------|-------------|------------|-------------|
| 4.5.8-4.6.x; exact canonical 4.7.0-beta2 | v0.0.25 | v0.0.20 | v0.0.10 | v0.0.13 |
| >=4.5.8 | v0.0.23.post1 | guest-VM-interface writer build / next release | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.23 | guest-VM-interface writer build / next release | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.22 | v0.0.19.post5 | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.21 | v0.0.18.post5 | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.20.post3 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20.post2 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20.post1 | v0.0.17.post1 | v0.0.9.post1 | v0.0.11.post1 |
| >=4.5.8 | v0.0.20 | v0.0.17 | v0.0.8.post1 | v0.0.11 |
| >=4.5.8 | v0.0.19 | v0.0.16 | v0.0.8.post1 | v0.0.9 |
| >=4.5.8 | v0.0.18.post1 | v0.0.14 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8 | v0.0.18 | v0.0.14 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8 | v0.0.17 | v0.0.13 | v0.0.8.post1 | v0.0.3.post1 |

See [COMPATIBILITY.md](COMPATIBILITY.md) for the full version compatibility table.

### NetBox support tiers

`netbox-proxbox` declares two NetBox support tiers, defined once in
[`netbox_proxbox/compat.py`](netbox_proxbox/compat.py) and shared verbatim
across the whole Proxbox plugin stack:

| Tier | NetBox range | What it means |
|---|---|---|
| **Stable** | `4.5.8` – `4.6.99` | Admitted silently. Directly exercised in CI at v4.5.8, v4.5.10, v4.6.0 and v4.6.6. |
| **Experimental** | exact canonical `4.7.0-beta2` | Loads and runs normally for evaluation; the upstream pre-release is not production-certified, so the plugin warns once at startup. |

The exact beta2 support needs **no configuration at all** — no setting, opt-in
flag, or install step. On that canonical release you will see one warning per
plugin, from `manage.py check` and in the startup log:

```
WARNINGS:
?: (netbox_proxbox.W001) Proxbox is running on NetBox 4.7.0-beta2, which is
   supported on an experimental basis only. Certified support covers NetBox
   4.5.8 through 4.6.99. NetBox 4.7.0-beta2 is also an upstream pre-release:
   upstream does not support pre-releases in production and does not guarantee
   an upgrade path from a pre-release to the final release. Use it for
   evaluation on disposable data only.
   HINT: The plugin itself is operational on this release; this is a maturity
   notice, not a plugin fault. Do not treat it as clearance to run a NetBox
   pre-release in production — that restriction is upstream's, and silencing
   this notice does not lift it. On an evaluation install you can quiet it with
   PLUGINS_CONFIG['netbox_proxbox']['silence_netbox_compatibility_warning'] = True.
```

It is a warning, never an error — it cannot block NetBox from starting.

**Silencing is for evaluation installs only.** The
notice above is the only thing telling you the release is unsupported upstream
and has no guaranteed upgrade path to GA; quieting it does not change either
fact. It does not admit a later prerelease or GA build.

**To silence it**, set the key in this plugin's `PLUGINS_CONFIG` entry:

```python
PLUGINS_CONFIG = {
    "netbox_proxbox": {"silence_netbox_compatibility_warning": True},
}
```

That silences both the system check and the startup log line.

> Django's own `SILENCED_SYSTEM_CHECKS` is honoured too, but **not from
> `configuration.py`** — NetBox's `settings.py` imports an explicit list of
> named settings and that one is not on it, so setting it there has no effect.
> It only applies through NetBox's `local_settings.py` hatch, which upstream
> labels unsupported. Use the `PLUGINS_CONFIG` key above.

NetBox releases below `4.5.8` and above bare `4.7.0` are refused by NetBox's
stock plugin version gate. Because NetBox passes the same bare `4.7.0` for
beta2, later prereleases, and GA, this plugin additionally reads canonical
`release.yaml`: only `version: "4.7.0"` plus `designation: "beta2"` is admitted.
An unreviewed 4.7 identity raises `IncompatiblePluginError`; NetBox warns, omits
the plugin from `registry["plugins"]["installed"]`, and continues startup.

> **Upgrading to NetBox 4.7 means upgrading the whole plugin stack.** A
> Proxbox-family plugin left at the old `4.6.99` ceiling does not stop NetBox
> from starting — `settings.py` catches the incompatibility, warns, and
> **silently skips that plugin**. The symptom is an absence (missing views, API
> routes and jobs), not an error, and a health probe against NetBox still
> passes. Upgrade `netbox-proxbox`, `netbox-ceph`, `netbox-packer`,
> `netbox-pbs` and `netbox-pdm` together, then confirm each is registered with
> `apps.is_installed(...)`. On 4.5.8–4.6.x, mixed versions remain fine.

> **On beta version strings.** NetBox splits its release identity: at tag
> `v4.7.0-beta2`, canonical `release.yaml` carries `version: "4.7.0"` with
> `designation: "beta2"`, and NetBox passes only bare `"4.7.0"` to the stock
> plugin gate. The declared ceiling is therefore `4.7.0`, with a second
> fail-closed canonical identity check. Optional `local/release.yaml` may add
> only informational `build`; it cannot override version or designation.

## Requirements

- NetBox 4.5.8 through 4.6.x (stable), or exact canonical 4.7.0-beta2
  (experimental evaluation only — see above)
- Verified with NetBox v4.5.8 through v4.5.10, v4.6.0 through v4.6.6, and
  exact v4.7.0-beta2 commit
  `aa1d49d0f5021a28e6efc2d0364b84c5bcec7137` (experimental tier); the source
  matrix verifies release metadata and installs commit-bound, hash-checked
  Python 3.12/Linux dependency locks
- Python 3.12+
- Proxmox VE 7.x, 8.x, or 9.x (PVE 9 requires `VM.GuestAgent.Audit` on the API role; see "Troubleshooting" below for the PVE 9 auth checklist)
- Proxbox API backend as a separately deployed service (see below)

## Quick Start

Choose the installation path that matches your NetBox deployment:

- **Standard NetBox install (venv on host):** follow steps below.
- **NetBox Docker install (`netbox-docker`):** use the Docker-specific workflow in [Installing the Plugin in Docker-Based NetBox Deployments](./docs/installation/3-installing-plugin-docker.md).

1. **Install the plugin** into your NetBox virtual environment (host/venv deployment):

   ```bash
   cd /opt/netbox/netbox
   git clone https://github.com/emersonfelipesp/netbox-proxbox.git
   source /opt/netbox/venv/bin/activate
   pip install -e ./netbox-proxbox
   ```

2. **Enable the plugin** in `netbox/netbox/configuration.py`:

   ```python
   PLUGINS = ["netbox_proxbox"]
   ```

3. **Run migrations and collect static files:**

   ```bash
   python3 manage.py migrate netbox_proxbox
   python3 manage.py collectstatic --no-input
   sudo systemctl restart netbox
   ```

4. **Install the Proxbox API backend:**

   ```bash
   mkdir -p /opt/proxbox-api
   cd /opt/proxbox-api
   python3 -m venv venv
   source venv/bin/activate
   pip install proxbox-api
   uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800
   ```

   Or use Docker (the published image runs **nginx** on port **8000** inside the container, in front of **uvicorn**):

   ```bash
   docker run -d --name proxbox-api -p 8800:8000 emersonfelipesp/proxbox-api:latest
   ```

   **HTTPS with mkcert (optional):** the backend also publishes **`emersonfelipesp/proxbox-api:latest-mkcert`** (and `:<version>-mkcert`). **nginx** terminates **TLS** there (mkcert certs) on **`PORT`** (default **8000**); add more certificate names or IPs with **`MKCERT_EXTRA_NAMES`** (comma- or space-separated). Example:

   ```bash
   docker run -d --name proxbox-api-tls \
     -p 8800:8000 \
     -e MKCERT_EXTRA_NAMES='proxbox.backend.local' \
     emersonfelipesp/proxbox-api:latest-mkcert
   ```

   Point your NetBox **ProxBox API** endpoint at `https://<host>:8800` (or your mapped port). Trust the mkcert root on clients if needed; see the [proxbox-api README](https://github.com/emersonfelipesp/proxbox-api/blob/main/README.md) for build flags, `CAROOT`, and details.

5. **Configure endpoints in NetBox:**

   - Go to **Plugins > Proxbox**
   - Create a **Proxmox API** endpoint (your Proxmox host URL and token).
     The Proxmox user/token must hold a role with `Datastore.Audit`,
     `Sys.Audit`, `VM.Audit`, `VM.Monitor`, **and `VM.GuestAgent.Audit`**.
     `VM.GuestAgent.Audit` is required on Proxmox VE >= 9 for the backend to
     pull VM IPs through the QEMU guest agent — without it, VMs sync but
     their IP addresses are missing from NetBox. See the proxbox-api docs
     [Required Proxmox role privileges](https://github.com/emersonfelipesp/proxbox-api/blob/main/docs/getting-started/configuration.md#required-proxmox-role-privileges)
     for the `pveum role add` command.
   - Create a **NetBox API** endpoint (your NetBox URL and token)
   - Create a **ProxBox API** endpoint (the backend from step 4)

6. **Run your first sync:**

    Click **Full Update** on the Proxbox home page. Progress appears in real-time.

## NetBox Docker Install Option

If your NetBox runs with `netbox-community/netbox-docker`, install the plugin through the Docker plugin files in your NetBox Docker project:

1. Add plugin requirements to `plugin_requirements.txt` (PyPI or Git):

   ```txt
   netbox-proxbox
   # or
   # netbox-proxbox @ git+https://github.com/emersonfelipesp/netbox-proxbox.git
   ```

2. Enable the plugin in `configuration/plugins.py`:

   ```python
   PLUGINS = ["netbox_proxbox"]
   ```

3. Rebuild and restart NetBox:

   ```bash
   docker compose build
   docker compose up -d
   ```

4. Run migrations in the NetBox container:

   ```bash
   docker compose exec netbox /opt/netbox/netbox/manage.py migrate
   ```

For complete Docker installation instructions, validation checks, and Git/source install examples, see [docs/installation/3-installing-plugin-docker.md](./docs/installation/3-installing-plugin-docker.md).

## Scheduled Sync

Proxbox sync jobs run on NetBox's **`default`** RQ queue. A standard NetBox installation already ships a `netbox-rq` systemd service that runs:

```
manage.py rqworker high default low
```

Check whether it is running before doing anything else:

```bash
sudo systemctl status netbox-rq
```

If it is **active (running)**, you have nothing extra to configure — Proxbox jobs will be picked up automatically.

If the service is **inactive or missing**, enable it:

```bash
sudo systemctl enable --now netbox-rq
```

The unit file is provided by NetBox at `contrib/netbox-rq.service` in the NetBox repository. If you need to create it manually, copy it from there and run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netbox-rq
```

> **Upgrading from an older Proxbox release?** Jobs used to be enqueued on the `netbox_proxbox.sync` queue. The stock `netbox-rq` service does not listen to that queue, so old-style jobs will not run. New jobs always use `default` and are picked up without any changes.

Disabled `ProxmoxEndpoint` rows are hard-excluded from operational reads and
sync jobs. The scheduler, CLI sync command, dashboard cards, keepalive checks,
HA/storage/firewall/SDN/datacenter live reads, backend endpoint preflight, and
stale scheduled job parameters all filter to `enabled=True` before contacting
proxbox-api or Proxmox. To pause a production endpoint, set **Enabled** to
false; the row remains visible in the API and UI but no connection attempt is
made for that endpoint.

### Schedule a sync

1. In NetBox, go to **Proxbox > Schedule Sync**.
2. Choose one or more sync types (**All**, Devices, VMs, Storage, etc.).
3. Optionally set a **Schedule at** time and a **Recurs every** interval in minutes (e.g. `1440` for daily).
4. Click **Schedule**.

Track job status under **Proxbox > Sync Jobs** or **Operations > Background Jobs**.

### Job timeout

Proxbox sync jobs default to a **7200-second (2-hour) RQ wall-clock limit** (`PROXBOX_SYNC_JOB_TIMEOUT`). NetBox's default `RQ_DEFAULT_TIMEOUT` is only 300 s, which would kill long syncs. No configuration is needed unless your syncs routinely take longer than two hours; if they do, override the constant in `netbox_proxbox/jobs.py`.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Job stays **`pending`** | No RQ worker running, or worker not listening to `default` queue | Start/restart `manage.py rqworker` |
| Job stays **`running`** for a long time | Proxbox API is still syncing or stream is slow | Check the job **Log** tab; wait or inspect the backend |
| Job **`errored: JobTimeoutException`** | RQ wall-clock limit exceeded | Increase `PROXBOX_SYNC_JOB_TIMEOUT` in `netbox_proxbox/jobs.py` |
| Disabled endpoint still appears in `/api/plugins/proxbox/endpoints/proxmox/` | Expected API behavior; disabled rows remain inventory records | Leave it disabled to prevent all connection attempts. Re-enable only when the endpoint should participate in cards, checks, and sync jobs again. |
| VM IP addresses stay empty after upgrade | The separate `proxbox-api` backend is too old, is on the v0.0.13/v0.0.14 agent-flag warning window, existing VMs still lack `proxmox_vm_id`, or the Proxmox role lacks guest-agent privileges | Check the FastAPI card warning on the Proxbox home page. Run `proxbox-api >= 0.0.13` at minimum; if the warning references PR #156, install a backend build containing that fix or the next fixed backend release. Then run **Full Update** so existing VMs get `proxmox_vm_id` before the IP-address stage runs. For PVE 9, also confirm `VM.GuestAgent.Audit`. |
| **HTTP 401 Authentication failed!** against Proxmox VE 9.x | A stale stored token is overriding fresh password credentials, or the role is missing PVE 9 permissions | On the Proxmox endpoint edit page, tick **"Clear stored API token on save"** (and/or **"Clear stored password on save"**) to wipe the unused secret. The form rejects rows that end up with neither a password nor a complete `(token name, token value)` pair. Confirm the role on Proxmox grants `Datastore.Audit`, `Sys.Audit`, `VM.Audit`, and on PVE 9 also `VM.GuestAgent.Audit`. The plugin now surfaces the upstream PVE 9 error message in the UI instead of `"Unknown error."`, which makes "no such realm" / "expired token" / "missing privilege" failures self-diagnosing. |

#### Switching credentials cleanly (PVE 9 friendly)

The Proxmox endpoint edit form preserves the stored password and token value
when you submit blank masked fields — that is intentional for partial edits.
When you genuinely want to **switch** auth modes (for example, password → token
or vice versa, or rotate a leaked secret), tick the matching **"Clear
stored …"** checkbox so the unused credential is wiped on save. Clearing the
token always clears **both** `token name` and `token value` together so the row
never persists in a half-token state.

## Documentation

Full documentation is available at [emersonfelipesp.github.io/netbox-proxbox](https://emersonfelipesp.github.io/netbox-proxbox/).

Key pages:

- [Installation Guide](https://emersonfelipesp.github.io/netbox-proxbox/installation/2-installing-plugin-git/)
- [Backend Setup](https://emersonfelipesp.github.io/netbox-proxbox/installation/backend-setup/)
- [Endpoint Auto-Configuration](https://emersonfelipesp.github.io/netbox-proxbox/developer/endpoint-autoconfiguration/)
- [Scheduled Sync](https://emersonfelipesp.github.io/netbox-proxbox/features/scheduled-sync/)
- [REST API](https://emersonfelipesp.github.io/netbox-proxbox/api/)
- [Semantic MCP bridge](https://emersonfelipesp.github.io/netbox-proxbox/api/semantic-mcp-bridge/)
- [Certification Evidence](https://emersonfelipesp.github.io/netbox-proxbox/certification/)
- [Application Packet](https://emersonfelipesp.github.io/netbox-proxbox/application-packet/)

## Community

- GitHub Discussions: https://github.com/orgs/emersonfelipesp/discussions

## LLM Agent Safety

> **Before any destruction-adjacent operation, read `AGENTS.md` §"LLM Agent Safety Guardrails".**

Proxbox protects VM destruction behind a five-lock chain. LLM agents **MUST NOT**:
- Autonomously set `apply_destroy_confirmed=True`
- Submit the confirmation phrase `"allow-edit-and-add-actions"` on a user's behalf
- Approve a `DeletionRequest` as the same user who created it (`self_approve_allowed=False`)

The `DeletionRequest` REST endpoint (`/api/plugins/proxbox/deletion-requests/`) is read-only — enforced by `netbox_proxbox/api/views.py::DeletionRequestViewSet.http_method_names = ["get", "head", "options"]`. Pinned by `tests/test_static_guardrails.py`.

The plugin contains a read-only semantic producer manifest for a future
compatible netbox-sdk bridge. No
released SDK identity is activated yet: the checked activation artifact remains
blocked, so the API root omits `mcp` and `/api/plugins/proxbox/mcp/` returns 503
until one exact immutable SDK passes the paired CI vectors. The future
bridge exposes sync-job listing and guarded scheduling through the existing DRF
endpoint; the plugin does not run a separate MCP server or store a second
credential.
Scheduling is advertised as destructive because reconciliation can remove
stale NetBox inventory records, not because it deletes Proxmox infrastructure.
Once activated, agents use netbox-sdk's generic `plugin_list_tools` and
`plugin_call_tool` envelope; the descriptor names are not standalone MCP tools.
Bridge v1 accepts
13 explicit concrete `sync_stages`, an optional fail-closed Proxmox endpoint
scope, strict RFC 3339 scheduling, and an exactly-one-unit bounded `recurrence`.
It does not expose the legacy REST `netbox_endpoint_ids` scope. The MCP
mutation opt-in is server-wide, not per tool, and ambiguous write outcomes must
never be auto-retried. Integer JSON endpoint-ID literals retain the full signed
64-bit range, while integral float/Decimal forms normalize only through
`9007199254740991` to prevent rounded identity. The complete discovery flow,
executable examples, error handling, compatibility policy, and agent checklist are in the
[Semantic MCP Bridge guide](https://emersonfelipesp.github.io/netbox-proxbox/api/semantic-mcp-bridge/).

## Contributing

See [DEVELOP.md](./DEVELOP.md) for development setup and contribution guidelines.

Gitea pull-request CI runs the quality/mocked suite before strict docs/package
validation on the shared capacity-bounded Python runner. One repository-wide
concurrency group covers all refs without auto-cancelling protected or immutable
evidence. Both jobs require at least 384 MiB free and print the measured and
required KiB before environment creation. That floor is based on a 195,498 KiB
locked quality environment plus the 42,021 KiB source tree, leaving 155,697 KiB
of measured residual capacity before transient operations. The hosted preflight
reports the exact available capacity; serialization and cacheless operation
bound the remaining pressure. Both jobs set `UV_NO_CACHE=1` and always
remove environments, tool caches, output trees, and generated bytecode. Quality
installs the locked `test`, `dev`, and `cli` optional extras with `--no-dev`;
the serialized docs job owns the separate MkDocs `dev` and exact packaging
`publish` dependency groups and builds without an isolated floating tool
environment. Keep those scopes separate so concurrent caches, duplicate docs
dependencies, or floating package tools cannot exhaust or drift on the runner.
Each job also scrubs those paths before use; stale generated-state symlinks are
removed without traversal and fail that run closed, protecting reused workspaces
from redirected writes or stale package evidence.

## Support the Project

If Proxbox has been useful for you, consider supporting the project on GitHub Sponsors:

[Sponsor Me!](https://github.com/sponsors/emersonfelipesp)
