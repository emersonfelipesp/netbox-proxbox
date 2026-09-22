# Enable OpenBao credential storage

Proxbox can store supported credential material through `netbox-openbao` while
keeping only provider UUID references and assignment metadata in NetBox. This
setup surface is structural and secret-free. It does not accept, display, move,
or verify credential material.

## Dependencies

Install compatible `netbox_openbao` and `netbox_rpc` plugins, add both names to
NetBox `PLUGINS`, apply their migrations, and restart every NetBox web and
worker process. `netbox-openbao` owns engines, policies, credentials,
assignments, and provider access. `netbox-rpc` owns audited host-operation
catalog and execution history. Proxbox owns its credential references and the
mapping between a Proxbox object and an OpenBao assignment.

The command reports both plugins because protected-write rollout depends on the
composed stack. It does not seed or validate the broader RPC catalog, backend
compatibility, target bindings, migration ledger, or protected-write operation
matrix. Those remain separate integration work; a green setup report does not
certify that broader rollout.

## Configure and verify

Select an existing active NetBox account in **Proxbox Settings → OpenBao service
username**. The command never creates a user or grants permissions. Set
**OpenBao policy slug** to the exact policy intended for Proxbox.

Run the strictly read-only check before changing the storage backend:

```bash
python manage.py proxbox_openbao_setup --check
```

It prints every met and missing prerequisite and exits nonzero while anything
is missing. The settings readiness card consumes the same typed result.

Interactive credential storage validation uses the provider subset of that
result: `netbox-openbao`, a default engine, and the exact configured policy.
It does not require `netbox-rpc` or the automation service username merely to
store material through an authenticated request actor. The command and panel
remain composed-stack diagnostics and therefore report both. Background reads
still require the configured active service user, and the broader protected
write rollout still requires RPC readiness.

If no default `SecretEngine` exists, provide its non-secret structural URL
explicitly. Authentication values remain in the provider's supported runtime
environment and are never command arguments or database fields.

```bash
python manage.py proxbox_openbao_setup \
  --api-url https://openbao.example.net:8200 \
  --engine-name "Proxbox OpenBao" \
  --engine-slug proxbox \
  --kv-mount secret
```

The command creates only a missing default engine and the exact configured
`CredentialPolicy`. Re-running it is a no-op. An existing default engine is
preserved. If any final composed prerequisite remains missing, the command exits
nonzero and rolls back the engine, policy, and assignment writes from that run.

## Object and purpose mapping

| Proxbox owner | Credential type | Assignment target | Purpose |
| --- | --- | --- | --- |
| Proxmox endpoint password | `password` | Proxmox endpoint | `login` |
| Proxmox endpoint API token | `api-token` | Proxmox endpoint | `api` |
| Proxmox endpoint SSH password/keypair | `ssh-password` / `ssh-keypair` | Proxmox endpoint | `console` |
| Node SSH password/keypair | `ssh-password` / `ssh-keypair` | Linked NetBox device | `login` |
| FastAPI, PBS, and PDM tokens | `api-token` | Owning endpoint | `api` |
| Firecracker agent token | `api-token` | Firecracker host | `agent` |
| VM cloud-init password/keypair | `password` / `ssh-keypair` | Parent virtual machine | `login` |

Preview missing assignments without writes:

```bash
python manage.py proxbox_openbao_setup --check --backfill-assignments
```

Apply only missing relations with:

```bash
python manage.py proxbox_openbao_setup --backfill-assignments
```

Backfill does not create credentials, read or move material, modify a UUID
reference, change an existing relation, or replace another owner's primary
assignment. An existing exact relation is accepted only when it is enabled and
its primary state matches the mapping above. The referenced credential type
must also match the owner's declared slot. Backfill stops on disabled or
primary-state-drifted exact rows, incompatible credential types, unresolved
references, or foreign primary conflicts; it never repairs those operator-owned
states implicitly. A second run creates no rows.

## Rollback

Before returning an owner or the plugin default to legacy encrypted storage,
follow the owning model's reference and assignment cleanup workflow. Do not
delete provider material merely because one owner stops using it: credentials
may be shared. Preserve OpenBao audit records and assignments until every owner
has been reconciled. Then choose `legacy_encrypted` in Proxbox settings and
configure the plugin Fernet key through the documented recovery-safe process.

Rollback does not authorize copying protected material through this command.
Legacy-material migration and external credential identifier reconciliation
belong to the broader audited-write integration and require their own reviewed,
resumable workflow.
