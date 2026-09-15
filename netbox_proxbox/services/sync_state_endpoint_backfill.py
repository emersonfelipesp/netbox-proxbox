"""Bind VM sync-state rows to corroborated plugin Proxmox endpoints."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import hmac
import json

from netbox_proxbox.models.sync_state import ProxboxVirtualMachineSyncState


UNVERIFIED_SAMPLE_LIMIT = 20
_REVIEW_TOKEN_DIGEST_LENGTH = 16
_VM_MODEL_NAME = "ProxboxVirtualMachineSyncState"


class ConfirmationReviewError(ValueError):
    """Refuse a confirmation whose reviewed identities are absent or stale."""


@dataclass(frozen=True)
class BackfillSummary:
    """Serializable counts and refusals from one endpoint backfill pass."""

    rows_bound_by_model: dict[str, int]
    skipped_backend_ids: dict[str, str]
    unverified: dict[str, dict[str, object]] = field(default_factory=dict)
    confirmed_bindings: dict[str, dict[str, object]] = field(default_factory=dict)

    @property
    def total_rows_bound(self) -> int:
        """Return the total number of rows bound across all sidecar models."""
        return sum(self.rows_bound_by_model.values())

    @property
    def total_unverified(self) -> int:
        """Return the number of matching rows deliberately left unbound."""
        return sum(int(item["count"]) for item in self.unverified.values())

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation for job data."""
        return {
            "rows_bound_by_model": dict(self.rows_bound_by_model),
            "skipped_backend_ids": dict(self.skipped_backend_ids),
            "unverified": dict(self.unverified),
            "confirmed_bindings": dict(self.confirmed_bindings),
            "total_rows_bound": self.total_rows_bound,
            "total_unverified": self.total_unverified,
        }

    def one_line(self) -> str:
        """Return a stable one-line rendering for jobs and commands."""
        return (
            "Sync-state endpoint backfill: "
            "automatic_corroboration=locked_relations_only "
            f"rows_bound_by_model={json.dumps(self.rows_bound_by_model, sort_keys=True)} "
            f"skipped_backend_ids={json.dumps(self.skipped_backend_ids, sort_keys=True)} "
            f"unverified_rows_left_unbound={self.total_unverified} "
            f"unverified={json.dumps(self.unverified, sort_keys=True)} "
            f"confirmed_bindings={json.dumps(self.confirmed_bindings, sort_keys=True)}"
        )


def _canonical_positive_id(value: object) -> str | None:
    """Return a canonical positive decimal identifier or ``None``."""
    try:
        normalized = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return str(normalized) if normalized > 0 else None


