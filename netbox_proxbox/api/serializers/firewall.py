"""API serializers for Proxmox firewall models."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.api.serializers.cluster import (
    NestedProxmoxEndpointSerializer,
    NestedProxmoxNodeSerializer,
)
from netbox_proxbox.choices import (
    FirewallLogLevelChoices,
    FirewallRuleTypeChoices,
    FirewallScopeChoices,
    FirewallSyncStatusChoices,
    FirewallZoneChoices,
)
from netbox_proxbox.models import (
    ProxmoxFirewallAlias,
    ProxmoxFirewallIPSet,
    ProxmoxFirewallIPSetEntry,
    ProxmoxFirewallOptions,
    ProxmoxFirewallRule,
    ProxmoxFirewallSecurityGroup,
)


class NestedProxmoxFirewallSecurityGroupSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxfirewallsecuritygroup-detail",
    )

    class Meta:
        model = ProxmoxFirewallSecurityGroup
        fields = ("id", "url", "display", "name")
        brief_fields = ("id", "url", "display", "name")


class ProxmoxFirewallSecurityGroupSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxfirewallsecuritygroup-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer(required=False, allow_null=True)
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxFirewallSecurityGroup
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "name",
            "comment",
            "status",
            "raw_config",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "status")


class ProxmoxFirewallRuleSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxfirewallrule-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer(required=False, allow_null=True)
    proxmox_node = NestedProxmoxNodeSerializer(required=False, allow_null=True)
    virtual_machine = NestedVirtualMachineSerializer(required=False, allow_null=True)
    security_group = NestedProxmoxFirewallSecurityGroupSerializer(
        required=False, allow_null=True
    )
    zone = ChoiceField(choices=FirewallZoneChoices)
    rule_type = ChoiceField(choices=FirewallRuleTypeChoices)
    log = ChoiceField(choices=FirewallLogLevelChoices, required=False, allow_blank=True)
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxFirewallRule
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "zone",
            "proxmox_node",
            "virtual_machine",
            "security_group",
            "pos",
            "rule_type",
            "action",
            "enable",
            "macro",
            "iface",
            "source",
            "dest",
            "proto",
            "dport",
            "sport",
            "log",
            "icmp_type",
            "comment",
            "digest",
            "status",
            "raw_config",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "zone",
            "pos",
            "rule_type",
            "action",
            "enable",
            "status",
        )


class ProxmoxFirewallIPSetSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxfirewallipset-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer(required=False, allow_null=True)
    virtual_machine = NestedVirtualMachineSerializer(required=False, allow_null=True)
    scope = ChoiceField(choices=FirewallScopeChoices)
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxFirewallIPSet
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "scope",
            "virtual_machine",
            "name",
            "comment",
            "status",
            "raw_config",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "scope", "status")


class NestedProxmoxFirewallIPSetSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxfirewallipset-detail",
    )

    class Meta:
        model = ProxmoxFirewallIPSet
        fields = ("id", "url", "display", "name", "scope")
        brief_fields = ("id", "url", "display", "name", "scope")


class ProxmoxFirewallIPSetEntrySerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxfirewallipsetentry-detail",
    )
    ipset = NestedProxmoxFirewallIPSetSerializer(required=True)

    class Meta:
        model = ProxmoxFirewallIPSetEntry
        fields = (
            "id",
            "url",
            "display",
            "ipset",
            "cidr",
            "comment",
            "nomatch",
            "raw_config",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "cidr", "nomatch")


class ProxmoxFirewallAliasSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxfirewallalias-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer(required=False, allow_null=True)
    virtual_machine = NestedVirtualMachineSerializer(required=False, allow_null=True)
    scope = ChoiceField(choices=FirewallScopeChoices)
    status = ChoiceField(choices=FirewallSyncStatusChoices, required=False)

    class Meta:
        model = ProxmoxFirewallAlias
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "scope",
            "virtual_machine",
            "name",
            "cidr",
            "comment",
            "status",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "cidr", "scope", "status")


class ProxmoxFirewallOptionsSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxfirewalloptions-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer(required=False, allow_null=True)
    proxmox_node = NestedProxmoxNodeSerializer(required=False, allow_null=True)
    virtual_machine = NestedVirtualMachineSerializer(required=False, allow_null=True)
    zone = ChoiceField(choices=FirewallZoneChoices)

    class Meta:
        model = ProxmoxFirewallOptions
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "zone",
            "proxmox_node",
            "virtual_machine",
            "enable",
            "policy_in",
            "policy_out",
            "options",
            "raw_config",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "zone",
            "enable",
            "policy_in",
            "policy_out",
        )
