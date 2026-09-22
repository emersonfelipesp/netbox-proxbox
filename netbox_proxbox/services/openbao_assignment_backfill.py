"""Assignment-only repair for Proxbox OpenBao credential references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction


@dataclass(frozen=True, slots=True)
class AssignmentProposal:
    """One missing relation; it contains identifiers, never material."""

    credential_uuid: str
    credential_type: str
    app_label: str
    model: str
    object_id: int
    purpose: str
    primary: bool
    owner: str


@dataclass(frozen=True, slots=True)
class AssignmentBackfillResult:
    proposals: tuple[AssignmentProposal, ...]
    created: int = 0


def _proposal(
    owner: Any,
    reference: Any,
    credential_type: str,
    purpose: str,
    primary: bool,
) -> AssignmentProposal:
    return AssignmentProposal(
        str(reference),
        credential_type,
        owner._meta.app_label,
        owner._meta.model_name,
        int(owner.pk),
        purpose,
        primary,
        f"{owner._meta.label_lower}:{owner.pk}",
    )


def _target_proposal(
    reference: Any,
    *,
    credential_type: str,
    app_label: str,
    model: str,
    object_id: int,
    purpose: str,
    primary: bool,
    owner: str,
) -> AssignmentProposal:
    return AssignmentProposal(
        str(reference),
        credential_type,
        app_label,
        model,
        object_id,
        purpose,
        primary,
        owner,
    )


def _endpoint_proposals() -> Iterable[AssignmentProposal]:
    from netbox_proxbox.integrations.openbao_assignments import _is_primary
    from netbox_proxbox.integrations.openbao_pending import SLOTS
    from netbox_proxbox.models import ProxmoxEndpoint

    for owner in ProxmoxEndpoint.objects.order_by("pk"):
        for field, slot in SLOTS.items():
            reference = getattr(owner, field, None)
            if reference:
                yield _proposal(
                    owner,
                    reference,
                    slot.credential_type,
                    slot.purpose,
                    _is_primary(owner, field),
                )


def _single_proposals() -> Iterable[AssignmentProposal]:
    from netbox_proxbox.integrations.openbao_single_pending import SPECS
    from netbox_proxbox.models import (
        FastAPIEndpoint,
        FirecrackerHost,
        PBSEndpoint,
        PDMEndpoint,
    )

    models = (FastAPIEndpoint, PBSEndpoint, PDMEndpoint, FirecrackerHost)
    for model in models:
        spec = SPECS[model._meta.model_name]
        for owner in model.objects.order_by("pk"):
            reference = getattr(owner, spec.reference_field, None)
            if reference:
                yield _proposal(
                    owner, reference, spec.credential_type, spec.purpose, True
                )


def _node_proposals() -> Iterable[AssignmentProposal]:
    from netbox_proxbox.integrations.openbao_node_assignments import _selected_reference
    from netbox_proxbox.integrations.openbao_node_pending import SLOTS
    from netbox_proxbox.models import NodeSSHCredential

    for owner in NodeSSHCredential.objects.select_related("node").order_by("pk"):
        if not any(getattr(owner, field, None) for field in SLOTS):
            continue
        device_id = getattr(owner.node, "netbox_device_id", None)
        selected_field = _selected_reference(owner)
        reference = getattr(owner, selected_field, None)
        label = f"{owner._meta.label_lower}:{owner.pk}"
        if device_id is None:
            raise ValidationError(
                f"{label} has a provider credential reference but no linked NetBox device."
            )
        if reference is None:
            raise ValidationError(
                f"{label} has provider references but its selected authentication reference is missing."
            )
        yield _target_proposal(
            reference,
            credential_type=SLOTS[selected_field].credential_type,
            app_label="dcim",
            model="device",
            object_id=int(device_id),
            purpose="login",
            primary=True,
            owner=label,
        )


def _cloudinit_proposals() -> Iterable[AssignmentProposal]:
    from netbox_proxbox.integrations.openbao_cloudinit import (
        SPECS,
        _expected_primary_name,
        _references,
    )
    from netbox_proxbox.models import ProxmoxVMCloudInit

    for owner in ProxmoxVMCloudInit.objects.order_by("pk"):
        references = _references(owner)
        primary = _expected_primary_name(owner, references)
        vm = owner.virtual_machine
        for name, spec in SPECS.items():
            reference = references[name]
            if reference:
                yield _proposal(
                    vm,
                    reference,
                    spec.credential_type,
                    spec.purpose,
                    name == primary,
                )


def _require_credential_type(item: AssignmentProposal, credential: Any) -> None:
    if credential.credential_type != item.credential_type:
        raise ValidationError(
            f"The provider credential referenced by {item.owner} has an incompatible type."
        )


def _require_exact_state(item: AssignmentProposal, assignment: Any) -> None:
    if not getattr(assignment, "enabled", True):
        raise ValidationError(
            f"The existing provider assignment for {item.owner} is disabled."
        )
    if bool(assignment.is_primary) != item.primary:
        expected = "primary" if item.primary else "non-primary"
        raise ValidationError(
            f"The existing provider assignment for {item.owner} must be {expected}."
        )


def _exact_assignment(item: AssignmentProposal, credential: Any) -> Any | None:
    from netbox_openbao.models import CredentialAssignment

    return CredentialAssignment.objects.filter(
        credential=credential,
        assigned_object_type__app_label=item.app_label,
        assigned_object_type__model=item.model,
        assigned_object_id=item.object_id,
        purpose=item.purpose,
    ).first()


def assignment_proposals() -> tuple[AssignmentProposal, ...]:
    """Return missing assignments, refusing unresolved references."""
    from netbox_openbao.models import Credential

    proposed: dict[tuple[str, str, str, int, str], AssignmentProposal] = {}
    for item in (
        *_endpoint_proposals(),
        *_single_proposals(),
        *_node_proposals(),
        *_cloudinit_proposals(),
    ):
        credential = Credential.objects.filter(uuid=item.credential_uuid).first()
        if credential is None:
            raise ValidationError(
                f"The provider credential referenced by {item.owner} does not exist."
            )
        _require_credential_type(item, credential)
        exact = _exact_assignment(item, credential)
        if exact is not None:
            _require_exact_state(item, exact)
        else:
            key = (
                item.credential_uuid,
                item.app_label,
                item.model,
                item.object_id,
                item.purpose,
            )
            previous = proposed.get(key)
            if previous is None or (item.primary and not previous.primary):
                proposed[key] = item
    return tuple(proposed.values())


@transaction.atomic
def backfill_assignments() -> AssignmentBackfillResult:
    """Create only missing assignment rows; never alter existing relations."""
    from netbox_openbao.models import Credential, CredentialAssignment

    proposals = assignment_proposals()
    created = 0
    for item in proposals:
        content_type = ContentType.objects.get_by_natural_key(
            item.app_label, item.model
        )
        target_model = content_type.model_class()
        if (
            target_model is None
            or not target_model.objects.select_for_update()
            .filter(pk=item.object_id)
            .exists()
        ):
            raise ValidationError(
                f"The assignment target for {item.owner} is unavailable."
            )
        credential = (
            Credential.objects.select_for_update()
            .filter(uuid=item.credential_uuid)
            .first()
        )
        if credential is None:
            raise ValidationError(
                f"The provider credential referenced by {item.owner} became unavailable."
            )
        _require_credential_type(item, credential)
        exact = _exact_assignment(item, credential)
        if exact is not None:
            _require_exact_state(item, exact)
            continue
        if (
            item.primary
            and CredentialAssignment.objects.filter(
                assigned_object_type=content_type,
                assigned_object_id=item.object_id,
                purpose=item.purpose,
                is_primary=True,
            ).exists()
        ):
            raise ValidationError(
                f"{item.owner} already has a different primary {item.purpose} assignment."
            )
        assignment = CredentialAssignment(
            credential=credential,
            assigned_object_type=content_type,
            assigned_object_id=item.object_id,
            purpose=item.purpose,
            is_primary=item.primary,
        )
        assignment.full_clean()
        try:
            with transaction.atomic():
                assignment.save()
        except IntegrityError as exc:
            exact = _exact_assignment(item, credential)
            if exact is not None:
                _require_exact_state(item, exact)
                continue
            raise ValidationError(
                f"A concurrent assignment conflict prevented backfill for {item.owner}."
            ) from exc
        created += 1
    return AssignmentBackfillResult(proposals, created)
