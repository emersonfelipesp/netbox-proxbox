from django.views import View
from django.shortcuts import render, redirect

try:
    from netbox import configuration
except Exception as error:
    print(error)
    
def returnSudoUser():
    """
    Retrieves the sudo user and password from the plugin configuration.
    This function accesses the plugin configuration to fetch the sudo user and password
    required for FastAPI operations. If the configuration keys are not found, it catches
    the exception and prints the error.
    
    **Returns:**
    - **dict:** A dictionary containing the sudo user and password with keys "user" and "password".
    """
    
    
    plugin_configuration: dict = getattr(configuration, "PLUGINS_CONFIG", {})
    
    sudo_user: str = ""
    sudo_password: str = ""
    try:
        sudo_user = plugin_configuration["netbox_proxbox"]["fastapi"]["sudo"]["user"]
        sudo_password = plugin_configuration["netbox_proxbox"]["fastapi"]["sudo"]["password"]
        
    except Exception as error:
        print(error)
        
    return { "user": sudo_user, "password": sudo_password}


def run_command(sudo_command):
    """
    ### Executes a given sudo command using the credentials retrieved from the configuration.
    
    **Args:**
    - **sudo_command (str):** The sudo command to be executed.
    
    **Returns:**
        None
        
    **Raises:**
    - **Exception:** If there is an error retrieving the sudo user credentials or executing the command.
    
    The function performs the following steps:
    1. Retrieves the sudo user credentials (username and password) from the configuration.
    2. Executes the given sudo command, passing the password to stdin.
    3. Captures and prints the stdout and stderr of the command execution.
    4. Prints a success message if the command is executed successfully, otherwise prints the error message.
    """
    
    user: dict = {}
    #username: str = ""
    password: str = ""
    
    try:
        user = returnSudoUser()
        # username = user["user"] # IMPLEMENTATION LEFT.
        password = user["password"]
    except Exception as error:
        print(f"Not able to get sudo user and password from 'configuration.py'\n{error}")
    
    try:
        # Run the command and pass the password to stdin
        result = subprocess.run(
            sudo_command, 
            input=password + '\n',   # Pass the password
            stdout=subprocess.PIPE,  # Capture stdout
            stderr=subprocess.PIPE,  # Capture stderr
            text=True                # Use text mode for strings
        )  
        
        # Check the result
        if result.returncode == 0:
            print(f"Command '{sudo_command}' correctly issued.")
            return result.stdout
        else:
            print(f"Failed to run Command '{sudo_command}' Error:", result.stderr)
            return None
    
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def find_proxbox_service_in_ls(service_name: str, folder_path: str):
    """
    ### Find the Proxbox service in the list of services.
    
    This function uses the `ls` command to list the services in the system and
    searches for the Proxbox service in the output.
    
    **Returns:**
    - **bool:** True if the Proxbox service is found, False otherwise.
    """
    
    output:str = str(run_command(['sudo', '-S', 'ls', '-l', folder_path]))
    
    for line in output.splitlines():
        if service_name in line:
            return True

    return False


def check_proxbox_service_file():
    """
    Checks for the existence of the `proxbox.service`' file in the systemd folder.
    If the file does not exist, attempts to download it from a specified GitHub repository.
   
    **Steps:**
    1. Checks if the `proxbox.service` file exists in the '/etc/systemd/system' directory.
    2. If the file is not found, changes the directory to '/etc/systemd/system'.
    3. Attempts to download the `proxbox.service` file from the GitHub repository.
    4. Rechecks if the `proxbox.service` file exists after the download attempt.
    
    **Returns:**
    - **bool:** True if the `proxbox.service` file is found or successfully downloaded, False otherwise.
    """
    
    branch: str = 'develop'
    systemd_folder: str = '/etc/systemd/system'
    service_name: str = 'proxbox.service'
    github_url: str = f'https://raw.githubusercontent.com/netdevopsbr/netbox-proxbox/{branch}/contrib/{service_name}'
    
    file_exists: bool = False
    
    file_exists = find_proxbox_service_in_ls(service_name=service_name, folder_path=systemd_folder)
        
    if not file_exists:
        print("Proxbox service file not found.")
        
        try:
            run_command(['sudo', '-S', 'wget', '-P', systemd_folder, github_url])
            run_command(['sudo', '-S', 'systemctl', 'daemon-reload'])
            
        except Exception as error:
            print(f"Error getting proxbox.service file.\n   > {error}")
            return False

        file_exists = find_proxbox_service_in_ls(service_name=service_name, folder_path=systemd_folder)
        
        if file_exists:
            print("Proxbox service file found.")
            return True
    else:
        print("Proxbox service file found.")
        return True
    
    print(f"[ERROR] Proxbox service file not found and not able to get it from GitHub.\nURL to Download it: {github_url}")
    return False


def change_proxbox_service(desired_state: str):
    """
    ### Change the state of the Proxbox service.
    
    This function attempts to start, restart, or stop the Proxbox service
    based on the provided desired state. It uses system commands to manage
    the service.
    
    **Args:**
    - **desired_state (str):** The desired state of the Proxbox service. 
    It can be "start", "restart", or "stop".
    
    **Raises:**
    - **Exception:** If an error occurs while attempting to change the Proxbox service state.
    """
    
    if check_proxbox_service_file():
        print(f"Proxbox service file found. Try to change Service State to: {desired_state}")
        try:
            if desired_state == "start": 
                print("START PROXBOX")
                run_command(['sudo', '-S', 'systemctl', 'start', 'proxbox'])
                
            if desired_state == "restart":
                print("RESTART PROXBOX")
                run_command(['sudo', '-S', 'systemctl', 'restart', 'proxbox'])     
                
            if desired_state == "stop":
                print("STOP PROXBOX")
                run_command(['sudo', '-S', 'systemctl', 'stop', 'proxbox'])
            
        except Exception as error:
            print(f"Error occured trying to change Proxbox status.\n   > {error}")
    else:
        print("Proxbox service file not found. Not able to change Service State.")
        return False

        
