# Configuring plugin in the old way (<=v0.0.5)

## Change Netbox '**[configuration.py](https://github.com/netbox-community/netbox/blob/develop/netbox/netbox/configuration.example.py)**' to add PLUGIN parameters
The plugin's configuration is also located in **/opt/netbox/netbox/netbox/configuration.py**:

Replace the values with your own following the [Configuration Parameters](#2-configuration-parameters) section.

**OBS:** You do not need to configure all the parameters, only the one's different from the default values. It means that if you have some value equal to the one below, you can skip its configuration. For netbox you should ensure the domain/port either targets gunicorn or a true http port that is not redirected to https.

```python
PLUGINS_CONFIG = {
    'netbox_proxbox': {
        'proxmox': [
            {
                'domain': 'proxbox.example.com',    # May also be IP address
                'http_port': 8006,
                'user': 'root@pam',   # always required
                'password': 'Strong@P4ssword', # only required, if you don't want to use token based authentication
                'token': {
                    'name': 'tokenID',	# Only type the token name and not the 'user@pam:tokenID' format
                    'value': '039az154-23b2-4be0-8d20-b66abc8c4686'
                },
                'ssl': False
            },
            # The following json is optional and applies only for multi-cluster use
            {
                'domain': 'proxbox2.example.com',    # May also be IP address
                'http_port': 8006,
                'user': 'root@pam',   # always required
                'password': 'Strong@P4ssword', # only required, if you don't want to use token based authentication
                'token': {
                    'name': 'tokenID',	# Only type the token name and not the 'user@pam:tokenID' format
                    'value': '039az154-23b2-4be0-8d20-b66abc8c4686'
                },
                'ssl': False
            }
        ],
        'netbox': {
            'domain': 'localhost',     # Ensure localhost is added to ALLOWED_HOSTS
            'http_port': 8001,     # Gunicorn port.
            'token': '0dd7cddfaee3b38bbffbd2937d44c4a03f9c9d38',
            'settings': {
                'virtualmachine_role_id' : 0,
                'node_role_id' : 0,
                'site_id': 0
            }
        },
        'fastapi': {
            # Uvicorn Host is (most of the time) the same as Netbox (as both servers run on the same machine)
            'uvicorn_host': 'localhost',
            'uvicorn_port': 8800,    # Default Proxbox FastAPI port
            # Although it seems weird, the sudo-user is necessary so that Proxbox automatically starts Proxbox Backend.
            # It makes it more "plug-in", without the need to user input manual commands.
            'sudo': {
                'user': "sudo_enabled_user",
                'password': 'Strong@P4ssword',
            }
        }
    }
}
```