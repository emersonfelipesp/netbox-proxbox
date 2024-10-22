import subprocess

from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy
# 'View' is a django subclass. Basic type of class-based views
from django.views import View
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from django.views.decorators.cache import never_cache

# Enables permissions for views using Django authentication system.
# PermissionRequiredMixin = will handle permission checks logic and will plug into the
# Netbox's existing authorization system.
from django.contrib.auth.mixins import PermissionRequiredMixin

from .icon_classes import icon_classes

import json

from netbox import configuration
from . import ProxboxConfig
    
import markdown
from . import github

import requests

class HomeView(View):
    """Homepage"""
    template_name = 'netbox_proxbox/home.html'

    # service incoming GET HTTP requests
    def get(self, request):
        """Get request."""
        
        plugin_configuration = configuration.PLUGINS_CONFIG
        default_config = ProxboxConfig.default_settings
        
        # print("plugin_configuration: ", plugin_configuration, "\n\n")
        # print("default_config: ", default_config)
        
        
        uvicorn_host = plugin_configuration["netbox_proxbox"]["fastapi"]["uvicorn_host"]
        uvicorn_port = plugin_configuration["netbox_proxbox"]["fastapi"]["uvicorn_port"]
        
        fastapi_endpoint = f"http://{uvicorn_host}:{uvicorn_port}"

        return render(
            request,
            self.template_name,
            {
                "configuration": plugin_configuration,
                "default_config": default_config,
                "configuration_json": json.dumps(plugin_configuration, indent=4),
                "default_config_json": json.dumps(default_config, indent=4)
            }
        )


class ContributingView(View):
    """Contributing"""
    template_name = 'netbox_proxbox/contributing.html'

    # service incoming GET HTTP requests
    def get(self, request):
        """Get request."""

        title = "Contributing to Proxbox Project"
        
        return render(
            request,
            self.template_name,
            {
                "html": github.get(filename = "CONTRIBUTING.md"),
                "title": title,
            }
        )


class CommunityView(View):
    """Community"""
    template_name = 'netbox_proxbox/community.html'

    # service incoming GET HTTP requests
    def get(self, request):
        """Get request."""

        title = "Join our Community!"
        
        return render(
            request,
            self.template_name,
            {
                "title": title,
            }
        )

def returnSudoUser():
    plugin_configuration = configuration.PLUGINS_CONFIG
    
    sudo_user: str = ""
    sudo_password: str = ""
    try:
        sudo_user = plugin_configuration["netbox_proxbox"]["fastapi"]["sudo"]["user"]
        sudo_password = plugin_configuration["netbox_proxbox"]["fastapi"]["sudo"]["password"]
        
    except Exception as error:
        print(error)
        
    return { "user": sudo_user, "password": sudo_password}


def run_command(sudo_command):
    
    user = returnSudoUser()
    username = user["user"]
    password = user["password"]
    
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
        else:
            print(f"Failed to run Command '{sudo_command}' Error:", result.stderr)
    
    except Exception as e:
        print(f"An error occurred: {e}")
    

class FixProxboxBackendView(View):
    """
    Try to fix Proxbox Backend by issuing OS commands.
    """
    template_name = 'netbox_proxbox/fix-proxbox-backend.html'
    
    def get(self, request):
       
        plugin_configuration = configuration.PLUGINS_CONFIG
        
        output: str = ""
        try:
            print("START PROXBOX")
            run_command(['sudo', '-S', 'systemctl', 'start', 'proxbox'])

            
        except subprocess.CalledProcessError as e:
            # Handle the case where the command fails
            print(f"Command failed with return code {e.returncode}")
            print("Output (STDOUT + STDERR):", e.output)
            return redirect('plugins:netbox_proxbox:home')
            
        except Exception as error:
            print(error)
            return redirect('plugins:netbox_proxbox:home')
            

        return redirect('plugins:netbox_proxbox:home')


class StopProxboxBackendView(View):
    "Stop Proxbox Backend by issuing OS commands"
    
    def get(self, request):
            
        output: str = ""
        
        try:
            print("STOP PROXBOX")
            run_command(['sudo', '-S', 'systemctl', 'stop', 'proxbox'])

                
        except subprocess.CalledProcessError as e:
            # Handle the case where the command fails
            print(f"Command failed with return code {e.returncode}")
            print("Output (STDOUT + STDERR):", e.output)
            
        except Exception as error:
            print(error)
            
        return redirect('plugins:netbox_proxbox:home')

        
class RestartProxboxBackendView(View):
    "Restart Proxbox Backend by issuing OS commands"
    
    def get(self, request):
            
        output: str = ""
        
        try:
            print("RESSTART PROXBOX")
            run_command(['sudo', '-S', 'systemctl', 'restart', 'proxbox'])
                
        except subprocess.CalledProcessError as e:
            # Handle the case where the command fails
            print(f"Command failed with return code {e.returncode}")
            print("Output (STDOUT + STDERR):", e.output)
            
        except Exception as error:
            print(error)
            
        return redirect('plugins:netbox_proxbox:home')  
    
class StatusProxboxBackendView(View):
    "Restart Proxbox Backend by issuing OS commands"
    
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
            
            """
            return render(
                request,
                self.template_name,
                {
                    "message": output,
                }
            )
            """
                        
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

    
def DiscussionsView(request):
    external_url = "https://github.com/orgs/netdevopsbr/discussions"
    return redirect(external_url)

def DiscordView(request):
    external_url = "https://discord.com/invite/9N3V4mpMXU"
    return redirect(external_url)

def TelegramView(request):
    external_url = "https://t.me/netboxbr"
    return redirect(external_url)