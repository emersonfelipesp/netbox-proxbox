from typing import Annotated

from fastapi import APIRouter, Depends, Query

from netbox_proxbox.backend.schemas import PluginConfig
from netbox_proxbox.backend.schemas.netbox import NetboxSessionSchema
from netbox_proxbox.backend.schemas.proxmox import ProxmoxMultiClusterConfig
from netbox_proxbox.backend.exception import ProxboxException

router = APIRouter()

PROXBOX_PLUGIN_NAME = "netbox_proxbox"

@router.get("/netbox/plugins-config")
async def netbox_plugins_config(
        plugin_name: Annotated[
            str,
            Query(
                title="Netbox Plugin Name",
                description="Netbox plugin name to get configuration from PLUGINS_CONFIG variable located at Netbox 'configuration.py' file."
            )
        ] | None = PROXBOX_PLUGIN_NAME,
        list_all: Annotated[
            bool,
            Query(
                title="List All Plugins",
                description="Return all plugins configuration from PLUGINS_CONFIG variable located at Netbox 'configuration.py' file.",
            )
        ] | None = False
    ):
    """
    PLUGIN_CONFIG variable defined by user in Netbox 'configuration.py' file
    """

    try:
        from netbox.settings import PLUGINS_CONFIG
    except Exception as e:
        raise ProxboxException(
            message = "Could not import PLUGINS CONFIG from configuration.py",
            python_exception = f"{e}"
        )

    # If ?list=all=True
    # Return complete PLUGINS_CONFIG (including other plugins)
    if list_all:
        return PLUGINS_CONFIG
    
    # Message error to not found plugins.
    plugin_not_found = f"Could not get '{plugin_name}' plugin config from 'PLUGINS_CONFIG' variable located at Netbox 'configuration.py'"
    
    # Search for configuration of another plugin. This feature is not recommended and may cause security issues, use at your own risk.
    if plugin_name != PROXBOX_PLUGIN_NAME:
        return PLUGINS_CONFIG.get(plugin_name, {
                    "error": {
                        "message": plugin_not_found
                    }
                }
            )       
        
    try:
        return PluginConfig(**PLUGINS_CONFIG.get(plugin_name, {
                    "error": {
                        "message": plugin_not_found
                    }
                }
            )
        )
        
    except Exception as e:
        raise ProxboxException(
            message = "Plugin configuration at PLUGINS_CONFIG (configuration.py) is probably incorrect.",
            detail = "Could not feed 'PluginConfig' pydantic model with config provided from 'PLUGINS_CONFIG'.",
            python_exception = f"{e}",
        )


@router.get("/netbox/default-settings")
async def proxbox_netbox_default():
    """
    Default Plugins settings 
    """
    
    from netbox_proxbox import ProxboxConfig
    return ProxboxConfig.default_settings


@router.get("/settings")
async def proxbox_settings(
    plugins_config: Annotated[PluginConfig, Depends(netbox_plugins_config)],
    default_settings: Annotated[PluginConfig, Depends(proxbox_netbox_default)],
    list_all: Annotated[
        bool,
        Query(
            title="List All Plugins",
            description="Return all plugins configuration from PLUGINS_CONFIG variable located at Netbox 'configuration.py' file.",
        )
    ] | None = False
):
    """
    TODO: Compare PLUGINS_CONFIG defined by user with default settings from ProxboxConfig.default_settings
    """
    return plugins_config

ProxboxConfigDep = Annotated[PluginConfig, Depends(proxbox_settings)]

@router.get("/settings/netbox")
async def netbox_settings(
    proxbox_config: ProxboxConfigDep
):
    """
    Get user configuration for Netbox from PLUGINS_CONFIG
    """
    return proxbox_config.netbox

    
    
@router.get("/settings/proxmox")
async def proxmox_settings(
    proxbox_config: ProxboxConfigDep
):
    """
    Get user configuration for Proxmox from PLUGINS_CONFIG
    """
    return proxbox_config.proxmox


NetboxConfigDep = Annotated[NetboxSessionSchema, Depends(netbox_settings)]
ProxmoxConfigDep = Annotated[ProxmoxMultiClusterConfig, Depends(proxmox_settings)]
 