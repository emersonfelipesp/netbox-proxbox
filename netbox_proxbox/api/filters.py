import django_filters
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from netbox_proxbox.models import SyncProcess
from netbox_proxbox.choices import SyncTypeChoices, SyncStatusChoices

class SyncProcessFilterSet(NetBoxModelFilterSet):
    """
    FilterSet for SyncProcess model.
    
    This filter set provides filtering capabilities for SyncProcess objects,
    allowing users to filter by various fields in both the UI and API.
    
    Available filters:
    - sync_type: Filter by sync process type (full, incremental, etc.)
    - status: Filter by sync process status (pending, running, completed, etc.)
    - started_after: Filter processes started after a specific date
    - started_before: Filter processes started before a specific date
    - completed_after: Filter processes completed after a specific date
    - completed_before: Filter processes completed before a specific date
    - q: General search across name and comments
    """
    sync_type = django_filters.MultipleChoiceFilter(
        choices=SyncTypeChoices,
        null_value=None
    )
    status = django_filters.MultipleChoiceFilter(
        choices=SyncStatusChoices,
        null_value=None
    )
    started_after = django_filters.DateTimeFilter(
        field_name='started_at',
        lookup_expr='gte'
    )
    started_before = django_filters.DateTimeFilter(
        field_name='started_at',
        lookup_expr='lte'
    )
    completed_after = django_filters.DateTimeFilter(
        field_name='completed_at',
        lookup_expr='gte'
    )
    completed_before = django_filters.DateTimeFilter(
        field_name='completed_at',
        lookup_expr='lte'
    )
    q = django_filters.CharFilter(
        method='search',
        label='Search',
    )

    class Meta:
        model = SyncProcess
        fields = ['id', 'name', 'sync_type', 'status', 'started_at', 'completed_at']

    def search(self, queryset, name, value):
        """
        Perform a general search across name and comments.
        """
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) |
            Q(comments__icontains=value)
        ) 