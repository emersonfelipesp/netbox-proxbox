from fastapi import APIRouter

from netbox_proxbox.backend.schemas import PluginConfig
from netbox_proxbox.backend.schemas.netbox import *

router = APIRouter()

PROXBOX_PLUGIN_NAME = "netbox_proxbox"

@router.get("/plugins-config")
async def netbox_plugins_config(
        plugin_name: str | None = PROXBOX_PLUGIN_NAME,
        list_all: bool | None = False
    ):
    """
    PLUGIN_CONFIG variable defined by user in Netbox 'configuration.py' file
    """

    try:
        from netbox.settings import PLUGINS_CONFIG
    except Exception as e:
        return {
            "error": {
                "message": "Could not import PLUGINS CONFIG from configuration.py",
                "python_exception": f"{e}"
            }
        }

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
        return {
                "error": {
                    "message": "Plugin configuration at PLUGINS_CONFIG (configuration.py) is probably incorrect.",
                    "detail": "Could not feed 'PluginConfig' pydantic model with config provided from 'PLUGINS_CONFIG'.",
                    "python_exception": f"{e}",
            }
        }
        

    return PLUGINS_CONFIG.get(plugin_name, {
            "error": {
                "message": f"Could not get '{plugin_name}' plugin config from 'PLUGINS_CONFIG' variable located at Netbox 'configuration.py'"
            }
        }
    )