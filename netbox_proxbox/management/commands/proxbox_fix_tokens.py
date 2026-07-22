"""Django management command to check and explicitly bootstrap legacy tokens.

Usage:
    python manage.py proxbox_fix_tokens [--fix]

This command:
- Lists all FastAPIEndpoint objects and their token status
- Checks if tokens are registered with the proxbox-api backend
- With --fix, records an explicit adoption fingerprint and, only when required,
  bootstraps an enabled legacy row against an empty backend
"""

from argparse import ArgumentParser
from dataclasses import replace

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Command implementation."""

    help = "Check and explicitly adopt eligible legacy FastAPIEndpoint keys"

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Handle add arguments."""
        parser.add_argument(
            "--fix",
            action="store_true",
            help=(
                "Adopt an enabled legacy row and bootstrap its retained key only "
                "when the backend has no keys"
            ),
        )

    def handle(self, *args: object, **options: object) -> None:
        """Handle handle."""
        from netbox_proxbox.models import FastAPIEndpoint
        from django.db import connection

        from netbox_proxbox.services.backend_key_adoption import (
            BackendKeyAdoptionProof,
            BackendKeyAdoptionError,
            backend_key_runtime_is_trusted,
            backend_key_target,
            backend_key_target_fingerprint,
            bootstrap_backend_key_at_url,
            inspect_backend_key_at_url,
        )

        def persist_adoption(
            endpoint: FastAPIEndpoint,
            candidate: str,
            proof: BackendKeyAdoptionProof,
        ) -> bool:
            """Persist one explicit proof through the model's adoption gate."""
            endpoint.token = candidate
            endpoint._backend_key_adoption_proof = replace(
                proof,
                target_fingerprint=backend_key_target_fingerprint(endpoint),
            )
            try:
                endpoint.save(update_fields={"token_enc"})
            except (ValidationError, ValueError, TypeError):
                self.stdout.write(
                    self.style.ERROR(
                        "  Adoption: FAILED; the endpoint row was left unchanged"
                    )
                )
                return False
            self.stdout.write(
                self.style.SUCCESS("  Adoption: target fingerprint recorded")
            )
            return True

        fix_mode = options.get("fix", False)

        self.stdout.write("=" * 60)
        self.stdout.write("FastAPIEndpoint Token Status")
        self.stdout.write("=" * 60)

        endpoints = FastAPIEndpoint.objects.all()
        if not endpoints:
            self.stdout.write(self.style.WARNING("No FastAPIEndpoint objects found."))
            self.stdout.write(
                "Create a FastAPIEndpoint in NetBox: Plugins > ProxBox > Endpoints > FastAPI"
            )
            return

        all_registered = True

        for endpoint in endpoints:
            self.stdout.write("")
            self.stdout.write(f"FastAPIEndpoint ID: {endpoint.pk}")
            self.stdout.write(f"  Name: {endpoint.name}")
            self.stdout.write(f"  Domain: {endpoint.domain or '(none)'}")

            if endpoint.ip_address:
                self.stdout.write(f"  IP Address: {endpoint.ip_address.address}")
            else:
                self.stdout.write("  IP Address: (none)")

            self.stdout.write(f"  Port: {endpoint.port}")
            self.stdout.write(f"  Verify SSL: {endpoint.verify_ssl}")
            self.stdout.write(f"  Enabled: {endpoint.enabled}")

            token_status = "HAS TOKEN" if endpoint.token else "NO TOKEN"
            token_style = self.style.SUCCESS if endpoint.token else self.style.ERROR
            self.stdout.write(f"  Token: {token_style(token_status)}")

            if not endpoint.token:
                all_registered = False
                continue

            if not bool(getattr(endpoint, "enabled", True)):
                self.stdout.write(
                    self.style.WARNING(
                        "  Backend Status: Disabled; no network check was performed. "
                        "Enable the endpoint and explicitly resubmit its key first."
                    )
                )
                all_registered = False
                continue

            target_trusted = backend_key_runtime_is_trusted(endpoint)
            stored_target_fingerprint = str(
                getattr(endpoint, "backend_key_target_fingerprint", "") or ""
            ).strip()
            if not stored_target_fingerprint and not fix_mode:
                self.stdout.write(
                    self.style.WARNING(
                        "  Backend Status: Legacy target is not adopted; no network "
                        "check was performed. Review the target and run with --fix."
                    )
                )
                all_registered = False
                continue
            if stored_target_fingerprint and not target_trusted:
                self.stdout.write(
                    self.style.ERROR(
                        "  Backend Status: REFUSED because the adopted target has "
                        "drifted. Explicitly resubmit the key through the endpoint "
                        "form or API."
                    )
                )
                all_registered = False
                continue

            try:
                base_url, verify_ssl = backend_key_target(endpoint)
            except BackendKeyAdoptionError as exc:
                self.stdout.write(
                    self.style.WARNING(f"  Backend URL: Cannot construct ({exc.code})")
                )
                all_registered = False
                continue

            self.stdout.write(f"  Backend URL: {base_url}")

            try:
                inspection = inspect_backend_key_at_url(
                    base_url,
                    verify_ssl,
                    endpoint.token,
                )
            except BackendKeyAdoptionError as exc:
                self.stdout.write(
                    self.style.ERROR(f"  Token Status: Validation failed ({exc.code})")
                )
                all_registered = False
                continue

            if inspection.state == "accepted":
                proof = BackendKeyAdoptionProof(
                    fingerprint=inspection.fingerprint,
                    action="adopted",
                )
                if target_trusted:
                    self.stdout.write(
                        self.style.SUCCESS("  Token Status: Registered with backend")
                    )
                    continue
                if not fix_mode:
                    self.stdout.write(
                        self.style.WARNING(
                            "  Token Status: Accepted, but the legacy target is "
                            "not adopted; run with --fix"
                        )
                    )
                    all_registered = False
                    continue
                if not persist_adoption(endpoint, endpoint.token, proof):
                    all_registered = False
                continue

            self.stdout.write(
                self.style.WARNING("  Backend Status: Needs bootstrap (no keys)")
            )
            if fix_mode:
                if connection.in_atomic_block:
                    self.stdout.write(
                        self.style.ERROR(
                            "  Registration: REFUSED inside a database transaction"
                        )
                    )
                    all_registered = False
                    continue
                self.stdout.write("  Attempting one-time key bootstrap...")
                try:
                    proof = bootstrap_backend_key_at_url(
                        base_url,
                        verify_ssl,
                        endpoint.token,
                        label=f"netbox-fastapi-{endpoint.pk}",
                    )
                except BackendKeyAdoptionError as exc:
                    self.stdout.write(
                        self.style.ERROR(f"  Registration: FAILED ({exc.code})")
                    )
                    all_registered = False
                else:
                    if persist_adoption(endpoint, endpoint.token, proof):
                        self.stdout.write(self.style.SUCCESS("  Registration: SUCCESS"))
                    else:
                        all_registered = False
            else:
                self.stdout.write("  Run with --fix to attempt registration")
                all_registered = False

        self.stdout.write("")
        self.stdout.write("=" * 60)

        if all_registered:
            self.stdout.write(
                self.style.SUCCESS(
                    "All FastAPIEndpoint tokens are registered with their backends."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Some endpoints need attention. Use --fix only after reviewing "
                    "the target of an enabled legacy row and retaining its stored key."
                )
            )

        self.stdout.write("")
        if fix_mode:
            self.stdout.write("Token fix completed.")
        else:
            self.stdout.write(
                "Use --fix for explicit legacy target adoption; bootstrap occurs "
                "only when the backend is empty."
            )
