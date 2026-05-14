"""Provide NetBox CRUD views for the Cloud Portal cloud image template catalog."""

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import CloudImageTemplateFilterSet
from netbox_proxbox.forms import CloudImageTemplateFilterForm, CloudImageTemplateForm
from netbox_proxbox.models import CloudImageTemplate
from netbox_proxbox.tables import CloudImageTemplateTable


__all__ = (
    "CloudImageTemplateView",
    "CloudImageTemplateListView",
    "CloudImageTemplateEditView",
    "CloudImageTemplateDeleteView",
    "CloudImageTemplateBulkDeleteView",
)


@register_model_view(CloudImageTemplate, "list", path="", detail=False)
class CloudImageTemplateListView(generic.ObjectListView):
    """Global list of cloud image templates with export and bulk delete actions."""

    queryset = CloudImageTemplate.objects.select_related("cluster").prefetch_related(
        "allowed_tenants", "tags"
    )
    table = CloudImageTemplateTable
    filterset = CloudImageTemplateFilterSet
    filterset_form = CloudImageTemplateFilterForm
    template_name = "netbox_proxbox/cloudimagetemplate_list.html"
    actions = {
        "add": {"add"},
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(CloudImageTemplate)
class CloudImageTemplateView(generic.ObjectView):
    """Detail view for a single cloud image template with tenant scope and source VMID."""

    queryset = CloudImageTemplate.objects.select_related("cluster").prefetch_related(
        "allowed_tenants", "tags"
    )
    template_name = "netbox_proxbox/cloudimagetemplate.html"


@register_model_view(CloudImageTemplate, "add", detail=False)
@register_model_view(CloudImageTemplate, "edit")
class CloudImageTemplateEditView(generic.ObjectEditView):
    """Create or edit a cloud image template entry."""

    queryset = CloudImageTemplate.objects.all()
    form = CloudImageTemplateForm
    default_return_url = "plugins:netbox_proxbox:cloudimagetemplate_list"


@register_model_view(CloudImageTemplate, "delete")
class CloudImageTemplateDeleteView(generic.ObjectDeleteView):
    """Delete a single cloud image template entry."""

    queryset = CloudImageTemplate.objects.all()
    default_return_url = "plugins:netbox_proxbox:cloudimagetemplate_list"


@register_model_view(CloudImageTemplate, "bulk_delete", detail=False)
class CloudImageTemplateBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete cloud image templates from the global list."""

    queryset = CloudImageTemplate.objects.select_related("cluster")
    filterset = CloudImageTemplateFilterSet
    table = CloudImageTemplateTable
    default_return_url = "plugins:netbox_proxbox:cloudimagetemplate_list"
