# NetBox v2.10+ uses Material Design icons and previous versions use Font Awesome.
# This file exists to make plugin compatible with both versions,
# with dictionary dinamicaly mapping class names to underlying MD or FA CSS classess
from .release import NETBOX_RELEASE_CURRENT, NETBOX_RELEASE_210

if NETBOX_RELEASE_CURRENT >= NETBOX_RELEASE_210:
    icon_classes = {
        "plus": "mdi mdi-plus-thick",
        "search": "mdi mdi-magnify",
        "remove": "mdi mdi-close-thick",
    }
else:
    icon_classes = {
        "plus": "fa fa-plus",
        "search": "fa fa-search",
        "remove": "fa fa-remove",
    }