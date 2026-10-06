# Version 0.0.29.post1

## Summary

This maintenance release adds an explicit connection-target approval recovery
panel to NetBox and Proxmox endpoint detail pages. It also restores optional
netbox-openbao operation and corrects credential-storage settings rendering.

## Release identity

The package and plugin source both identify this maintenance release as
`0.0.29.post1`.

## Recover endpoint connections after upgrading

Version `0.0.29` introduced an approval requirement before endpoint credentials
can be sent. Existing endpoints retain their transport configuration but do not
receive an automatic approval. Consequently, a healthy FastAPI connection can
coexist with a Proxmox keepalive error when the Proxmox target is unapproved.

1. Open the affected Proxmox endpoint detail page in NetBox.
2. Select **Review again** in the connection approval panel.
3. Verify the displayed target address, port, TLS setting, and credential identity.
4. Select **Approve reviewed target** only if those values identify the intended
   destination, then retry the connection check or synchronization.
5. Repeat this review for a NetBox endpoint when its connection target also
   requires approval.

Approval requires the existing sensitive-data authorization and applicable
endpoint view and change permissions. Disabled endpoints cannot be approved.
Editing a connection target invalidates its previous approval. A failed or timed
out request requires a fresh review; it is never displayed as a successful
approval. No credential secret is returned by the review panel, and no target
is approved automatically.

## Credential storage without netbox-openbao

Automatic credential storage uses local Fernet encryption when the optional
netbox-openbao companion is unavailable. The Settings page now displays the
credential storage backend, OpenBao policy slug, and service username. Selecting
OpenBao explicitly while the companion is disabled produces a field error.

An endpoint without OpenBao credential references can be deleted without the
companion. Existing OpenBao references remain protected: deletion and changes
away from OpenBao are refused until those credentials are cleaned up through
the supported path.

## Upgrade and migration

Run the standard NetBox plugin migration procedure after installing this version.
This release introduces exactly one migration,
`0105_reset_implicit_openbao_storage_default`, after
`0104_security_hardening`. It changes an implicit plugin-wide OpenBao default
to Automatic only when no credential owner has an OpenBao reference. It
preserves explicit endpoint overrides and installations containing such
references. Reversing this data migration does not restore an implicit OpenBao
default.

SSH password reuse also forwards the requesting user's identity to OpenBao
material resolution. Enabled endpoints therefore reach the intended credential
availability checks instead of failing on an unsupported resolver argument.
Disabled endpoints still refuse credential disclosure before any provider read.

The connection approval panel adds no database fields and does not backfill
approval or sensitive-data grants. Existing plain-HTTP configurations retain
their stored transport choices; an approval requirement is independent of the
FastAPI transport choice.

## Compatibility baseline

The support contract remains NetBox `4.5.8` through `4.7.0` GA. This maintenance
source retains the preceding backend pairing.

Current backend-runtime pairing: netbox-proxbox 0.0.29.post1 <-> proxbox-api 0.0.23.post3 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.29.post1 | v0.0.23.post3 | v0.0.13 | v0.0.15 |
