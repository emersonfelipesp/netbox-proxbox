from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import select
    
from proxbox_api.schemas import PluginConfig
from proxbox_api.schemas.netbox import NetboxSessionSchema
from proxbox_api.exception import ProxboxException



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
    Asynchronously retrieves the configuration for a specified Netbox plugin from the `PLUGINS_CONFIG` variable 
    located in the Netbox '`configuration.py`' file.
    
    **Args:**
    - **plugin_name (`Annotated[str, Query]`):** The name of the Netbox plugin to get the configuration for. 
    Defaults to PROXBOX_PLUGIN_NAME.
    
    - **list_all (`Annotated[bool, Query]`):** If True, returns the entire PLUGINS_CONFIG including configurations 
    for all plugins. Defaults to False.
   
    **Returns:**
    - **dict:** The configuration for the specified plugin, or an error message if the plugin is not found.
    If `list_all` is `True`, returns the entire `PLUGINS_CONFIG`.
    
    **Raises:**
    - **`ProxboxException`:** If there is an error importing PLUGINS_CONFIG from 'configuration.py' or if the 
    plugin configuration is incorrect and cannot be fed into the PluginConfig pydantic model.
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
    ### Asynchronously retrieves the default settings for Proxbox from the Netbox configuration.
    
    **Returns:**
    - **dict:** The default settings for Proxbox.
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

