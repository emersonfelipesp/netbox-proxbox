from .. import (
    create,
)

async def tag(netbox_vm):
    # Get current tags
    tags = netbox_vm.tags

    # Get tag names from tag objects
    tags_name = []
    for tag in tags:
        tags_name.append(tag.name)

    
    tags = await create.extras.tag()

    # If Proxbox not found int Netbox tag's list, update object with the tag.
    if tags.name not in tags_name:
        tags.append(tags.id)

        netbox_vm.tags = tags

        # Save new tag to object
        if netbox_vm.save() == True:
            return True
        else:
            return False

    return False