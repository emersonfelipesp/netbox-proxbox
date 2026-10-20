"""Typed request contract and endpoint permissions for local cluster reconciliation."""

from dcim.models import Site
from django.db.models import QuerySet
from rest_framework import serializers
from tenancy.models import Tenant
from virtualization.models import ClusterType


class VisiblePrimaryKeyField(serializers.PrimaryKeyRelatedField):
    """Resolve referenced inventory without exposing hidden object existence."""

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().restrict(self.context["request"].user, "view")


class ClusterBindingRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    mode = serializers.ChoiceField(choices=("cluster", "standalone"))
    cluster_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    cluster_type = VisiblePrimaryKeyField(queryset=ClusterType.objects.all())
    site = VisiblePrimaryKeyField(
        queryset=Site.objects.all(), required=False, allow_null=True
    )
    tenant = VisiblePrimaryKeyField(
        queryset=Tenant.objects.all(), required=False, allow_null=True
    )
