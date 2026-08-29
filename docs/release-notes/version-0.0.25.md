# Version 0.0.25

netbox-proxbox `0.0.25` pairs with `proxbox-api 0.0.20`,
`proxmox-sdk 0.0.13`, and the backend's REST dependency
`netbox-sdk 0.0.10`. NetBox support includes a **stable** tier covering
`4.5.8` through `4.6.99`, and **experimental** evaluation of exact canonical
`4.7.0-beta2`. The numeric ceiling is `4.7.0`; canonical metadata must retain
designation `beta2`. The latest certified NetBox release remains `4.6.6`.

Current backend-runtime pairing: netbox-proxbox 0.0.25 <-> proxbox-api 0.0.20 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.6.x; exact canonical 4.7.0-beta2 | v0.0.25 | v0.0.20 | v0.0.10 | v0.0.13 |

## Sync Jobs is now a Proxbox-only page

**Proxbox → Sync & Operations → Sync Jobs** opens `/plugins/proxbox/jobs/` and
lists Proxbox sync jobs only. It previously linked to NetBox's own background
job list, which shows *every* job in the instance — reports, custom scripts, and
any other plugin's work — leaving operators to pick the Proxbox rows out by eye.

- **Nothing familiar is lost.** The page subclasses NetBox's job list, so
  filtering, sorting, pagination, column selection and CSV export behave exactly
  as they do on the core page. Only the queryset is narrowed.
- **What counts as a Proxbox job** is decided by the same rule the rest of the
  plugin already used, expressed as a database filter so it can drive a list
  view. The two are held together by a test that treats the existing per-row
  check as the oracle over a matrix of job rows, so they cannot drift apart.
- **Bulk delete is deliberately omitted.** Its confirmation flow returns to the
  unfiltered core list, which would bounce you out of the page you opened to
  avoid it. Delete a job from its own page, or from **Operations → Background
  Jobs**.

## The bug report for a failed sync is anonymized

Jobs that end in an **errored** or **failed** state — or in a status NetBox does
not recognise — offer a **Bug report** action that packages the job's metadata,
error and logs for an issue on the public tracker. That payload is now scrubbed
before you ever see it.

Sync errors and logs routinely carry Proxmox node hostnames and FQDNs,
management addresses, API URLs, `user@pam` realm principals, API tokens and key
material. Those are replaced with **stable placeholders**: the same host is
`<host-1>` everywhere it appears, so a maintainer can still follow which node
failed which stage without learning what it is called.

- **The pre-filled issue link is generated from the same scrubbed text** as the
  on-screen copy, so opening it cannot publish anything the modal did not show
  you.
- **Diagnosis survives.** A word that merely contains a credential-ish term is
  not an assignment, so `Invalid v1 token` and `session expired` come through
  verbatim, a permission failure keeps its privilege, path and cause, and dotted
  module paths in tracebacks stay readable.
- **Version numbers, timestamps, job IDs and status values are kept** — they
  carry nothing identifying and are what make a report actionable.
- **Scrubbing is best-effort and the modal says so.** A bare single-word node
  name in prose is indistinguishable from any other identifier unless something
  labels it as a host, and a credential key spelled with look-alike characters
  from another script is not matched. Review the text before posting it.

## Credential redaction has one definition

The plugin redacts credentials in two places — on the way into the job log, and
on the way into a public bug report. Those two had drifted apart, so a field
name caught in one was published by the other. They now share one
dependency-free module, and the job-log redactor becomes **strictly stricter**
as a result: it additionally recognises `auth`, `session`, `passphrase`, the
plugin's own `encryption_key`, host/public/signing key names, and the `Token`,
`Digest`, `Negotiate` and `ApiKey` authentication schemes — `Token` being the
scheme NetBox's own API uses.

Redaction is also materially faster on hostile input. Log text is not trusted,
and the previous matcher was quadratic on some shapes; a long run that
previously took tens of seconds now completes in milliseconds.

## Upgrade

No migrations, no configuration changes, and no compatibility changes. Upgrade
the package and restart NetBox as usual; the new page appears under
**Proxbox → Sync & Operations**.
