"""Tasks for use with Invoke.

(c) 2020 Network To Code
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
  http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
from invoke import task

PYTHON_VER = os.getenv("PYTHON_VER", "3.8")
NETBOX_VER = os.getenv("NETBOX_VER", "master")

# Name of the docker image/container
NAME = os.getenv("IMAGE_NAME", "nm-netbox-plugin-proxbox")
PWD = os.getcwd()

COMPOSE_FILE = "development/docker-compose.yml"
BUILD_NAME = "netbox_proxbox"


# ------------------------------------------------------------------------------
# BUILD
# ------------------------------------------------------------------------------
@task
def build(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Build all docker images.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    context.run(
        f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} build --build-arg netbox_ver={netbox_ver} --build-arg python_ver={python_ver}",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
    )


# ------------------------------------------------------------------------------
# START / STOP / DEBUG
# ------------------------------------------------------------------------------
@task
def debug(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Start NetBox and its dependencies in debug mode.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    print("Starting Netbox .. ")
    context.run(
        f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} up",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
    )


@task
def start(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Start NetBox and its dependencies in detached mode.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    print("Starting Netbox in detached mode.. ")
    context.run(
        f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} up -d",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
    )


@task
def stop(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Stop NetBox and its dependencies.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    print("Stopping Netbox .. ")
    context.run(
        f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} down",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
    )


@task
def destroy(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Destroy all containers and volumes.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    context.run(
        f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} down",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
    )
    context.run(
        f"docker volume rm -f {BUILD_NAME}_pgdata_netbox_proxbox",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
    )


# ------------------------------------------------------------------------------
# ACTIONS
# ------------------------------------------------------------------------------
@task
def nbshell(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Launch a nbshell session.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    context.run(
        f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} run netbox python manage.py nbshell",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
        pty=True,
    )


@task
def cli(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Launch a bash shell inside the running NetBox container.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    context.run(
        f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} run netbox bash",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
        pty=True,
    )


@task
def create_user(context, user="admin", netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Create a new user in django (default: admin), will prompt for password.

    Args:
        context (obj): Used to run specific commands
        user (str): name of the superuser to create
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    context.run(
        f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} run netbox python manage.py createsuperuser --username {user}",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
        pty=True,
    )


@task
def makemigrations(context, app_name=BUILD_NAME, name="", netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Run Make Migration in Django.

    Args:
        context (obj): Used to run specific commands
        app_name (str): Name of the app for which to run migration
        name (str): Name of the migration to be created
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    context.run(
        f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} up -d postgres",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
    )

    if name:
        context.run(
            f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} run netbox python manage.py makemigrations {app_name} --name {name}",
            env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
        )
    else:
        context.run(
            f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} run netbox python manage.py makemigrations {app_name}",
            env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
        )

    context.run(
        f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} down",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
    )


# ------------------------------------------------------------------------------
# TESTS / LINTING
# ------------------------------------------------------------------------------
@task
def unittest(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Run Django unit tests for the plugin.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    docker = f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} run netbox"
    context.run(
        f'{docker} sh -c "python manage.py test netbox_proxbox"',
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
        pty=True,
    )


@task
def pylint(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Run pylint code analysis.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    docker = f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} run netbox"
    # We exclude the /migrations/ directory since it is autogenerated code
    context.run(
        f"{docker} sh -c \"cd /source && find . -name '*.py' -not -path '*/migrations/*' | "
        'PYTHONPATH=/opt/netbox/netbox DJANGO_SETTINGS_MODULE=netbox.settings xargs pylint"',
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
        pty=True,
    )


@task
def black(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Run black to check that Python files adhere to its style standards.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    docker = f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} run netbox"
    context.run(
        f'{docker} sh -c "cd /source && black --check --diff ."',
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
        pty=True,
    )


@task
def pydocstyle(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Run pydocstyle to validate docstring formatting adheres to NTC defined standards.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    docker = f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} run netbox"
    # We exclude the /migrations/ directory since it is autogenerated code
    context.run(
        f"{docker} sh -c \"cd /source && find . -name '*.py' -not -path '*/migrations/*' | xargs pydocstyle\"",
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
        pty=True,
    )


@task
def bandit(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Run bandit to validate basic static code security analysis.

    Args:
        context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    docker = f"docker-compose -f {COMPOSE_FILE} -p {BUILD_NAME} run netbox"
    context.run(
        f'{docker} sh -c "cd /source && bandit --configfile .bandit.yml --recursive ./"',
        env={"NETBOX_VER": netbox_ver, "PYTHON_VER": python_ver},
        pty=True,
    )


@task
def tests(context, netbox_ver=NETBOX_VER, python_ver=PYTHON_VER):
    """Run all tests for this plugin.

    Args:
         context (obj): Used to run specific commands
        netbox_ver (str): NetBox version to use to build the container
        python_ver (str): Will use the Python version docker image to build from
    """
    # Sorted loosely from fastest to slowest
    print("Running black...")
    black(context, netbox_ver=netbox_ver, python_ver=python_ver)
    print("Running bandit...")
    bandit(context, netbox_ver=netbox_ver, python_ver=python_ver)
    print("Running pydocstyle...")
    pydocstyle(context, netbox_ver=netbox_ver, python_ver=python_ver)
    print("Running pylint...")
    pylint(context, netbox_ver=netbox_ver, python_ver=python_ver)
    print("Running unit tests...")
    unittest(context, netbox_ver=netbox_ver, python_ver=python_ver)
    # print("Running yamllint...")
    # yamllint(context, NAME, python_ver)

    print("All tests have passed!")
