"""Bind typed sync-state rows to ProxmoxEndpoint records by backend id."""

from __future__ import annotations

from argparse import ArgumentParser
import time

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Repair endpoint foreign keys on proxbox-api-owned sync-state rows."""

    help = (
        "Bind null sync-state endpoint foreign keys from proxbox-api endpoint ids "
        "corroborated by locked cluster/node relations or explicit confirmation."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Register the backend selector and non-mutating preview flag."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the rows that would be bound without changing them.",
        )
        parser.add_argument(
            "--fastapi-endpoint",
            type=int,
            default=None,
            metavar="PK",
            help="Use this enabled FastAPIEndpoint instead of the default backend.",
        )
        parser.add_argument(
            "--confirm-binding",
            action="append",
            default=[],
            metavar="BACKEND_ID=PLUGIN_PK[:TOKEN]",
            help=(
                "Assert that unverified rows carrying BACKEND_ID belong to the "
                "mapped ProxmoxEndpoint PLUGIN_PK. Preview without TOKEN, then "
                "supply the emitted review token when applying."
            ),
        )

    def handle(self, *args: object, **options: object) -> None:
        """Resolve endpoint identities, then preview or apply the repair."""
        del args
        decision = self._branching_decision()
        confirmations, review_tokens = self._parse_confirmations(
            options.get("confirm_binding")
        )
        mapping = self._resolve_endpoint_mapping(options.get("fastapi_endpoint"))
        if not mapping:
            raise CommandError(
                "No enabled ProxmoxEndpoint could be resolved to a current "
                "proxbox-api backend id; no sync-state row was changed."
            )
        self._validate_confirmations(confirmations, mapping)
        dry_run = bool(options.get("dry_run"))
        if dry_run:
            summary = self._preview(mapping, confirmations)
            self.stdout.write(f"Dry run — {summary.one_line()}")
            return
        self._require_apply_tokens(confirmations, review_tokens)
        review_error = self._confirmation_review_error()
        try:
            summary = self._apply(mapping, confirmations, review_tokens, decision)
        except review_error as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(summary.one_line()))

    @staticmethod
    def _positive_id(value: object, label: str) -> str:
        """Return one canonical positive id or raise a command error."""
        try:
            normalized = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise CommandError(f"{label} must be a positive integer.") from exc
        if normalized <= 0:
            raise CommandError(f"{label} must be a positive integer.")
        return str(normalized)

    @classmethod
    def _parse_confirmations(
        cls, values: object
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Parse repeatable confirmation pairs and optional review tokens."""
        confirmations: dict[str, str] = {}
        review_tokens: dict[str, str] = {}
        for value in values or []:
            pair, separator, token = str(value).partition(":")
            parts = pair.split("=")
            if len(parts) != 2:
                raise CommandError(
                    "--confirm-binding must use BACKEND_ID=PLUGIN_PK[:TOKEN]."
                )
            backend_id = cls._positive_id(parts[0], "confirmed backend id")
            plugin_pk = cls._positive_id(parts[1], "confirmed plugin endpoint pk")
            if backend_id in confirmations and confirmations[backend_id] != plugin_pk:
                raise CommandError(
                    f"backend id {backend_id} was confirmed for multiple plugin "
                    "endpoint pks."
                )
            confirmations[backend_id] = plugin_pk
            if separator:
                normalized_token = token.strip()
                if not normalized_token or ":" in normalized_token:
                    raise CommandError(
                        "--confirm-binding TOKEN must be one nonempty review token."
                    )
                if (
                    backend_id in review_tokens
                    and review_tokens[backend_id] != normalized_token
                ):
                    raise CommandError(
                        f"backend id {backend_id} was supplied multiple review tokens."
                    )
                review_tokens[backend_id] = normalized_token
        return confirmations, review_tokens

    @staticmethod
    def _require_apply_tokens(
        confirmations: dict[str, str], review_tokens: dict[str, str]
    ) -> None:
        """Require every applied assertion to carry its dry-run review token."""
        missing = sorted(set(confirmations) - set(review_tokens), key=int)
        if missing:
            pairs = ", ".join(
                f"{backend_id}={confirmations[backend_id]}" for backend_id in missing
            )
            raise CommandError(f"Apply requires the dry-run review token for: {pairs}.")

    @staticmethod
    def _confirmation_review_error():
        """Return the service error type without importing models at command load."""
        from netbox_proxbox.services.sync_state_endpoint_backfill import (
            ConfirmationReviewError,
        )

        return ConfirmationReviewError

    @classmethod
    def _validate_confirmations(
        cls,
        confirmations: dict[str, str],
        mapping: dict[str, str],
    ) -> None:
        """Require every assertion to equal one unambiguous current mapping."""
        for backend_id, plugin_pk in confirmations.items():
            mapped_plugins = {
                cls._positive_id(candidate_pk, "mapped plugin endpoint pk")
                for candidate_pk, candidate_backend_id in mapping.items()
                if cls._positive_id(candidate_backend_id, "mapped backend id")
                == backend_id
            }
            if mapped_plugins != {plugin_pk}:
                raise CommandError(
                    f"--confirm-binding {backend_id}={plugin_pk} does not match one "
                    "unambiguous current plugin-to-backend endpoint mapping."
                )

    @staticmethod
    def _branching_decision():
        """Resolve branch isolation before any backend access or ORM repair."""
        from netbox_proxbox.services.branch_lifecycle import (
            BranchingUnavailableError,
            require_branch_isolation_or_raise,
        )

        try:
            return require_branch_isolation_or_raise()
        except BranchingUnavailableError as exc:
            raise CommandError(str(exc)) from exc

    @staticmethod
    def _resolve_endpoint_mapping(fastapi_endpoint_id: object) -> dict[str, str]:
        """Resolve every enabled plugin endpoint against one selected backend."""
        from netbox_proxbox.models import ProxmoxEndpoint
        from netbox_proxbox.services.backend_context import (
            get_fastapi_request_context,
        )
        from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_ids

        context = get_fastapi_request_context(endpoint_id=fastapi_endpoint_id)
        if context is None or not context.http_url:
            selected = (
                f" with pk {fastapi_endpoint_id}"
                if fastapi_endpoint_id is not None
                else ""
            )
            raise CommandError(
                f"No usable enabled FastAPIEndpoint{selected} was found."
            )
        endpoints = list(ProxmoxEndpoint.objects.filter(enabled=True))
        mapping, error = resolve_backend_endpoint_ids(
            endpoints,
            base_url=context.http_url,
            auth_headers=context.headers or {},
            backend_verify_ssl=bool(context.verify_ssl),
        )
        if error:
            raise CommandError(f"Could not resolve proxbox-api endpoint ids: {error}")
        return {str(pk): str(backend_id) for pk, backend_id in mapping.items()}

    @staticmethod
    def _preview(mapping: dict[str, str], confirmations: dict[str, str]):
        """Return a non-mutating summary for the resolved mapping."""
        from netbox_proxbox.services.sync_state_endpoint_backfill import (
            preview_sync_state_endpoint_backfill,
        )

        return preview_sync_state_endpoint_backfill(
            mapping,
            confirmed_bindings=confirmations,
        )

    def _apply(
        self,
        mapping: dict[str, str],
        confirmations: dict[str, str],
        review_tokens: dict[str, str],
        decision: object,
    ):
        """Apply on main only when explicitly allowed, otherwise use a branch."""
        from netbox_proxbox.services.branch_lifecycle import BranchingDecisionState
        from netbox_proxbox.services.sync_state_endpoint_backfill import (
            backfill_sync_state_endpoints,
        )

        if decision.state is BranchingDecisionState.DISABLED:
            return backfill_sync_state_endpoints(
                mapping,
                confirmed_bindings=confirmations,
                confirmation_review_tokens=review_tokens,
            )
        return self._apply_in_branch(mapping, confirmations, review_tokens, decision)

    def _apply_in_branch(
        self,
        mapping: dict[str, str],
        confirmations: dict[str, str],
        review_tokens: dict[str, str],
        decision: object,
    ):
        """Create, activate, and merge one isolation branch for the repair."""
        from netbox_proxbox.services.branch_lifecycle import (
            activate_sync_branch,
            create_and_provision_branch,
            merge_branch,
        )
        from netbox_proxbox.services.sync_state_endpoint_backfill import (
            backfill_sync_state_endpoints,
        )

        settings = decision.settings or {}
        prefix = settings.get("prefix", "proxbox-sync")
        branch = create_and_provision_branch(
            name=f"{prefix}-endpoint-backfill-{int(time.time())}",
            user=None,
        )
        with activate_sync_branch(branch):
            summary = backfill_sync_state_endpoints(
                mapping,
                confirmed_bindings=confirmations,
                confirmation_review_tokens=review_tokens,
            )
        merged, message, _disposition = merge_branch(
            branch=branch,
            user=None,
            on_conflict=settings.get("on_conflict", "fail"),
        )
        self.stdout.write(message)
        if not merged:
            raise CommandError(message)
        return summary
