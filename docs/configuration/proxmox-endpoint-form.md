# Proxmox Endpoint Form

The Proxmox endpoint add and edit form separates read-only settings from the
settings that only matter when writes or SSH are enabled.

| Section | Always shown | What it controls |
|---|---|---|
| Connection and credentials (read-only API access) | Yes | Address, port, API username, password or API token, TLS verification, site, tenant, tags. This is everything an inventory-only endpoint needs. |
| Write access (opt-in) | Yes | **Allow Proxmox-side writes**. The **Allow netbox-packer template builds** option appears only after writes are enabled, or while it is already checked. |
| Access methods | Yes | **API only** (default) or **API + SSH**. |
| SSH credential access (API + SSH only) | Only for API + SSH | An application-service credential (the default for new configuration), a dedicated endpoint credential, or reused API credentials, plus the pinned host-key fingerprint. |
| Service monitoring (needs write access and API + SSH) | Only with writes enabled and API + SSH | Systemd service collection through netbox-rpc. |

A section stays visible when it holds a validation error, and an option that is
already checked is never hidden, so you can always see and clear it. Hidden
fields are still submitted unchanged, and the browser's own field checks are switched off while a section is hidden so a hidden field can never block saving. If JavaScript is unavailable, every
section is shown.

When reuse mode and service monitoring are enabled together, a password entered
on the same create or edit submission satisfies validation without being copied
onto the model as a validation side effect. Runtime readiness still becomes true
only after the credential has been persisted successfully.

## API-only endpoints do not need SSH

An endpoint with **API only** access never opens an SSH session. The form
ignores every SSH field for it, so a leftover or placeholder SSH value cannot
block saving, and the submitted SSH values are not stored. Switching the
endpoint to **API + SSH** applies the full SSH validation again: a username, a
pinned host-key fingerprint, and a matching password or private key.

## Application-service SSH credentials

New SSH configuration defaults to **SSH credential on an application service**.
This represents the complete relationship in NetBox:

`ServiceSSHCredential → ProxmoxEndpointService → IPAddress → ProxmoxEndpoint`

Select the endpoint IP address and optionally select one of that endpoint's
application services. If the selector is blank, Proxbox reuses the visible TCP
service bound to that IP and SSH port. If none exists, a user with
`netbox_proxbox.add_proxmoxendpointservice` may create the default `ssh`
service during the same save. The service receives the endpoint IP, the TCP
port is synchronized back to `ssh_port`, and the new credential is stored only
after the chain validates.

The SSH tab exposes the endpoint IP selector with NetBox quick-add enabled, so
an operator can create the IP first and complete the chain without returning to
the main endpoint form. A selected service must belong to the same endpoint;
Proxbox never attaches a core `ipam.Service` because NetBox does not allow an
endpoint or cluster as that model's parent.

With this source, the browser terminal and the host-key scan connect to the
endpoint IP address that the service is validated to bind, even when the
endpoint also has a domain. Other sources keep their domain-first host.
Storing or replacing the credential requires `add_servicesshcredential` (new)
or object-level `change` on the existing credential, and binding the IP to a
selected service requires `change` on that service. Releasing service-sourced
material through the secrets API additionally requires `view` on the
credential.

An API-only main-form edit cannot clear a selected service credential. Explicit
service password or private-key clears are rejected before saving. Use the SSH
credential settings for an authorized clear before changing the access method.
Ordinary API-only edits preserve the service credential and ignored SSH drafts.

Local storage encrypts passwords and private keys with the configured Fernet
key. When netbox-openbao is enabled, the form can instead create a provider
credential or assign an existing `ssh-password` or `ssh-keypair` credential to
the application service for the primary `console` purpose. The selected
backend never falls back to the other backend.
