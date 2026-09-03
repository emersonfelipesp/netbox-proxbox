# `netbox_proxbox.templates`

> **Repository destination guardrail:** This guide inherits the hard rule in
> the repository-root `CLAUDE.md`. EdgeUno and the local EdgeUno vendor
> submodule are read-only reference sources, never change destinations. All
> development writes must target exactly
> `https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox.git`; approved
> public promotion may target only
> `https://github.com/emersonfelipesp/netbox-proxbox.git`. Never mutate EdgeUno
> issues, PRs, branches, commits, tags, releases, packages, mirrors, or
> deployments, and never configure EdgeUno as a writable remote, upstream,
> fallback, or PR base.

This directory contains Django templates bundled with the plugin.

## Structure

- [`netbox_proxbox/`](./netbox_proxbox/): the plugin template namespace used by all plugin views.

## Notes

- Template names in Python views resolve into this namespaced subtree.
- Most behavior-rich pages pair templates here with JS under `static/netbox_proxbox/js/`.
- The namespaced subtree includes shared layout templates, page fragments, table snippets, test pages, and widget partials.
- `netbox_proxbox/proxmoxendpoint_templates.html` enables its netbox-packer
  creation action only through `packer_build_authorized`, which requires an
  enabled endpoint plus both broad and narrow write gates; disabled buttons
  keep the translated refusal text on a tooltip wrapper because disabled
  controls do not receive pointer events. The endpoint detail template displays
  the explicit narrow assertion independently for audit and the read-only
  backend-confirmed grant so a failed revocation's deletion block is visible.
- `netbox_proxbox/settings.html` renders only encrypted-family labels, counts,
  and secret-free states. Rotation password inputs never render submitted or
  stored values. The destructive reset form is omitted unless the user holds
  the separate reset permission; keep all recovery rendering free of dynamic
  `innerHTML` and ciphertext/key material.
- `netbox_proxbox/inc/vm_proxmox_card.html` is the typed reflection card on a
  core VM detail page. It may show only the count of reflected cloud-init SSH
  keys, never their contents, and must rely on Django autoescaping for every
  sidecar and cloud-init value.
- `netbox_proxbox/inc/vm_proxmox_intent_card.html` shows the separate desired
  state only when a `ProxmoxVMIntent` row exists and the request user has model
  view permission plus object visibility through `objects.restrict(user,
  "view")`. If restriction is unavailable or fails, the extension renders
  nothing. All operator text, especially `cloud_init_user_data`, must pass
  through Django autoescaping; never apply the `safe` filter or call `mark_safe`
  on an individual field value.
- `netbox_proxbox/inc/sync_state_card.html` is the shared typed reflection card
  for the other thirteen core object types. `template_content.py` supplies only
  explicit sidecar fields, links resolved relations, and suppresses the card
  when the reverse one-to-one row is absent. Keep Django autoescaping enabled;
  every rendered link must use `target="_blank" rel="noopener"`.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md)
