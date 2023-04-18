from . import proxbox_api

# Import config
fastapi_host = proxbox_api.plugins_config.FASTAPI_HOST
fastapi_port = proxbox_api.plugins_config.FASTAPI_PORT

import logging

import subprocess
import sys

def kill_proccess(**kwargs):
    # Get vars from fucntion calll
    name = kwargs.get("name", None)
    psaux = kwargs.get("psaux", None)
    
    # Check if variable is filled
    if psaux == None:
        logging.error("[ERROR] Variable 'psaux' was not informed when calling 'kill_proccess' function")
        return
    if name == None:
        logging.error("[ERROR] Variable 'name' was not informed when calling 'kill_proccess' function")
        return
    
    # Split 'ps aux' output into list
    psaux_array = psaux.split("\\n")
    
    # Find the PID and command used to deploy existing uvicorn
    for line in psaux_array:
        if line == None:
            logging.error(f"[ERROR] ps aux line is empty\n   > {line}")
    
        # Split words in line into list
        line_array = line.split()
        
        command = None
        pid_int = None
        try:            
            if len(line_array) > 10:
                if "[gunicorn]" in line_array[10] and "<defunct>" in line_array[11]:
                    pid_int = line_array[1]
                if "[uvicorn]" in line_array[10] and "<defunct>" in line_array[11]:
                    pid_int = line_array[1]
                    
                for line in line_array:
                    if name in line and app_type in line:
                        pid_int = line_array[1]
            
                if pid_int != None:
                    print(f"pid_int: {pid_int}") 
                    print(f"   > PID: '{pid_int}'\n   > Command: {command}\n   -> Proxbox will kill t he proccess using the following command: 'kill -9 {pid_int}'")    
                
                    try:
                        # Try kill proccess (and subprocess)
                        subprocess.run(["kill", "-9", str(pid_int)])
                    
                    except Exception as error:
                        logging.error(f"[ERROR] Coudn't kill proccess.\n   > {error}")
            else:
                logging.error(f"[ERROR] Not possible to get proccess name since the proccess line contains less than 10 words.\n   > Proccess line: {line}")
                   
        except Exception as error:
            logging.error(f"[ERROR] Unable to kill existing proccess to use the specified port.\n   > {error}")
            pass


def deploy():
    # Deploy FastAPI with uvicorn instance
    import subprocess
    
    psaux = None
    
    try:
        # Check if Netbox is running in development mode
        psaux = str(subprocess.run(["sudo", "ps", "aux"], capture_output=True).stdout)
    except Exception as error:
        logging.error(f"[ERROR] Not able to get 'ps aux' output\n   > {error}")
        
    try:
        # Import config
        fastapi_host = proxbox_api.plugins_config.FASTAPI_HOST
        fastapi_port = proxbox_api.plugins_config.FASTAPI_PORT
        
        # Gunicorn proccess
        gunicorn_proccess = f"gunicorn netbox-proxbox.netbox_proxbox.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind {fastapi_host}:{fastapi_port}"
        gunicorn_proccess = gunicorn_proccess.split()
        
        # Uvicorn proccess (development mode)
        uvicorn_proccess = f"uvicorn netbox-proxbox.netbox_proxbox.main:app --host {fastapi_host} --port {fastapi_port} --reload"
        uvicorn_proccess = uvicorn_proccess.split()
        
        uvicorn_spawn = None

        
        worker_class = "uvicorn.workers.UvicornWorker"
        # Check Uvicorn is running
        if f"gunicorn netbox-proxbox.netbox_proxbox.main:app --workers 4 --worker-class {worker_class} --bind {str(fastapi_host)}:{str(fastapi_port)}" in psaux:
            log_message = "[OK] FastAPI (uvicorn) is already running."
            logging.info(log_message)
            
            if psaux != None:
                # Try to kill existing proccess
                kill_proccess(
                    app_type = "gunicorn",
                    name = "netbox-proxbox.netbox_proxbox.main", 
                    psaux = str(psaux)
                )
            
            return {
                'fastapi_host': fastapi_host,
                'fastapi_port': fastapi_port,
            }

        # Check if there's already a process running with the same port
        output = str(subprocess.run(["sudo", "netstat", "-tuln"], capture_output=True).stdout)
        if f":{fastapi_port}" in output:
            log_message = f"[ERROR] Port '{fastapi_port}' is already being used.\n   > Unable to spawn uvicorn process, you'll have to change the port or kill the proccess running.\n   > To do this, change 'PLUGINS_CONFIG' variable in 'configuration.py' Netbox"
            logging.error(log_message)
            
            if psaux != None:
                # Try to kill existing proccess
                kill_proccess(
                    app_type = "uvicorn",
                    name = "netbox-proxbox.netbox_proxbox.main:app",
                    psaux = str(psaux),
                )

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
                uvicorn_spawn = uvicorn_proccess
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
if fastapi_port == None:
    logging.error("[ERROR] FastAPI Port not configured by user at 'configuration.py'")
