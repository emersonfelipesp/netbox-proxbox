# Security Policy and Threat Model

## Purpose and scope

This document defines the security policy and threat model for NetBox Proxbox. It helps operators, vulnerability reporters, and maintainers distinguish a genuine boundary violation from an authorized infrastructure operation.

NetBox Proxbox is a plugin that runs inside NetBox and synchronizes inventory and selected operator-approved actions between NetBox, proxbox-api, Proxmox, and optional companion plugins. It inherits NetBox's security foundation, but it also adds credentials, outbound connections, background jobs, synchronization logic, browser-console relays, and infrastructure mutation paths.

This model is based on the [NetBox threat model](https://github.com/netbox-community/netbox/blob/main/THREAT_MODEL.md), uses the same boundary-first approach, and applies a lightweight STRIDE analysis. NetBox's policy does not cover this third-party plugin, and NetBox maintainers are not responsible for Proxbox reports.

## Supported versions

Security fixes are made against the latest released version and the current development branch. Before reporting, reproduce the issue on one of those versions. Older releases may be asked to upgrade before a report is evaluated.

## Reporting a vulnerability

Do not open a public issue, pull request, discussion, or chat thread for a suspected vulnerability.

Send a confidential report to [Emerson Felipe](mailto:emersonfelipe.2003@gmail.com) with the subject `netbox-proxbox security report`. Include:

- the affected version and deployment topology;
- prerequisites and required permissions;
- reproducible steps or a minimal proof of concept;
- the expected and observed result;
- the security impact and the boundary crossed;
- any proposed mitigation or patch.

Do not include production credentials, API tokens, private keys, database contents, or sensitive infrastructure data. Use synthetic values and redact logs. The maintainer will acknowledge the report, validate its scope, coordinate a fix and release when necessary, and agree on disclosure timing with the reporter. Do not disclose the issue publicly before coordinated remediation.

Reports must describe a confirmed, reproducible exploit. An automated scanner result without a realistic exploit path is not sufficient.

## Supported deployment model

This threat model assumes all of the following:

- NetBox is installed and operated according to its official security and installation guidance on an internal or otherwise access-controlled network.
- Authentication is required. Anonymous access to NetBox, the plugin API, proxbox-api, Redis, PostgreSQL, worker controls, or Proxmox management interfaces is not supported.
- A trusted reverse proxy terminates TLS, applies request limits, and supplies authoritative client-address headers. Only explicitly trusted proxies may set those headers.
- NetBox, PostgreSQL, Redis, workers, proxbox-api, and management interfaces are reachable only by the components and operators that need them.
- Infrastructure operators, NetBox superusers, host administrators, database administrators, and anyone who can read process secrets or the plugin encryption key are fully trusted.
- Proxbox permissions are granted according to least privilege. Users who can create or change endpoint, credential, synchronization, console, RPC, Packer, or write-approval objects are trusted operators for those capabilities.
- proxbox-api is an authenticated private service. Its API key is sent only over a trusted TLS connection to the exact configured authority.
- Proxmox, NetBox, proxbox-api, and optional companion credentials use dedicated least-privilege identities. Operators protect and rotate them outside this plugin where required.
- TLS verification stays enabled in production. Options that disable verification are for isolated development or lab environments and remove the server-identity boundary.
- Backups, host hardening, secret injection, network segmentation, resource limits, and availability controls are deployment responsibilities.

A report that depends on public anonymous exposure, a malicious host administrator, direct database modification, stolen operator credentials, or deliberately disabled TLS verification is outside this supported model unless the report demonstrates a separate boundary bypass.

## Assets and trust boundaries

The protected assets include NetBox and Proxmox inventory, endpoint configuration, encrypted credentials, the plugin encryption key, proxbox-api keys, NetBox API tokens, Proxmox API tokens or passwords, SSH credential references, browser-console tickets, job and approval state, audit records, and the authority to mutate managed infrastructure.

The principal boundaries are:

1. **Browser or API client to NetBox.** NetBox authentication, CSRF protection, Django/DRF validation, and the permissions implemented by each view are authoritative. Most plugin model APIs use NetBox's object-permission framework. The SSH credential secret endpoint is intentionally stronger authority: a valid service token with the model-level `view_nodesshcredential` permission can retrieve the selected node's plaintext credential for proxbox-api and is not narrowed by an object constraint during credential lookup. Grant that permission only to the dedicated proxbox-api service identity.
2. **NetBox to plugin code and workers.** A queued task retains only the authority granted by the initiating permission and the persisted endpoint policy. Queue access is an operator boundary.
3. **Plugin to proxbox-api.** Requests require the configured API key and an exact validated target. Redirects, authority changes, or stale credential bindings must fail closed.
4. **proxbox-api to NetBox and Proxmox.** proxbox-api holds powerful service credentials. Its authentication, endpoint policy, write gates, approvals, and upstream authorization form an independent boundary.
5. **Browser console path.** NetBox permissions authorize the handoff. Tickets, upstream URLs, Proxmox credentials, and TLS policy remain server-side and must not be exposed to the browser.
6. **Optional companion services.** netbox-rpc, netbox-packer, OpenBao, PBS, PDM, Ceph, and other integrations retain their own authorization and audit boundaries. Installing a companion does not grant Proxbox implicit authority.

## Trusted and untrusted actors

| Actor | Trust | Security posture |
| --- | --- | --- |
| NetBox, PostgreSQL, Redis, and configured workers | Trusted | They execute plugin code and hold application state or secrets. |
| Infrastructure and application administrators | Trusted | Host, database, configuration, or secret access implies full control. |
| Active NetBox superusers | Trusted | NetBox intentionally permits superusers to bypass object-level permission checks. |
| Operators permitted to manage endpoints, credentials, jobs, approvals, consoles, or infrastructure writes | Trusted for the granted capability | These permissions can cause outbound access or managed-system changes by design. `view_nodesshcredential` is service-level secret-reveal authority, not a safe general inventory-view permission. |
| Authenticated users without those permissions | Untrusted | They must remain inside NetBox's model and object permission constraints. |
| proxbox-api and explicitly enabled companion services | Trusted service principals | They are trusted only for configured routes, identities, endpoints, and capabilities. |
| Proxmox API responses, guest-agent data, discovered inventory, imported files, webhook payloads, and remote error text | Untrusted data | Validate before storage, rendering, logging, or use in a path or request. |
| Unauthenticated or Internet-adjacent parties | Untrusted | They are outside the supported deployment model and must not reach management services directly. |

## Privileged-by-design behavior

The following behavior is intentional when an authorized operator uses the corresponding capability:

- storing encrypted service credentials and using them for outbound NetBox, proxbox-api, Proxmox, PBS, PDM, or companion requests;
- discovering infrastructure and creating or updating NetBox inventory during synchronization;
- queuing, canceling, retrying, or repairing synchronization and maintenance jobs;
- opening a permission-gated browser console through the server-side relay;
- enabling explicitly gated Proxmox writes, template builds, RPC procedures, or other approved operational actions;
- reading infrastructure data that the operator and the configured service identity are permitted to view;
- configuring a private endpoint or trusted proxy that causes the service to contact that exact destination.

These capabilities are not vulnerabilities merely because they can change infrastructure, reach an internal service, or use privileged credentials. A vulnerability exists when a less-privileged actor obtains the capability, a declared gate is bypassed, authority changes without revalidation, or a secret crosses its intended boundary.

## In-scope vulnerabilities

Examples include:

- authentication, CSRF, or NetBox object-permission bypass;
- horizontal or vertical privilege escalation across endpoint, tenant, job, console, approval, or write permissions;
- a disabled endpoint or write gate still causing network access or a managed-system mutation;
- server-side request forgery, redirect following, hostname or URL injection, or endpoint substitution that escapes the exact configured authority;
- exposure of plaintext credentials, API keys, console tickets, private keys, authorization headers, or recoverable secret material through APIs, pages, logs, changelogs, exceptions, telemetry, or artifacts;
- cryptographic or state-management flaws that permit ciphertext substitution, stale-key reuse, cross-endpoint decryption, or unsafe reset or rotation;
- stored or reflected cross-site scripting against another user, unsafe template rendering, SQL/ORM injection, command injection, path traversal, or unsafe deserialization;
- replay, race, or confused-deputy flaws that bypass an approval, consume another actor's authorization, or execute a different action than the reviewed request;
- object-permission constraint bypasses, or tenant isolation failures where the deployment has configured tenant-aware permission constraints;
- browser-console authorization bypass, ticket leakage, origin confusion, or relay access outside the selected VM or container;
- dependency vulnerabilities with a realistic exploit path through supported Proxbox behavior.

## Out-of-scope issues and intended behavior

The following are normally outside this project's vulnerability scope:

- actions performed by a trusted NetBox superuser, host administrator, database administrator, or holder of the relevant endpoint or write permission;
- direct database or filesystem modification by an administrator;
- rate limiting, TLS termination, network firewalls, host patching, backups, and resource quotas that belong to the reverse proxy or deployment platform;
- client-IP spoofing when an operator trusts an untrusted proxy or forwards unsanitized client-address headers;
- self-XSS with no effect on another user or privilege boundary;
- denial of service that requires trusted administrative access or deployment outside documented capacity and network controls;
- failures caused solely by unsupported NetBox, Proxmox, proxbox-api, Python, database, or companion versions;
- use of intentionally disabled TLS verification in a production or hostile network;
- an automated dependency or source scan without a confirmed reachable exploit path.

## Lightweight STRIDE analysis

| Category | Proxbox posture |
| --- | --- |
| Spoofing | NetBox sessions and API tokens authenticate users; API keys authenticate proxbox-api calls; upstream credentials authenticate service identities. Exact endpoint binding, TLS verification, and trusted-proxy configuration protect peer identity. |
| Tampering | NetBox permissions, schema validation, transactions, write gates, approvals, and upstream authorization protect changes. Audit records must not contain secrets. |
| Repudiation | NetBox changelog entries, job records, approval records, and companion audit trails identify operations. Operators must preserve logs and synchronized time. |
| Information disclosure | NetBox object permissions limit inventory. Tenant fields, request filters, and `allowed_tenants` metadata do not automatically isolate ordinary Proxbox inventory APIs; deployments that require tenant isolation must configure explicit NetBox object-permission constraints. Encryption protects stored secrets, while API responses, templates, logs, telemetry, and console relays must redact them. |
| Denial of service | Bounded jobs, timeouts, concurrency controls, reverse-proxy limits, and infrastructure quotas protect availability. Deployment-level capacity remains the operator's responsibility. |
| Elevation of privilege | Superusers and explicitly authorized operators are trusted. Any unintended bypass of model permissions, endpoint gates, approvals, tenant scope, or companion authorization is in scope. |

## Operator security checklist

- Keep NetBox, NetBox Proxbox, proxbox-api, and companion packages on supported releases.
- Expose only the reverse proxy; isolate databases, queues, proxbox-api, and management interfaces.
- Require TLS and verify certificates for every service-to-service connection.
- Use dedicated least-privilege NetBox, Proxmox, SSH, and companion identities.
- Restrict endpoint, credential, job, console, approval, and write permissions to trusted operators. Reserve `view_nodesshcredential` for the dedicated proxbox-api service identity because it authorizes plaintext credential retrieval without object-level narrowing.
- Keep write capabilities disabled until explicitly required and independently authorized.
- Protect and back up the plugin encryption key separately from encrypted database values.
- Rotate credentials after suspected exposure and review logs for secret leakage.
- Configure explicit NetBox object-permission constraints when tenant isolation is required; do not treat tenant fields, request filters, or endpoint allowlists as a substitute.
- Review enabled endpoints, tenant metadata and allowlists, trusted proxies, RPC procedures, and companion integrations regularly.
- Preserve changelog, job, approval, and service audit records for incident response.

## Relationship to upstream policies

NetBox vulnerabilities must be reported under the [NetBox security policy](https://github.com/netbox-community/netbox/security/policy). Proxmox, Django, FastAPI, or dependency vulnerabilities that do not arise from Proxbox integration should be reported to their respective maintainers. If the affected boundary is unclear, report privately to this project first; maintainers will coordinate with the appropriate upstream project.
