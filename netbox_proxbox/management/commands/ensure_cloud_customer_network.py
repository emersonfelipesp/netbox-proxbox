"""Ensure the NetBox IPAM objects that designate the cloud customer network."""

from __future__ import annotations

from argparse import ArgumentParser
from ipaddress import ip_address, ip_interface, ip_network

from django.core.management.base import BaseCommand, CommandError

GATEWAY_DESCRIPTION = "cloud-customer gateway"


class Command(BaseCommand):
    """Create or reuse the IPAM objects and write plugin settings."""

    help = (
        "Ensure the Role, VLAN, Prefix, gateway IP, and ProxboxPluginSettings "
        "values that designate the cloud customer network."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--prefix",
            required=True,
            help="Cloud customer network CIDR, for example 168.0.98.0/25.",
        )
        parser.add_argument(
            "--vlan",
            type=int,
            required=True,
            help="Cloud customer VLAN tag.",
        )
        parser.add_argument(
            "--vlan-name",
            default="cloud-vmbr1",
            help="Name for the NetBox VLAN row (default: cloud-vmbr1).",
        )
        parser.add_argument(
            "--bridge",
            default="vmbr1",
            help="Proxmox bridge name stored in plugin settings (default: vmbr1).",
        )
        parser.add_argument(
            "--gateway",
            required=True,
            help="Gateway IP address for the prefix, for example 168.0.98.1.",
        )
        parser.add_argument(
            "--role-name",
            default="Cloud Customer",
            help="Name for the NetBox IPAM role (default: Cloud Customer).",
        )
        parser.add_argument(
            "--role-slug",
            default="cloud-customer",
            help="Slug for the NetBox IPAM role (default: cloud-customer).",
        )
        parser.add_argument(
            "--enable-lock",
            action="store_true",
            help="Enable the cloud customer network lock setting after writing values.",
        )

    def handle(self, *args: object, **options: object) -> None:
        """Create missing target objects and populate ProxboxPluginSettings."""
        from ipam.models import IPAddress, Prefix, Role, VLAN

        from netbox_proxbox.models import ProxboxPluginSettings

        network = self._parse_prefix(str(options["prefix"]))
        vlan_tag = int(options["vlan"])
        if vlan_tag < 1 or vlan_tag > 4094:
            raise CommandError("--vlan must be between 1 and 4094.")

        gateway_address, gateway_with_mask = self._parse_gateway(
            str(options["gateway"]),
            network=network,
        )
        vlan_name = str(options["vlan_name"]).strip()
        bridge = str(options["bridge"]).strip()
        role_name = str(options["role_name"]).strip()
        role_slug = str(options["role_slug"]).strip()
        if not vlan_name:
            raise CommandError("--vlan-name must not be empty.")
        if not bridge:
            raise CommandError("--bridge must not be empty.")
        if not role_name:
            raise CommandError("--role-name must not be empty.")
        if not role_slug:
            raise CommandError("--role-slug must not be empty.")

        role, role_created = Role.objects.get_or_create(
            slug=role_slug,
            defaults={"name": role_name},
        )
        vlan, vlan_created = VLAN.objects.get_or_create(
            vid=vlan_tag,
            name=vlan_name,
            role=role,
        )
        prefix, prefix_created = Prefix.objects.get_or_create(
            prefix=str(network),
            role=role,
            vlan=vlan,
        )
        _gateway, gateway_created = IPAddress.objects.get_or_create(
            address=gateway_with_mask,
            defaults={
                "status": "reserved",
                "description": GATEWAY_DESCRIPTION,
            },
        )

        settings = ProxboxPluginSettings.get_solo()
        settings.cloud_customer_prefix_id = prefix.pk
        settings.cloud_customer_bridge = bridge
        settings.cloud_customer_vlan_tag = vlan_tag
        settings.cloud_customer_gateway = str(gateway_address)
        update_fields = [
            "cloud_customer_prefix_id",
            "cloud_customer_bridge",
            "cloud_customer_vlan_tag",
            "cloud_customer_gateway",
        ]
        if bool(options.get("enable_lock")):
            settings.cloud_network_lock_enabled = True
            update_fields.append("cloud_network_lock_enabled")
        settings.save(update_fields=update_fields)

        summary = {
            "role": self._status(role_created),
            "vlan": self._status(vlan_created),
            "prefix": self._status(prefix_created),
            "gateway": self._status(gateway_created),
            "settings": "updated",
            "lock": "enabled" if bool(options.get("enable_lock")) else "unchanged",
        }
        self.stdout.write(
            self.style.SUCCESS(
                "ensure_cloud_customer_network: "
                f"role={summary['role']} "
                f"vlan={summary['vlan']} "
                f"prefix={summary['prefix']} "
                f"gateway={summary['gateway']} "
                f"settings={summary['settings']} "
                f"lock={summary['lock']}"
            )
        )

    def _parse_prefix(self, value: str):
        try:
            return ip_network(value, strict=False)
        except ValueError as exc:
            raise CommandError(f"--prefix must be a valid CIDR: {exc}") from exc

    def _parse_gateway(self, value: str, *, network):
        try:
            gateway = ip_interface(value).ip if "/" in value else ip_address(value)
        except ValueError as exc:
            raise CommandError(f"--gateway must be a valid IP address: {exc}") from exc
        if gateway.version != network.version:
            raise CommandError("--gateway IP version must match --prefix.")
        if gateway not in network:
            raise CommandError("--gateway must be inside --prefix.")
        return gateway, f"{gateway}/{network.prefixlen}"

    def _status(self, created: bool) -> str:
        return "created" if created else "existing"