class FixProxboxBackendView(View):
    """
    ### View to handle the fixing of the Proxbox backend service.
    
    **Attributes:**
    - **template_name (str):** The path to the HTML template for this view.
    
    **Methods:**
    - **get(request):** Handles GET requests to start the Proxbox service and redirect to the home page.
    If an error occurs while starting the service, it prints the error.
    """

    template_name = 'netbox_proxbox/fix-proxbox-backend.html'
    
    def get(self, request):
        try:
            check_proxbox_service_file()
            
            change_proxbox_service(desired_state="start")
           
        except Exception as error:
            print(error)

        return redirect('plugins:netbox_proxbox:home')


class StopProxboxBackendView(View):
    """
    ### StopProxboxBackendView handles the stopping of the Proxbox backend service.
    
    **Methods:**
    - **get(request):** Handles GET requests to stop the Proxbox service. Redirects to the home page of the netbox_proxbox plugin.
    - request: The HTTP request object.
    
    **Raises:**
    - **Exception:** If an error occurs while attempting to stop the Proxbox service.
    """
    
    def get(self, request):
        try:
           change_proxbox_service(desired_state="stop")
            
        except Exception as error:
            print(error)
            
        return redirect('plugins:netbox_proxbox:home')

        
class RestartProxboxBackendView(View):
    """
    ### RestartProxboxBackendView is a Django view that handles the restart of the Proxbox backend service.
   
    **Methods:**
    - **get(request):** Handles GET requests to restart the Proxbox service. It calls the change_proxbox_service function
    with the desired state set to "restart". If an exception occurs, it prints the error and redirects
    to the home page of the netbox_proxbox plugin.
    """
    
    def get(self, request):
        try:
           change_proxbox_service(desired_state="restart")
            
        except Exception as error:
            print(error)
            
        return redirect('plugins:netbox_proxbox:home')


class StatusProxboxBackendView(View):
    """
    ### A Django view to display the status of the Proxbox backend service.
    
    **Attributes:**
    - **template_name (str):** The template to render the status page.
    
    **Methods:**
    - **get(request):** Handles GET requests to retrieve and display the status of the Proxbox service.
    Executes a system command to get the status of the Proxbox service using `systemctl`.
    Parses the output and formats it for display in the template.
    Handles exceptions and errors that may occur during the command execution.
    Returns the rendered template with the status information.
    """
    
    
    template_name = "netbox_proxbox/proxbox-backend-status.html"
    
    def get(self, request):
            
        output: list = []
        status_proxbox_process: str = ""
        
        try:
            print("CONSOLE STATUS")
            status_proxbox_process = subprocess.check_output(
                ['sudo','systemctl','status','proxbox'],
                stderr=subprocess.STDOUT,
                text=True
            )
            
            print("\n\nstatus_proxbox_process", status_proxbox_process )
            output: list = status_proxbox_process.splitlines()
            
        except subprocess.CalledProcessError as e:
            # Handle the case where the command fails
            print(f"Command failed with return code {e.returncode}")
            print("Output (STDOUT + STDERR):", e.output)
            
            output: list = str(e.output).splitlines()
                        
        except Exception as error:
            print(error)
        
        if output and (len(output) > 0):
            output[0] = f"<h2>{output[0]}</h2>"
            
            loaded, loaded_value = str(output[1]).split("Loaded: ")
            output[1] = f"<strong>Loaded: <span class='badge text-bg-grey'>{loaded_value}</span></strong>"
            
            active, active_status = str(output[2]).split(": ")
            
            if "active" in active_status or "running" in active_status:
                output[2] = f"<strong>{active} Status: <span class='badge text-bg-green'>{active_status}</span>"
            if "activating" in active_status:
                output[2] = f"<strong>{active} Status: <span class='badge text-bg-yellow'>{active_status}</span>"
            if "dead" in active_status:
                output[2] = f"<strong>{active} Status: <span class='badge text-bg-red'>{active_status}</span>"
            
            docs, docs_link = str(output[3]).split(": ")
            
            output[3] = f"<strong>{docs}: <a target='_blank' href='{docs_link}'>{docs_link}</a></strong>"

            if "Main PID" in output[4]:
                main_pid, main_pid_value = str(output[4]).split(": ")
                output[4] = f"<strong>{main_pid}: <span class='badge text-bg-grey'>{main_pid_value}</span></strong>"
            
            if "Tasks" in output[5]:
                tasks, tasks_value = str(output[5]).split("Tasks: ")
                output[5] = f"Tasks: <span class='badge text-bg-grey'>{tasks_value}</span>"
                
            if "Memory" in output[6]:
                memory, memory_value = str(output[6]).split("Memory: ")
                output[6] = f"Memory: <span class='badge text-bg-grey'>{memory_value}</span>"
            
            if "CPU" in output[7]:
                cpu, cpu_value = str(output[7]).split("CPU: ")
                output[7] = f"Memory: <span class='badge text-bg-grey'>{cpu_value}</span>"
                
            if "CGroup" in output[8]:
                cgroup, cgroup_value = str(output[8]).split("CGroup: ")
                output[8] = f"CGroup: <span class='badge text-bg-grey'>{cgroup_value}</span>"
            
            
        return render(
            request,
            self.template_name,
            {
                "message": output
            }
        )