# PLUGIN_CONFIG variables
from ..plugins_config import (
    NETBOX_SESSION as nb,
)

#
# extras.tags
# 
def tag():
    proxbox_tag_name = 'Proxbox'
    proxbox_tag_slug = 'proxbox'

    # Check if Proxbox tag already exists.
    proxbox_tag = nb.extras.tags.get(
        name = proxbox_tag_name,
        slug = proxbox_tag_slug
    )

    if proxbox_tag == None:
        try:
            # If Proxbox tag does not exist, create one.
            tag = nb.extras.tags.create(
                name = proxbox_tag_name,
                slug = proxbox_tag_slug,
                color = 'ff5722',
                description = "Proxbox Identifier (used to identify the items the plugin created)"
            )
        except:
            return "Error creating the '{0}' tag. Possible errors: the name '{0}' or slug '{1}' is already used.".format(proxbox_tag_name, proxbox_tag_slug)
    else:
        tag = proxbox_tag

    return tag





#
# dcim.device_roles
#
# OBS: this function is here and not in ./dcim.py since it is used by both NODE and VIRTUAL MACHINE.
def role(**kwargs):
    # If role_id equals to 0, consider it is not configured by user and must be created by Proxbox
    role_id = kwargs.get("role_id", 0)

    if not isinstance(role_id, int):
        return 'Role ID must be INTEGER. Netbox PLUGINS_CONFIG is configured incorrectly.'

    # If user configured ROLE_ID in Netbox's PLUGINS_CONFIG, use it.
    if role_id > 0:
        role = nb.dcim.device_roles.get(id = role_id)
        
        if role == None:
            return "Role ID of Virtual Machine or Node invalid. Maybe the ID passed does not exist or it is not a integer!"

    elif role_id == 0:
        role_proxbox_name = "Proxbox Basic Role"
        role_proxbox_slug = 'proxbox-basic-role'

        # Verify if basic role is already created
        role_proxbox = nb.dcim.device_roles.get(
            name = role_proxbox_name,
            slug = role_proxbox_slug
        )

        # Create a basic Proxbox VM/Node Role if not created yet.
        if role_proxbox == None:

            try:
                role = nb.dcim.device_roles.create(
                    name = role_proxbox_name,
                    slug = role_proxbox_slug,
                    color = 'ff5722',
                    vm_role = True
                )
            except:
                return "Error creating the '{0}' role. Possible errors: the name '{0}' or slug '{1}' is already used.".format(role_proxbox_name, role_proxbox_slug)
        
        # If basic role already created, use it.
        else:
            role = role_proxbox

    else:
        return 'Role ID configured is invalid.'

    return role