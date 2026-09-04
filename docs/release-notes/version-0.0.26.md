# Version 0.0.26

netbox-proxbox `0.0.26` pairs with `proxbox-api 0.0.20`,
`proxmox-sdk 0.0.13`, and the backend's REST dependency
`netbox-sdk 0.0.10`. NetBox support remains stable from `4.5.8` through
`4.6.99`, with experimental evaluation limited to exact canonical
`4.7.0-beta2`. The numeric ceiling remains `4.7.0`, and canonical metadata must
retain designation `beta2`.

The latest directly certified stable NetBox release remains `4.6.6`.

Current backend-runtime pairing: netbox-proxbox 0.0.26 <-> proxbox-api 0.0.20 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.6.x; exact canonical 4.7.0-beta2 | v0.0.26 | v0.0.20 | v0.0.10 | v0.0.13 |

## Browser-console handoff

Synchronized QEMU virtual machines and LXC containers can now hand an
authorized user to the browser console service. QEMU uses its noVNC client and
LXC uses its xterm.js terminal. NetBox sends only the persisted guest identity
through an HTTPS URL; the backend creates the opaque one-time console ticket
and keeps every Proxmox credential and websocket target server-side.

The handoff is disabled by default. Set the plugin's `console_url` to the
trusted management HTTPS origin after the frontend and backend relay have been deployed.
Users must hold the matching guest view permission. A missing URL, an invalid
scheme or origin, an unsaved guest, or a permission failure removes the action
instead of constructing a partial or unsafe console URL.

## Authoritative inventory and synchronization state

Guest detail pages now show an authoritative Proxmox detail card and their
current synchronization state without relying on duplicated reflection custom
fields. Migrations `0085`, `0086`, and `0087` retire the obsolete reflection
definitions in guarded stages. Each destructive migration checks for stored
values before and after locking and again immediately before removal. Any
meaningful value preserves its field, binding, and data.

The release also exposes synchronized Proxmox tags, adds a read-only sync-jobs
API, and makes Packer template-build authorization explicit on each endpoint.
These surfaces remain read-only or separately gated; they do not broaden the
plugin's default write boundary.

## Credential-source alignment

Migration `0083` makes OpenBao the default plugin credential-storage choice.
Existing configured values remain explicit. When an endpoint selects a node
SSH credential but no local secret is available, the plugin can use the exact
matching credential service's DeviceService instead of inventing or exposing a
new secret path.

## Resumable, identity-verified publication

The Gitea package publisher is now manual and runs only from the canonical
repository's `main` branch. Its control checkout is immutable. Candidate tag
validation records both the raw tag object and peeled source commit; each later
job refetches and verifies those identities before using the candidate.

Builds use the canonical locked Python, uv, Hatchling, and Twine versions. The
candidate is copied into a bounded passive build tree through no-follow file
descriptors. Symlinks, hard links, special files, oversized files, out-of-root
paths, and file or byte-count overflow fail closed. Candidate-controlled build
hooks are not executed.

The workflow uploads the immutable Gitea wheel and source distribution first,
downloads and hashes their actual registry bytes, and publishes and verifies
the matching release manifest. Only then does it inventory every page of
applicable GitHub tag rulesets, require their combined update, deletion, and
non-fast-forward protections with no bypass, verify push permission, and
reserve the exact RC tag in the approved public repository. An interrupted run
accepts an existing GitHub tag only when both its raw object and peeled source
match the verified candidate; otherwise it performs the first push. Resume mode
still requires authoritative package state and the rebuilt manifest to prove
that the same immutable release is being continued.

## Upgrade

Upgrade the package, run the normal NetBox migrations, and collect static files:

```bash
python manage.py migrate netbox_proxbox
python manage.py collectstatic --no-input
```

Review the guarded custom-field migration output before removing any manually
retained field. Configure `console_url` only after the matching management frontend and
backend relay are live at the trusted HTTPS origin. Existing installs that do
not configure it retain their previous behavior.
