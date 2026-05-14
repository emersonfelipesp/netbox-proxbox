"""Data callables consolidated for the ``0039_intent_custom_fields`` migration.

Registers the twelve NetBox→Proxmox intent custom fields:

  * Ten VM CFs (``virtualization.virtualmachine``) that carry the desired
    Proxmox state per VM (node, storage, ISO, template VMID, cloud-init
    fields) plus two Proxbox internal stamps (intent state, last apply
    run id).
  * Two Branch CFs (``netbox_branching.branch``) that gate the intent
    pipeline: ``apply_to_proxmox`` and ``apply_destroy_confirmed``.

Branching is optional — `netbox_branching` may not be installed. The
helper guards every Branch CF registration so the migration is safe on
either configuration, matching the runtime ``is_branching_available()``
pattern used elsewhere in the plugin.

Kept in a leading-underscore module so Django's migration loader skips
the file during discovery; only ``0039_intent_custom_fields`` is loaded
as a migration and imports the callables from here.
"""

from __future__ import annotations

VM_OPERATOR_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    (
        "proxmox_node",
        "text",
        "Proxmox target node",
        "Cluster node where the VM should run. Read by proxbox-api when "
        "applying CREATE/UPDATE intent diffs from a branched NetBox merge.",
    ),
    (
        "proxmox_storage",
        "text",
        "Proxmox storage pool",
        "Storage pool to use for the VM's primary disk during CREATE. "
        "Validated at plan time against the node's available storages.",
    ),
    (
        "proxmox_iso",
        "text",
        "Proxmox ISO volume id",
        "Optional Proxmox volume id of the install ISO. Empty means no "
        "ISO is attached on CREATE.",
    ),
    (
        "proxmox_template_vmid",
        "integer",
        "Proxmox template VMID",
        "Source VMID to clone from when creating this VM. Mutually "
        "exclusive with ISO-driven CREATE; both empty means an empty VM.",
    ),
    (
        "cloud_init_user",
        "text",
        "Cloud-Init user",
        "Default cloud-init username (Proxmox ``ciuser``). Optional; "
        "empty means inherit the Proxmox default. See Sub-PR K.",
    ),
    (
        "cloud_init_ssh_keys",
        "longtext",
        "Cloud-Init SSH keys",
        "Newline-separated authorized SSH public keys (Proxmox "
        "``sshkeys``). See Sub-PR K.",
    ),
    (
        "cloud_init_user_data",
        "longtext",
        "Cloud-Init user-data (YAML)",
        "Optional raw cloud-init user-data YAML rendered via ``cicustom``. "
        "Plan-time warning if it contains a literal ``password:`` key. "
        "See Sub-PR K.",
    ),
    (
        "cloud_init_network",
        "longtext",
        "Cloud-Init network config",
        "Optional cloud-init network config block (``ipconfig0`` style). "
        "See Sub-PR K.",
    ),
)

VM_INTERNAL_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    (
        "proxbox_intent_state",
        "text",
        "Proxbox intent state",
        "Last terminal intent verdict for this VM. One of ``applied``, "
        "``pending``, ``failed``. Written by proxbox-api after an apply "
        "run; do not edit by hand.",
    ),
    (
        "proxbox_last_apply_run_id",
        "text",
        "Proxbox last apply run id",
        "UUID of the most recent ProxmoxApplyJob touching this VM. Used "
        "to correlate the VM row with the apply log; managed by Proxbox.",
    ),
)

# Backwards-compat alias: the union of operator and internal fields. Kept
# so external test fixtures or operator scripts that reference the old
# name continue to resolve; the unregister path iterates this union too.
VM_INTENT_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    VM_OPERATOR_FIELDS + VM_INTERNAL_FIELDS
)

BRANCH_INTENT_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    (
        "apply_to_proxmox",
        "boolean",
        "Apply this branch to Proxmox",
        "Set to True on a netbox-branching branch to opt that branch into "
        "the NetBox→Proxmox intent pipeline. Default False; merging a "
        "branch with this flag off triggers no Proxmox-side mutation.",
    ),
    (
        "apply_destroy_confirmed",
        "boolean",
        "Apply destroys allowed for this branch",
        "Set to True on a netbox-branching branch to acknowledge that any "
        "DELETE diffs in the branch should produce DeletionRequest rows "
        "for separate authorization. Default False; absent this flag, "
        "DELETE diffs short-circuit at plan time.",
    ),
)


def _ensure_intent_cf(
    CustomField,
    ContentType,
    name: str,
    type_: str,
    label: str,
    description: str,
    *,
    app_label: str,
    model: str,
    ui_visible: str = "always",
    ui_editable: str = "yes",
    filter_logic: str = "loose",
) -> bool:
    """Register one intent CF on the given content type. Idempotent.

    Returns True when the CF row was created or its content-type pin was
    added; False when nothing needed to happen.
    """
    try:
        ct = ContentType.objects.get(app_label=app_label, model=model)
    except ContentType.DoesNotExist:
        return False

    cf, created = CustomField.objects.get_or_create(
        name=name,
        defaults={
            "type": type_,
            "label": label,
            "description": description,
            "ui_visible": ui_visible,
            "ui_editable": ui_editable,
            "filter_logic": filter_logic,
            "required": False,
            "search_weight": 0,
        },
    )
    changed = created
    if not cf.object_types.filter(pk=ct.pk).exists():
        cf.object_types.add(ct)
        changed = True
    return changed


def register_intent_custom_fields(apps, schema_editor):
    """Register the 12 NetBox→Proxmox intent CFs. Idempotent.

    Operator-facing VM CFs land with default ui flags (visible + editable).
    Internal Proxbox stamps land hidden + non-editable + filter disabled
    so operators cannot hand-edit them and defeat drift detection — the
    pattern matches ``register_last_synced_role_cf`` in
    ``_v0_0_15_release_data.py``.

    Skips Branch CFs silently when the ``netbox_branching`` plugin is not
    installed (its ContentType row will be missing). Note: the migration
    only runs at install time; if ``netbox_branching`` is installed after
    this migration has already applied, the two Branch CFs will not be
    backfilled automatically — the operator guide in Sub-PR L documents
    the manual remediation.
    """
    CustomField = apps.get_model("extras", "CustomField")
    ContentType = apps.get_model("contenttypes", "ContentType")

    for name, type_, label, description in VM_OPERATOR_FIELDS:
        _ensure_intent_cf(
            CustomField,
            ContentType,
            name,
            type_,
            label,
            description,
            app_label="virtualization",
            model="virtualmachine",
        )

    for name, type_, label, description in VM_INTERNAL_FIELDS:
        _ensure_intent_cf(
            CustomField,
            ContentType,
            name,
            type_,
            label,
            description,
            app_label="virtualization",
            model="virtualmachine",
            ui_visible="hidden",
            ui_editable="hidden",
            filter_logic="disabled",
        )

    for name, type_, label, description in BRANCH_INTENT_FIELDS:
        _ensure_intent_cf(
            CustomField,
            ContentType,
            name,
            type_,
            label,
            description,
            app_label="netbox_branching",
            model="branch",
        )


def unregister_intent_custom_fields(apps, schema_editor):
    """Remove every intent CF. Used by ``Migration.reverse_code``."""
    CustomField = apps.get_model("extras", "CustomField")
    names = [name for name, *_ in VM_INTENT_FIELDS + BRANCH_INTENT_FIELDS]
    CustomField.objects.filter(name__in=names).delete()
