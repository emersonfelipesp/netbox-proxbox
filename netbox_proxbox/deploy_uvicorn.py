from . import proxbox_api

# Import config
fastapi_host = proxbox_api.plugins_config.FASTAPI_HOST
fastapi_port = proxbox_api.plugins_config.FASTAPI_PORT

import logging


def deploy():
    # Deploy FastAPI with uvicorn instance
    try:
        import subprocess

        # Import config
        fastapi_host = proxbox_api.plugins_config.FASTAPI_HOST
        fastapi_port = proxbox_api.plugins_config.FASTAPI_PORT
        
        uvicorn_spawn = None
        # Check if Netbox is running in development mode
        psaux = str(subprocess.run(["sudo", "ps", "aux"], capture_output=True).stdout)

        # Check Uvicorn is running
        if f"uvicorn netbox-proxbox.netbox_proxbox.main:app --host {str(fastapi_host)} --port {str(fastapi_port)}" in psaux:
            log_message = "[OK] FastAPI (uvicorn) is already running."
            logging.info(log_message)
            return {
                'fastapi_host': fastapi_host,
                'fastapi_port': fastapi_port,
            }

        # Check if there's already a process running with the same port
        output = str(subprocess.run(["sudo", "netstat", "-tuln"], capture_output=True).stdout)
        if f":{fastapi_port}" in output:
            log_message = f"[ERROR] Port '{fastapi_port}' is already being used.\n   > Unable to spawn uvicorn process, you'll have to change the port or kill the proccess running.\nTo do this, change 'PLUGINS_CONFIG' variable in 'configuration.py' Netbox"
            logging.error(log_message)
            
            # Increment Port by one.
            fastapi_port = str(int(fastapi_port) + 1)

            logging.info(f"[INFO] Since the port is already being used, Proxbox will try to increment the port number by one ({fastapi_port}) and deploy de proccess:")
            
            # Check again if there's already a process running with the same port
            output_2 = str(subprocess.run(["sudo", "netstat", "-tuln"], capture_output=True).stdout)
            
            if f":{fastapi_port}" in output:
                log_message = f"[ERROR] Port '{fastapi_port}' is already being used. (2)\n   > Proxbox won't try running it to avoid unexpected troubles.\n   > Try using following shell commands:\n   -> 'ps aux | grep :{fastapi_port}'\n   -> 'netstat -tuln | grep :{fastapi_port}'"
                logging.error(log_message)

                # Increment Port by one.
                fastapi_port = str(int(fastapi_port) + 1)
                    

        # Check if Django is running
        if "manage.py runserver" in psaux:
            if ":8000" in psaux:
                # Spawn uvicorn process with '--reload' option
                print("Django Development (manage.py runserver) process was found, running uvicorn with '--reload' parameter.")
                uvicorn_spawn = ["uvicorn", "netbox-proxbox.netbox_proxbox.main:app", "--host", str(fastapi_host), "--port", str(fastapi_port), "--reload"]   
        else:
            # Spawn uvicorn process
            print("Only Django production process was found. Running uvicorn without '--reload' parameter.")
            uvicorn_spawn = ["uvicorn", "netbox-proxbox.netbox_proxbox.main:app", "--host", str(fastapi_host), "--port", str(fastapi_port)]
        subprocess.Popen(uvicorn_spawn)
        
    except Exception as error:
        log_message = f"[ERROR] {error}"
        logging.error(log_message)
        raise Exception(log_message)
    
    return {
        'fastapi_host': fastapi_host,
        'fastapi_port': fastapi_port,
    }

result = deploy()
fastapi_host = result.get("fastapi_host", None)
fastapi_port = result.get("fastapi_port", None)