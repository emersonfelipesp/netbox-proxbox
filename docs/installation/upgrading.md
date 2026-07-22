# Upgrading Proxbox

## Plugin Upgrade Checklist

Use this flow when upgrading an existing Proxbox installation in NetBox:

```bash
cd /opt/netbox/netbox
source /opt/netbox/venv/bin/activate
pip install -U netbox-proxbox
python3 manage.py migrate netbox_proxbox
python3 manage.py collectstatic --no-input
sudo systemctl restart netbox
```

If you install from a Git checkout instead of PyPI, replace the install step with:

```bash
pip install -e /opt/netbox/netbox/netbox-proxbox
```

## Important Notes

### FastAPI key target adoption (migration 0075)

Migration `0075_fastapi_backend_key_target_fingerprint` adds a durable binding
between each encrypted FastAPI key and every authority that may receive it: the
primary HTTP URL, fallback IP URL, TLS verification policy, and WebSocket
host/port flags. Existing rows intentionally receive a blank fingerprint. New
plugin code therefore blocks authenticated HTTP and server-side WebSocket
traffic until an operator reviews and adopts the current target.

Before upgrading, retain the currently valid proxbox-api key in your approved
secret store and record the intended domain, fallback IP, ports, HTTPS/TLS, and
WebSocket settings. For the strongest cutover, stop NetBox web and RQ processes,
install the package, and run the migration before restarting them.

After migration:

```bash
# Blank legacy fingerprints are reported without sending the stored key.
python manage.py proxbox_fix_tokens

# After reviewing the configured target, explicitly adopt the retained key.
python manage.py proxbox_fix_tokens --fix
```

`--fix` is the operator's consent to contact the reviewed target. It records the
fingerprint when the stored key already authenticates and performs the one-time
bootstrap POST only when proxbox-api proves that it has no keys. A nonblank
fingerprint that no longer matches its target is refused without network access;
edit the FastAPI endpoint and explicitly resubmit the retained key instead.

Verify that the diagnostic reports the key as registered, that the FastAPI
status card can complete an authenticated version check, and that one scoped
sync succeeds. If adoption fails, the local ciphertext/fingerprint remains
unchanged. Correct the target and retry with the same retained key. If the remote
bootstrap succeeded but the local transaction rolled back, retrying that same
key is recoverable because the backend can now authenticate it. Do not create a
replacement hidden key or delete the accepted remote key as a rollback tactic.

- Proxbox `0.0.23.post1` is the current release candidate for NetBox `4.5.8` through `4.5.10` and `4.6.x` (validated against `v4.5.8` through `v4.5.10` and `v4.6.0` through `v4.6.5`; declared compatibility range `4.5.8` through `4.6.99`). It pairs with a `proxbox-api` guest-VM-interface writer build / next release. Plugin version `0.0.23.post1` on the `0.0.23` release line. The previous stable `0.0.22` release pairs with backend `0.0.19.post5`.
- Upgrading to `0.0.23.post1` switches existing installs from `vm_interface_sync_strategy=legacy_rename` to `vm_interface_sync_strategy=guest_os_model`. Proxmox `netX` interfaces stay named `netX` as core `VMInterface` rows, and guest OS names such as `ens18` are stored in `GuestVMInterface` rows. Operators who want the old core-interface renaming behavior can re-select `vm_interface_sync_strategy=legacy_rename` in plugin settings after the upgrade.
- Disabled endpoint-like rows with `enabled=False` are inventory-only in `0.0.20.post3`: they remain visible in UI/API output, but status, keepalive, backend registration, OpenAPI, startup/signal, sync, PBS, PDM, and companion endpoint paths return before any backend or remote-service connection attempt.
- This release includes the PVE 9.2 schema migration plus `0045_repair_pbs_pdm_endpoint_enabled`, a database-only repair for affected `0.0.18` installs where `PBSEndpoint` and `PDMEndpoint` were missing the shared endpoint `enabled` column. Run `python manage.py migrate netbox_proxbox` after upgrade.
- If you operate the proxbox-api `*-nginx` image and previously could not connect, edit the FastAPI endpoint after upgrade and tick **Use HTTPS** (and untick **Verify SSL** if you use the bundled mkcert cert).
- Recent releases moved sync execution to NetBox Jobs and the default RQ queue, so keep a standard NetBox RQ worker running after upgrade.
- Review the release notes before jumping from older `0.0.7` or early `0.0.9` installs; the `0.0.15` line continues the NetBox `4.5.8` / `4.5.9` / `4.6` compatibility path established in `0.0.13.post4` and `0.0.14`. For `0.0.15` specifically, the new NetBox→Proxmox intent path is opt-in via `ProxboxPluginSettings.netbox_to_proxmox_enabled` plus a typed-confirmation phrase; nothing changes for existing installs unless an operator explicitly opts in.
- If you run `proxbox-api >= 0.0.10` behind a reverse proxy and want per-client rate-limiting and brute-force lockout to track real client IPs, set `PROXBOX_TRUSTED_PROXIES` (CIDR list) on the backend container. Without it, `X-Forwarded-For` is ignored and limits apply to the proxy's IP. This is a backend-side configuration; the plugin itself does not care.
- Upgrading from a pre-`0.0.13` install introduces 16 new per-endpoint `overwrite_*` columns on `ProxmoxEndpoint`. That migration shipped in `0.0.13`; `0.0.15` adds the new `overwrite_ip_address_dns_name` column on top.

## Backend Upgrade

Upgrade the separate `proxbox-api` service independently of the plugin:

```bash
source /opt/proxbox-api/venv/bin/activate
pip install -U proxbox-api
sudo systemctl restart proxbox
```

If you run the backend in Docker, pull the new image tag and recreate the container.

After upgrading from a backend older than `0.0.13`, run a **Full Update** from
the Proxbox home page. That pass repopulates the `proxmox_vm_id` custom field
on VMs created before the VM config fix; the VM IP-address stage depends on
that field when it matches Proxmox VMs back to NetBox objects. If the FastAPI
card shows the PR #156 advisory for `proxbox-api` `0.0.13` or `0.0.14`, install
a backend build containing that fix, or the next fixed backend release, before
re-testing VM IP sync.


> **Current release:** netbox-proxbox `0.0.23.post1` pairs with proxbox-api guest-VM-interface writer build / next release (NetBox `4.5.8`-`4.6.99`). Current pairing: netbox-proxbox 0.0.23.post1 <-> proxbox-api (guest-VM-interface writer build / next release) <-> proxmox-sdk 0.0.12 <-> netbox-sdk 0.0.10.