def _endpoint_claims(
    backend_id_by_plugin_pk: Mapping[str, str],
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Group plugin endpoint primary keys by canonical backend id."""
    claims: dict[str, set[str]] = {}
    skipped: dict[str, str] = {}
    for plugin_pk, backend_id in backend_id_by_plugin_pk.items():
        raw_backend_id = str(backend_id).strip() or "<blank>"
        canonical_backend_id = _canonical_positive_id(backend_id)
        canonical_plugin_pk = _canonical_positive_id(plugin_pk)
        if canonical_backend_id is None:
            skipped[raw_backend_id] = "backend id is not a positive integer"
            continue
        if canonical_plugin_pk is None:
            skipped[canonical_backend_id] = (
                f"plugin endpoint primary key {plugin_pk!r} is not a positive integer"
            )
            continue
        claims.setdefault(canonical_backend_id, set()).add(canonical_plugin_pk)
    return claims, skipped


def _ambiguous_claim_reasons(claims: Mapping[str, set[str]]) -> dict[str, str]:
    """Describe backend ids claimed by more than one plugin endpoint."""
    return {
        backend_id: (
            "claimed by multiple ProxmoxEndpoint primary keys: "
            + ", ".join(sorted(plugin_pks, key=int))
        )
        for backend_id, plugin_pks in claims.items()
        if len(plugin_pks) > 1
    }


def _confirmation_pairs(
    confirmed_bindings: Mapping[str, str] | None,
) -> set[tuple[str, str]]:
    """Return canonical backend-id/plugin-pk confirmation pairs."""
    pairs = set()
    for backend_id, plugin_pk in (confirmed_bindings or {}).items():
        canonical_backend_id = _canonical_positive_id(backend_id)
        canonical_plugin_pk = _canonical_positive_id(plugin_pk)
        if canonical_backend_id is not None and canonical_plugin_pk is not None:
            pairs.add((canonical_backend_id, canonical_plugin_pk))
    return pairs


def _confirmation_tokens(
    review_tokens: Mapping[str, str] | None,
) -> dict[str, str]:
    """Return review tokens keyed by canonical backend id."""
    return {
        canonical_backend_id: str(token)
        for backend_id, token in (review_tokens or {}).items()
        if (canonical_backend_id := _canonical_positive_id(backend_id)) is not None
    }


def _candidate_rows(backend_id: str, *, lock: bool) -> list[dict[str, object]]:
    """Load unbound VM rows carrying one current backend id."""
    queryset = ProxboxVirtualMachineSyncState.objects.filter(
        endpoint__isnull=True,
        proxmox_endpoint_raw_id=backend_id,
    ).order_by("pk")
    if lock:
        queryset = queryset.select_for_update()
    return list(
        queryset.values(
            "pk",
            "proxmox_cluster_id",
            "proxmox_node_id",
            "proxmox_cluster_name",
        )
    )


def _locked_relation_endpoints(
    rows: list[dict[str, object]],
    *,
    lock: bool,
) -> tuple[dict[str, str], dict[str, str]]:
    """Load endpoint ownership from the related cluster and node rows."""
    from netbox_proxbox.models.proxmox_cluster import ProxmoxCluster
    from netbox_proxbox.models.proxmox_node import ProxmoxNode

    endpoints = []
    for model, relation_field in (
        (ProxmoxCluster, "proxmox_cluster_id"),
        (ProxmoxNode, "proxmox_node_id"),
    ):
        related_pks = {
            row[relation_field] for row in rows if row[relation_field] is not None
        }
        queryset = model.objects.filter(pk__in=related_pks).order_by("pk")
        if lock:
            queryset = queryset.select_for_update()
        endpoints.append(
            {
                str(pk): str(endpoint_id)
                for pk, endpoint_id in queryset.values_list("pk", "endpoint_id")
            }
        )
    return endpoints[0], endpoints[1]


def _corroborated_row_pks(
    rows: list[dict[str, object]],
    plugin_pk: str,
    cluster_endpoints: Mapping[str, str],
    node_endpoints: Mapping[str, str],
) -> tuple[list[int], dict[str, list[dict[str, object]]]]:
    """Partition candidate row pks by their locked endpoint evidence."""
    corroborated: list[int] = []
    unverified: dict[str, list[dict[str, object]]] = {
        "no_relation_evidence": [],
        "not_corroborated": [],
        "relations_disagree": [],
    }
    for row in rows:
        row_pk = int(row["pk"])
        cluster_id = row["proxmox_cluster_id"]
        node_id = row["proxmox_node_id"]
        if cluster_id is None and node_id is None:
            unverified["no_relation_evidence"].append(row)
            continue
        cluster_endpoint = cluster_endpoints.get(str(cluster_id))
        node_endpoint = node_endpoints.get(str(node_id))
        present_endpoints = [
            endpoint
            for relation_id, endpoint in (
                (cluster_id, cluster_endpoint),
                (node_id, node_endpoint),
            )
            if relation_id is not None
        ]
        if all(endpoint == plugin_pk for endpoint in present_endpoints):
            corroborated.append(row_pk)
        elif cluster_id is not None and node_id is not None:
            unverified["relations_disagree"].append(row)
        else:
            unverified["not_corroborated"].append(row)
    return corroborated, {
        reason: reason_rows for reason, reason_rows in unverified.items() if reason_rows
    }


def _unverified_reason(plugin_pk: str) -> str:
    """Describe the evidence missing from rows refused automatic binding."""
    return (
        "at least one locked cluster/node relation must be present and every present "
        f"relation must belong to plugin endpoint {plugin_pk}; a recorded cluster "
        "name is not automatic ownership evidence"
    )


def _reason_buckets(
    unverified_by_reason: Mapping[str, list[dict[str, object]]],
    *,
    bounded: bool,
) -> dict[str, dict[str, object]]:
    """Build stable per-reason counts and reviewable row samples."""
    key = "sample_pks" if bounded else "row_pks"
    buckets: dict[str, dict[str, object]] = {}
    for reason, reason_rows in unverified_by_reason.items():
        displayed_rows = (
            reason_rows[:UNVERIFIED_SAMPLE_LIMIT] if bounded else reason_rows
        )
        bucket: dict[str, object] = {
            "count": len(reason_rows),
            key: [int(row["pk"]) for row in displayed_rows],
        }
        if bounded:
            bucket["sample_rows"] = [
                {
                    "pk": int(row["pk"]),
                    "proxmox_cluster_name": row["proxmox_cluster_name"],
                }
                for row in displayed_rows
            ]
        buckets[reason] = bucket
    return buckets


def _binding_bucket(
    backend_id: str,
    plugin_pk: str,
    row_pks: list[int],
    unverified_by_reason: Mapping[str, list[dict[str, object]]],
    *,
    bounded: bool,
    review_token: str | None = None,
) -> dict[str, object]:
    """Build one stable summary bucket for a backend/plugin pair."""
    key = "sample_pks" if bounded else "row_pks"
    bucket: dict[str, object] = {
        "backend_id": backend_id,
        "plugin_endpoint_pk": plugin_pk,
        "count": len(row_pks),
        key: row_pks[:UNVERIFIED_SAMPLE_LIMIT] if bounded else row_pks,
        "reason": _unverified_reason(plugin_pk),
        "reasons": _reason_buckets(unverified_by_reason, bounded=bounded),
    }
    if review_token is not None:
        bucket["review_token"] = review_token
    return bucket


def _token_mapping(
    backend_id_by_plugin_pk: Mapping[str, str],
) -> list[list[str]]:
    """Return the canonical valid mapping embedded in a review token."""
    claims, _skipped = _endpoint_claims(backend_id_by_plugin_pk)
    return [
        [plugin_pk, backend_id]
        for backend_id, plugin_pks in sorted(
            claims.items(), key=lambda item: int(item[0])
        )
        for plugin_pk in sorted(plugin_pks, key=int)
    ]


def _review_token(
    backend_id: str,
    plugin_pk: str,
    row_pks: list[int],
    backend_id_by_plugin_pk: Mapping[str, str],
) -> str:
    """Return a deterministic, self-contained token for one reviewed PK set."""
    payload = json.dumps(
        {
            "backend_id": backend_id,
            "mapping": _token_mapping(backend_id_by_plugin_pk),
            "plugin_endpoint_pk": plugin_pk,
            "row_pks": sorted(row_pks),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    digest = hashlib.sha256(payload).hexdigest()[:_REVIEW_TOKEN_DIGEST_LENGTH]
    return f"v1.{encoded}.{digest}"


def _reviewed_row_pks(
    token: str | None,
    backend_id: str,
    plugin_pk: str,
    backend_id_by_plugin_pk: Mapping[str, str],
) -> list[int]:
    """Decode and validate one self-contained review token."""
    pair_key = f"{backend_id}={plugin_pk}"
    if not token:
        raise ConfirmationReviewError(
            f"--confirm-binding {pair_key} requires the dry-run review token on apply."
        )
    try:
        version, encoded, supplied_digest = token.split(".")
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        expected_digest = hashlib.sha256(payload).hexdigest()[
            :_REVIEW_TOKEN_DIGEST_LENGTH
        ]
        decoded = json.loads(payload)
    except (
        ValueError,
        binascii.Error,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        raise ConfirmationReviewError(
            f"--confirm-binding {pair_key} has an invalid review token."
        ) from exc
    canonical_payload = json.dumps(
        decoded, separators=(",", ":"), sort_keys=True
    ).encode()
    if (
        version != "v1"
        or not isinstance(decoded, dict)
        or canonical_payload != payload
        or len(supplied_digest) != _REVIEW_TOKEN_DIGEST_LENGTH
        or not hmac.compare_digest(supplied_digest, expected_digest)
    ):
        raise ConfirmationReviewError(
            f"--confirm-binding {pair_key} has an invalid review token."
        )
    expected_identity = {
        "backend_id": backend_id,
        "mapping": _token_mapping(backend_id_by_plugin_pk),
        "plugin_endpoint_pk": plugin_pk,
    }
    if any(decoded.get(key) != value for key, value in expected_identity.items()):
        raise ConfirmationReviewError(
            f"--confirm-binding {pair_key} review token mapping no longer matches "
            "the current endpoint mapping. Run a new dry run."
        )
    row_pks = decoded.get("row_pks")
    if (
        not isinstance(row_pks, list)
        or any(type(pk) is not int or pk <= 0 for pk in row_pks)
        or row_pks != sorted(set(row_pks))
    ):
        raise ConfirmationReviewError(
            f"--confirm-binding {pair_key} has an invalid review token."
        )
    return row_pks


def _require_reviewed_row_set(
    reviewed_pks: list[int],
    current_pks: list[int],
    backend_id: str,
    plugin_pk: str,
) -> None:
    """Refuse a confirmation when the locked unverified set changed."""
    added = sorted(set(current_pks) - set(reviewed_pks))
    removed = sorted(set(reviewed_pks) - set(current_pks))
    if added or removed:
        raise ConfirmationReviewError(
            f"--confirm-binding {backend_id}={plugin_pk} review set changed; "
            f"added_pks={added}; removed_pks={removed}. Run a new dry run."
        )


def _backfill_claims(
    backend_id_by_plugin_pk: Mapping[str, str],
    claims: Mapping[str, set[str]],
    skipped: dict[str, str],
    confirmed_pairs: set[tuple[str, str]],
    review_tokens: Mapping[str, str],
    *,
    apply: bool,
) -> BackfillSummary:
    """Process unambiguous endpoint claims against current row evidence."""
    rows_by_model = {_VM_MODEL_NAME: 0}
    unverified: dict[str, dict[str, object]] = {}
    confirmed: dict[str, dict[str, object]] = {}
    for backend_id, plugin_pks in sorted(claims.items(), key=lambda item: int(item[0])):
        if backend_id in skipped:
            continue
        plugin_pk = next(iter(plugin_pks))
        rows = _candidate_rows(backend_id, lock=apply)
        cluster_endpoints, node_endpoints = _locked_relation_endpoints(rows, lock=apply)
        corroborated_pks, unverified_by_reason = _corroborated_row_pks(
            rows,
            plugin_pk,
            cluster_endpoints,
            node_endpoints,
        )
        unverified_pks = sorted(
            int(row["pk"])
            for reason_rows in unverified_by_reason.values()
            for row in reason_rows
        )
        pair_key = f"{backend_id}={plugin_pk}"
        if (backend_id, plugin_pk) in confirmed_pairs:
            token = _review_token(
                backend_id, plugin_pk, unverified_pks, backend_id_by_plugin_pk
            )
            confirmed[pair_key] = _binding_bucket(
                backend_id,
                plugin_pk,
                unverified_pks,
                unverified_by_reason,
                bounded=False,
                review_token=token,
            )
            if apply:
                reviewed_pks = _reviewed_row_pks(
                    review_tokens.get(backend_id),
                    backend_id,
                    plugin_pk,
                    backend_id_by_plugin_pk,
                )
                _require_reviewed_row_set(
                    reviewed_pks, unverified_pks, backend_id, plugin_pk
                )
            corroborated_pks.extend(unverified_pks)
        elif unverified_pks:
            unverified[pair_key] = _binding_bucket(
                backend_id,
                plugin_pk,
                unverified_pks,
                unverified_by_reason,
                bounded=True,
            )
        corroborated_pks.sort()
        changed = len(corroborated_pks)
        if apply and corroborated_pks:
            changed = ProxboxVirtualMachineSyncState.objects.filter(
                endpoint__isnull=True,
                proxmox_endpoint_raw_id=backend_id,
                pk__in=corroborated_pks,
            ).update(endpoint_id=plugin_pk)
        rows_by_model[_VM_MODEL_NAME] += int(changed)
    return BackfillSummary(rows_by_model, skipped, unverified, confirmed)


def _backfill_sync_state_endpoints(
    backend_id_by_plugin_pk: Mapping[str, str],
    *,
    apply: bool,
    confirmed_bindings: Mapping[str, str] | None = None,
    confirmation_review_tokens: Mapping[str, str] | None = None,
) -> BackfillSummary:
    """Count or apply corroborated and explicitly confirmed endpoint bindings."""
    claims, skipped = _endpoint_claims(backend_id_by_plugin_pk)
    skipped.update(_ambiguous_claim_reasons(claims))
    arguments = (
        backend_id_by_plugin_pk,
        claims,
        skipped,
        _confirmation_pairs(confirmed_bindings),
        _confirmation_tokens(confirmation_review_tokens),
    )
    if not apply:
        return _backfill_claims(*arguments, apply=False)

    from django.db import transaction

    with transaction.atomic():
        return _backfill_claims(*arguments, apply=True)


def backfill_sync_state_endpoints(
    backend_id_by_plugin_pk: Mapping[str, str],
    *,
    confirmed_bindings: Mapping[str, str] | None = None,
    confirmation_review_tokens: Mapping[str, str] | None = None,
) -> BackfillSummary:
    """Bind null endpoint FKs when locked evidence or confirmation agrees."""
    return _backfill_sync_state_endpoints(
        backend_id_by_plugin_pk,
        apply=True,
        confirmed_bindings=confirmed_bindings,
        confirmation_review_tokens=confirmation_review_tokens,
    )


def preview_sync_state_endpoint_backfill(
    backend_id_by_plugin_pk: Mapping[str, str],
    *,
    confirmed_bindings: Mapping[str, str] | None = None,
) -> BackfillSummary:
    """Count bindings and issue review tokens without changing sync state."""
    return _backfill_sync_state_endpoints(
        backend_id_by_plugin_pk,
        apply=False,
        confirmed_bindings=confirmed_bindings,
    )
