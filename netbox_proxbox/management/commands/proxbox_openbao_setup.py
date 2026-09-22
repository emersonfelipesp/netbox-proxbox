"""Inspect or create safe structural prerequisites for OpenBao storage."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from netbox_proxbox.services.openbao_readiness import openbao_readiness


class Command(BaseCommand):
    help = "Check or create secret-free structural prerequisites for OpenBao storage."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--check", action="store_true", help="Report only; never write."
        )
        parser.add_argument("--backfill-assignments", action="store_true")
        parser.add_argument("--engine-name", default="Proxbox OpenBao")
        parser.add_argument("--engine-slug", default="proxbox")
        parser.add_argument(
            "--api-url", help="Explicit OpenBao API URL for a new engine."
        )
        parser.add_argument("--namespace", default="")
        parser.add_argument("--kv-mount", default="secret")

    def _print_readiness(self) -> bool:
        readiness = openbao_readiness()
        for item in readiness.items:
            marker = "READY" if item.ready else "MISSING"
            self.stdout.write(f"[{marker}] {item.label}: {item.detail}")
            if not item.ready:
                self.stdout.write(f"  Remedy: {item.remedy}")
        return readiness.ready

    def _create_structure(self, options: dict[str, object]) -> None:
        try:
            from netbox_openbao.models import CredentialPolicy, SecretEngine
            from netbox_openbao.utils import get_default_engine
            from netbox_proxbox.models import ProxboxPluginSettings
        except ImportError as exc:
            raise CommandError(
                "netbox-openbao is unavailable; install and enable it first."
            ) from exc

        settings_row = ProxboxPluginSettings.get_solo()
        engine = get_default_engine()
        if engine is None:
            api_url = str(options.get("api_url") or "").strip()
            if not api_url:
                self.stdout.write(
                    "A default SecretEngine is missing; pass --api-url to create it."
                )
                return
            engine = SecretEngine(
                name=str(options["engine_name"]),
                slug=str(options["engine_slug"]),
                api_url=api_url,
                namespace=str(options["namespace"]),
                kv_mount=str(options["kv_mount"]),
                is_default=True,
            )
            try:
                engine.full_clean()
            except ValidationError as exc:
                raise CommandError(
                    f"Invalid SecretEngine configuration: {exc}"
                ) from exc
            engine.save()
            self.stdout.write(
                self.style.SUCCESS(f"Created default SecretEngine {engine.slug!r}.")
            )
        slug = (settings_row.openbao_policy_slug or "proxbox").strip()
        policy = CredentialPolicy.objects.filter(engine=engine, slug=slug).first()
        if policy is None:
            conflicting = CredentialPolicy.objects.filter(slug=slug).first()
            if conflicting is not None:
                raise CommandError(
                    f"CredentialPolicy {slug!r} belongs to a different engine; "
                    "choose a distinct openbao_policy_slug or reconcile it manually."
                )
            policy = CredentialPolicy(
                engine=engine,
                slug=slug,
                name=slug,
                openbao_policy=slug,
            )
            try:
                policy.full_clean()
            except ValidationError as exc:
                raise CommandError(
                    f"Invalid CredentialPolicy configuration: {exc}"
                ) from exc
            policy.save()
            self.stdout.write(self.style.SUCCESS(f"Created CredentialPolicy {slug!r}."))

    def _backfill(self, *, check: bool) -> None:
        try:
            from netbox_proxbox.services.openbao_assignment_backfill import (
                assignment_proposals,
                backfill_assignments,
            )

            proposals = assignment_proposals()
        except (ImportError, LookupError) as exc:
            raise CommandError("Assignment backfill requires netbox-openbao.") from exc
        except ValidationError as exc:
            raise CommandError(f"Assignment backfill refused: {exc}") from exc
        for proposal in proposals:
            self.stdout.write(
                f"Assignment needed: {proposal.owner} -> {proposal.purpose}"
            )
        if not check:
            try:
                result = backfill_assignments()
            except ValidationError as exc:
                raise CommandError(f"Assignment backfill refused: {exc}") from exc
            self.stdout.write(
                self.style.SUCCESS(f"Created {result.created} assignment(s).")
            )

    def handle(self, *args: object, **options: object) -> None:
        check = bool(options["check"])
        if check:
            ready = self._print_readiness()
            if options["backfill_assignments"]:
                self._backfill(check=True)
            if not ready:
                raise CommandError("OpenBao prerequisites are incomplete.")
            return
        with transaction.atomic():
            self._create_structure(options)
            if options["backfill_assignments"]:
                self._backfill(check=False)
            if not self._print_readiness():
                raise CommandError("OpenBao prerequisites remain incomplete.")
