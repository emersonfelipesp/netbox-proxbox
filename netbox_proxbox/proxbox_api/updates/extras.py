from .. import (
    create,
)

def tag(netbox_vm):
    # Get current tags
    tags = netbox_vm.tags

    # Get tag names from tag objects
    tags_name = []
    for tag in tags:
        tags_name.append(tag.name)

    
    # If Proxbox not found int Netbox tag's list, update object with the tag.
    if create.extras.tag().name not in tags_name:
        tags.append(create.extras.tag().id)

        netbox_vm.tags = tags

        # Save new tag to object
        if netbox_vm.save() == True:
            return True
        else:
            return False

    return False