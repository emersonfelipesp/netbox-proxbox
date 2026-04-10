"""Shared mixin classes for ProxBox tab views."""

from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from extras.models import TableConfig


class TableConfigOverrideMixin:
    """Mixin that builds a child table with optional TableConfig column overrides."""

    table_exclude: tuple[str, ...] = ("virtual_machine",)

    def get_table(
        self, data: object, request: HttpRequest, bulk_actions: bool = True
    ) -> object:
        if tableconfig_id := request.GET.get("tableconfig_id"):
            tableconfig = get_object_or_404(TableConfig, pk=tableconfig_id)
            if request.user.is_authenticated:
                table_name = self.table.__name__
                request.user.config.set(
                    f"tables.{table_name}.columns", tableconfig.columns
                )
                request.user.config.set(
                    f"tables.{table_name}.ordering",
                    tableconfig.ordering,
                    commit=True,
                )

        table = self.table(data, exclude=self.table_exclude)
        if "pk" in table.base_columns and bulk_actions:
            table.columns.show("pk")
        table.configure(request)
        return table
