# Hardware Discovery via SSH

The Proxmox REST API does not expose chassis hardware (serial number,
manufacturer, product name) or per-NIC link details (negotiated speed,
duplex, link state). Operators that need those fields populated in NetBox
historically had to hand-edit each `dcim.Device` and `dcim.Interface`.

In the `netbox-proxbox 0.0.15` line, the plugin can store per-node SSH
credentials, expose a token-gated credential endpoint, and register the
NetBox custom fields used by an opt-in **SSH-driven discovery pass**. The
released `proxbox-api 0.0.11` backend remains compatible and simply does
not run this discovery pass; discovery activates with a backend build that
includes [proxbox-api PR #80](https://github.com/emersonfelipesp/proxbox-api/pull/80).
That backend runs `dmidecode` and `ethtool` on each Proxmox node and
reflects the parsed values onto the matching NetBox records.

This page is the operator-facing setup guide.

## When to enable it

- You manage more than a handful of Proxmox hosts and want NetBox's
  `Device.serial`, `Device.manufacturer`, and chassis-related custom
  fields populated automatically.
- You want per-NIC negotiated speed / duplex / link state visible in the
  NetBox interface detail view.
- You can dedicate a least-privilege SSH user on each node (recommended:
  `proxbox-discovery` — see [Node-side setup](#3-node-side-setup)).

## When NOT to enable it

- You cannot pin host keys (the discovery driver refuses TOFU; every
  node's SHA-256 fingerprint must be stored before discovery runs).
- You cannot dedicate an SSH user — running discovery as `root` is
  technically possible but not supported by the documentation.
- Your management network does not reach the node SSH port.

## High-level architecture

```
proxbox-api                NetBox plugin                Proxmox node
─────────────              ─────────────                ─────────────
1. Fetch credentials ────►  /api/plugins/proxbox/
                            ssh-credentials/by-node/
                            <node_id>/credentials/
                            (NetBox API token)

2. Open SSH session ─────────────────────────────────►  sshd (port 22)
   (pinned fingerprint,                                  ↓
   sudo -n)                                              ↓
                                                         dmidecode -t 1
                                                         dmidecode -t 3
                                                         ip -o link show
                                                         ethtool <iface>

3. Parse outputs ◄───────────────────────────────────── stdout

4. Reflect to NetBox ────►  dcim.Device / dcim.Interface
                            custom_fields (drift-detect)
```

All SSH primitives — host-key pinning, sudo handling, output capping,
command allow-listing — live in `proxmox-sdk.ssh.RemoteSSHClient`.
`proxbox-api` is a thin consumer; it does not import `paramiko`.

## One-time setup

### 1. Configure the encryption key

The credentials store reuses `ProxboxPluginSettings.encryption_key`
(introduced in `0.0.11`). If it is empty, the plugin refuses to save
SSH credentials and `proxbox-api` refuses to fetch them.

1. Open **Plugins → Proxbox → Settings** in the NetBox UI.
2. Tick **Enable encryption** and paste a 32-byte Fernet key (or a
   raw 32-byte secret — the plugin will base64-encode it).
3. Save.

### 2. Enable the feature flag

In **Plugins → Proxbox → Settings**, tick
**Enable SSH-based hardware discovery** and save. The flag is
**off by default**; until you flip it, no SSH sockets are opened
during a sync.

### 3. Node-side setup

For each Proxmox node you want to discover, create a dedicated
discovery user. Example for Debian / Proxmox VE 8:

```bash
# 1. Create the user (no shell, no home password)
adduser --disabled-password --gecos "" proxbox-discovery

# 2. Drop your proxbox-discovery ed25519 public key into authorized_keys.
#    Use the locked-down command= prefix so only the discovery script runs:
mkdir -p /home/proxbox-discovery/.ssh
cat > /home/proxbox-discovery/.ssh/authorized_keys <<'EOF'
command="/usr/local/bin/proxbox-discover",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... proxbox-discovery
EOF
chown -R proxbox-discovery:proxbox-discovery /home/proxbox-discovery/.ssh
chmod 700 /home/proxbox-discovery/.ssh
chmod 600 /home/proxbox-discovery/.ssh/authorized_keys

# 3. Install the discovery dispatch script
cat > /usr/local/bin/proxbox-discover <<'EOF'
#!/bin/sh
case "$SSH_ORIGINAL_COMMAND" in
  "dmidecode -t 1"|"dmidecode -t 3")
    sudo -n /usr/sbin/$SSH_ORIGINAL_COMMAND ;;
  "ip -o link show")
    /usr/sbin/$SSH_ORIGINAL_COMMAND ;;
  ethtool\ *)
    /usr/sbin/$SSH_ORIGINAL_COMMAND ;;
  *)
    exit 1 ;;
esac
EOF
chmod 755 /usr/local/bin/proxbox-discover

# 4. Grant only the two dmidecode calls under sudo
cat > /etc/sudoers.d/proxbox-discovery <<'EOF'
proxbox-discovery ALL=(root) NOPASSWD: /usr/sbin/dmidecode -t 1, /usr/sbin/dmidecode -t 3
EOF
chmod 440 /etc/sudoers.d/proxbox-discovery
visudo -cf /etc/sudoers.d/proxbox-discovery
```

Only `dmidecode` needs `sudo`; `ip` and `ethtool` work without it on
Proxmox.

### 4. Pin the host-key fingerprint

The discovery driver refuses to connect unless the node's host key
matches the stored SHA-256 fingerprint exactly — no TOFU.

```bash
# Get the canonical fingerprint of the node's ed25519 host key
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
# Output: 256 SHA256:abc123… root@node1 (ED25519)
```

Copy the `SHA256:<base64>` segment.

### 5. Add the credential in NetBox

1. Browse to **Plugins → Proxbox → SSH Credentials → Add**.
2. Pick the **Proxmox node** (one credential per node).
3. Fill in:
    - **Username**: `proxbox-discovery`
    - **Port**: `22` (or your custom port)
    - **Auth method**: **SSH private key (recommended)**
    - **Private key**: paste the ed25519 PEM whose public counterpart
      you placed in the node's `authorized_keys`.
    - **Pinned host-key fingerprint**: paste `SHA256:abc123…`
    - **Sudo required**: ✅ (the dispatch script uses `sudo` for
      `dmidecode`)
4. Save. The form encrypts the private key with the configured
   Fernet key before persisting.

## Operations

### What the discovery pass writes

| NetBox object | Custom field | Source |
| --- | --- | --- |
| `dcim.Device` | `hardware_chassis_serial` | `dmidecode -t 3 → Serial Number` |
| `dcim.Device` | `hardware_chassis_manufacturer` | `dmidecode -t 1 → Manufacturer` |
| `dcim.Device` | `hardware_chassis_product` | `dmidecode -t 1 → Product Name` |
| `dcim.Interface` | `nic_speed_gbps` | `ethtool <iface> → Speed: 10000Mb/s` → `10` |
| `dcim.Interface` | `nic_duplex` | `ethtool <iface> → Duplex: Full` |
| `dcim.Interface` | `nic_link` | `ethtool <iface> → Link detected: yes` |

All six fields are registered automatically by migration
`0049_register_hardware_discovery_cfs`. They use `ui_editable=hidden`
because the discovery pass is the source of truth — manual edits drift
the next sync.

### Idempotency

A second consecutive successful sync emits **zero** `ObjectChange`
rows for the six hardware fields. Drift detection lives in the
proxbox-api reflection helper introduced by issue #357.

### Disabling the feature

Untick **Enable SSH-based hardware discovery** in Settings. The next
sync opens **zero** SSH sockets — the discovery orchestrator returns
early when the flag is False. Stored credentials remain encrypted at
rest; nothing is deleted.

## Troubleshooting

### `host_key_mismatch` warning frame

The node's host key changed since you pinned the fingerprint. Either:

1. The node was reinstalled — re-pin the fingerprint after verifying
   the new key out-of-band.
2. A MITM is intercepting the SSH session — stop, audit, and only
   re-pin once you have confirmed the new key matches what is on the
   node console.

### `hardware_discovery_timeout` warning frame

The SSH connection or command run exceeded the timeout (connect 10 s,
exec 30 s). The orchestrator runs nodes sequentially, so a stalled
node only delays itself — the run continues.

### `sudo: a password is required`

The discovery user is missing the sudoers entry, or the entry is
wider than the two dmidecode commands listed above. Re-check
`/etc/sudoers.d/proxbox-discovery` and confirm `sudo -n dmidecode -t 1`
succeeds when run as the discovery user on the node.

### 503 from the secrets endpoint

`/api/plugins/proxbox/ssh-credentials/by-node/<id>/credentials/`
returns `503 Service Unavailable` when
`ProxboxPluginSettings.encryption_key` is empty or the row is
encrypted with a now-rotated key. Re-pin the key (and re-save the
affected credentials) before the next sync.

### 403 from the secrets endpoint

The NetBox API token used by proxbox-api was rejected, the request was not
HTTPS while `DEBUG=False`, or the token's user lacks
`netbox_proxbox.view_nodesshcredential`. Confirm proxbox-api is configured
against this NetBox, sends `Authorization: Token <key>` (or NetBox v2's
`Bearer <key.secret>` form), and uses a service account with the
credential-view permission. This endpoint does not use
`FastAPIEndpoint.token`.

## Security boundary recap

- Browser users with the standard `view` permission on the credential
  see only metadata (`has_password`, `has_private_key`, fingerprint).
- Plaintext is only returned to the NetBox API-token-gated
  `…/credentials/` endpoint, which rejects browser sessions and refuses
  non-HTTPS when `DEBUG=False`.
- All SSH primitives are pinned to modern AEAD ciphers, ETM MACs, and
  curve25519 kex inside `proxmox-sdk.ssh.RemoteSSHClient`.
- The discovery user runs a `command=`-locked script, has no shell, no
  agent forwarding, no PTY, and `sudo` access only to two `dmidecode`
  invocations.
- `hardware_discovery_enabled=False` (default) results in zero SSH
  sockets opened — pinned by `tests/test_hardware_discovery_flag_off.py`
  in proxbox-api.
