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
        
        # Gunicorn proccess
        gunicorn_proccess = "gunicorn netbox-proxbox.netbox_proxbox.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8030"
        gunicorn_proccess = gunicorn_proccess.split()
        gunicorn_proccess[7] = f"{fastapi_host}:{fastapi_port}"
            
        uvicorn_spawn = None
        # Check if Netbox is running in development mode
        psaux = str(subprocess.run(["sudo", "ps", "aux"], capture_output=True).stdout)
        
        worker_class = "uvicorn.workers.UvicornWorker"
        # Check Uvicorn is running
        if f"gunicorn netbox-proxbox.netbox_proxbox.main:app --workers 4 --worker-class {worker_class} --bind {str(fastapi_host)}:{str(fastapi_port)}" in psaux:
            log_message = "[OK] FastAPI (uvicorn) is already running."
            logging.info(log_message)
            
            psaux = str(psaux)
            psaux_array = psaux.split("\\n")
            
            # Find the PID and command used to deploy existing uvicorn
            for line in psaux_array:
                line_array = line.split()
                try:
                    command = f"{line_array[10]} {line_array[11]} {line_array[12]} {line_array[13]} {line_array[14]} {line_array[15]} {line_array[16]}"
                    if "gunicron netbox-proxbox.netbox_proxbox.main" in command:
                        pid_int = line_array[1]
                        print(f"   > PID: {pid_int}\n   > Command: {command}\n   -> Proxbox will kill t he proccess using the following command: 'kill $(pgrep -P {pid_int})' and 'kill -9 {pid_int}'")
                        subproccess.run(["kill", "$(pgrep", "-P", f"{pid_int})"])
                        subproccess.run(["kill", "-9", {pid_int}])
                except Exception as error:
                    pass
            
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
                uvicorn_spawn = gunicorn_proccess
        else:
            # Spawn uvicorn process
            print("Only Django production process was found. Running uvicorn without '--reload' parameter.")

            uvicorn_spawn = gunicorn_proccess
            
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

if fastapi_host == None and fastapi_port == None:
    logging.error("[ERROR] FastAPI Host and FastAPI Port not configured by user at 'configuration.py'")
if fastapi_host == None:
    logging.error("[ERROR] FastAPI Host not configured by user at 'configuration.py'")
if fastapi_error == None:
    logging.error("[ERROR] FastAPI Port not configured by user at 'configuration.py'")
