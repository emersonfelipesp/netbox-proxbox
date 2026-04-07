"""Django management command to check and fix FastAPIEndpoint tokens.

Usage:
    python manage.py proxbox_fix_tokens [--fix]

This command:
- Lists all FastAPIEndpoint objects and their token status
- Checks if tokens are registered with the proxbox-api backend
- With --fix, attempts to register unregistered tokens
"""

import logging
from argparse import ArgumentParser

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Check and fix FastAPIEndpoint tokens and backend registration"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Attempt to register unregistered tokens with the backend",
        )

    def handle(self, *args: object, **options: object) -> None:
        from netbox_proxbox.models import FastAPIEndpoint
        from netbox_proxbox.signals import (
            _get_backend_url,
            _register_token_with_backend,
        )

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

            token_status = "HAS TOKEN" if endpoint.token else "NO TOKEN"
            token_style = self.style.SUCCESS if endpoint.token else self.style.ERROR
            self.stdout.write(f"  Token: {token_style(token_status)}")

            if endpoint.token:
                self.stdout.write(f"  Token Preview: {endpoint.token[:20]}...")
            else:
                all_registered = False
                continue

            base_url = _get_backend_url(endpoint)
            if not base_url:
                self.stdout.write(
                    self.style.WARNING("  Backend URL: Cannot construct (no domain/IP)")
                )
                all_registered = False
                continue

            self.stdout.write(f"  Backend URL: {base_url}")

            import requests

            try:
                status_resp = requests.get(
                    f"{base_url}/auth/bootstrap-status",
                    verify=endpoint.verify_ssl,
                    timeout=5,
                )
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    needs_bootstrap = status_data.get("needs_bootstrap", True)
                    has_db_keys = status_data.get("has_db_keys", False)

                    if needs_bootstrap and not has_db_keys:
                        self.stdout.write(
                            self.style.WARNING(
                                "  Backend Status: Needs bootstrap (no keys)"
                            )
                        )
                        all_registered = False

                        if fix_mode:
                            self.stdout.write("  Attempting to register token...")
                            if _register_token_with_backend(endpoint):
                                self.stdout.write(
                                    self.style.SUCCESS("  Registration: SUCCESS")
                                )
                            else:
                                self.stdout.write(
                                    self.style.ERROR("  Registration: FAILED")
                                )
                        else:
                            self.stdout.write(
                                "  Run with --fix to attempt registration"
                            )
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                "  Backend Status: Has API keys configured"
                            )
                        )

                        keys_resp = requests.get(
                            f"{base_url}/auth/keys",
                            headers={"X-Proxbox-API-Key": endpoint.token},
                            verify=endpoint.verify_ssl,
                            timeout=5,
                        )
                        if keys_resp.status_code == 200:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    "  Token Status: Registered with backend"
                                )
                            )
                        elif keys_resp.status_code == 401:
                            self.stdout.write(
                                self.style.WARNING(
                                    "  Token Status: NOT registered with backend"
                                )
                            )
                            all_registered = False
                            if fix_mode:
                                self.stdout.write("  Attempting to register token...")
                                if _register_token_with_backend(endpoint):
                                    self.stdout.write(
                                        self.style.SUCCESS("  Registration: SUCCESS")
                                    )
                                else:
                                    self.stdout.write(
                                        self.style.ERROR("  Registration: FAILED")
                                    )
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  Token Status: Unknown (HTTP {keys_resp.status_code})"
                                )
                            )
                            all_registered = False
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Backend Status: Error (HTTP {status_resp.status_code})"
                        )
                    )
                    all_registered = False

            except requests.exceptions.RequestException as exc:
                self.stdout.write(
                    self.style.ERROR(f"  Backend Status: Connection failed - {exc}")
                )
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
                    "Some endpoints need attention. Run with --fix to attempt automatic registration."
                )
            )

        self.stdout.write("")
        if fix_mode:
            self.stdout.write("Token fix completed.")
        else:
            self.stdout.write("Use --fix to attempt automatic token registration.")
