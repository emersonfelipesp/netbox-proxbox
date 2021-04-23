import django_filters
from django.db.models import Q

from virtualization.models import VirtualMachine, Cluster

from .models import ProxmoxVM


class ProxmoxVMFilter(django_filters.FilterSet):
    """Filter capabilities for ProxmoxVM instances."""

    q = django_filters.CharFilter(
        # method = the method it must call when the field is used
        method="search",
        # label = the text that will appear in the field as a hint.
        label="Search",
    )

    # django_filters.ModelMultipleChoiceFilter = drop down-menu with multiple choices
    cluster = django_filters.ModelMultipleChoiceFilter(
        # field_name = specifies attribute on the model field that we will filter 'ProxmoxVM' objects on
        # cluster = field   
        field_name="cluster__name",
        queryset=Cluster.objects.all(),
        to_field_name="name",
    )

    node = django_filters.CharFilter(
        # icontains = case insensitive partial match
        # default lookup method is exact which forces exact matches.
        lookup_expr="icontains",
    )

    virtual_machine = django_filters.ModelMultipleChoiceFilter(
        field_name="virtual_machine__name",
        queryset=VirtualMachine.objects.all(),
        to_field_name="name",
    )

    # uses exact match to filter 'proxmox_vm_id' field
    proxmox_vm_id = django_filters.CharFilter()

    # define model this filter is based on
    class Meta:
        model = ProxmoxVM

        # list of fields for which filters will be auto-generated
        # any field that doesn't need special treatment goes here
        fields = [
            "type",
            "description",
        ]

    def search(self, queryset, name, value):
        """Perform the filtered search."""

        # queryset =  list of objects currently meeting filter criteria, before q filter is applied
        # name = name of the filter field
        # value = value entered into the filter field in web GUI
        
        # returns unchanged query set if no value was provided
        if not value.strip():
            return queryset

        # if there is a value, use 'Q' Django object to build a query based on two fields
        qs_filter = Q(type__icontains=value) | Q(description__icontains=value)
        
        # apply this filter to queryset and return the result.
        # if value is contained in either 'type'' or 'description',
        # for given object then the object will be included in final queryset
        return queryset.filter(qs_filter)