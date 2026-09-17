"""Audit nodes that need local Proxbox SSH credentials before an upgrade."""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from netbox_proxbox.choices import ProxmoxAccessMethodChoices
from netbox_proxbox.models import ProxmoxNode


class Command(BaseCommand):
    help = "List Proxmox nodes that do not have a local NodeSSHCredential."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--fail-on-missing", action="store_true")

    def handle(self, *args, **options) -> None:
        missing = ProxmoxNode.objects.filter(ssh_credential__isnull=True)
        blocking = list(
            missing.filter(
                endpoint__enabled=True,
                endpoint__access_methods=ProxmoxAccessMethodChoices.API_SSH,
            )
            .order_by("pk")
            .values_list("pk", "name")
        )
        informational = list(
            missing.filter(
                ~Q(
                    endpoint__enabled=True,
                    endpoint__access_methods=ProxmoxAccessMethodChoices.API_SSH,
                )
            )
            .order_by("pk")
            .values_list("pk", "name", "endpoint__enabled", "endpoint__access_methods")
        )
        for pk, name in blocking:
            self.stdout.write(f"blocking node_id={pk} name={name}")
        for pk, name, endpoint_enabled, access_methods in informational:
            reason = "disabled_endpoint" if not endpoint_enabled else "api_only"
            self.stdout.write(
                f"informational node_id={pk} name={name} reason={reason} "
                f"access_methods={access_methods}"
            )
        self.stdout.write(f"blocking_missing_local_credentials={len(blocking)}")
        self.stdout.write(
            f"informational_missing_local_credentials={len(informational)}"
        )
        if blocking and options["fail_on_missing"]:
            raise CommandError(
                "Enabled SSH-capable nodes require local NodeSSHCredential rows"
            )
