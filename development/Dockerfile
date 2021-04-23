ARG python_ver=3.8.5
FROM python:${python_ver}

ARG netbox_ver=master
ENV PYTHONUNBUFFERED 1

RUN mkdir -p /opt

RUN pip install --upgrade pip\
  && pip install poetry

# -------------------------------------------------------------------------------------
# Install NetBox
# -------------------------------------------------------------------------------------
# Remove redis==3.4.1 from the requirements.txt file as a workaround to #4910
# https://github.com/netbox-community/netbox/issues/4910, required for version 2.8.8 and earlier
#
RUN git clone --single-branch --branch ${netbox_ver} https://github.com/netbox-community/netbox.git /opt/netbox/ && \
    cd /opt/netbox/ && \
    sed -i '/^redis\=\=/d' /opt/netbox/requirements.txt && \
    pip install -r /opt/netbox/requirements.txt

# Make the django-debug-toolbar always visible when DEBUG is enabled,
# except when we're running Django unit-tests.
RUN echo "import sys" >> /opt/netbox/netbox/netbox/settings.py && \
    echo "TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'" >> /opt/netbox/netbox/netbox/settings.py && \
    echo "DEBUG_TOOLBAR_CONFIG = {'SHOW_TOOLBAR_CALLBACK': lambda _: DEBUG and not TESTING }" >> /opt/netbox/netbox/netbox/settings.py

# Work around https://github.com/rq/django-rq/issues/421
RUN pip install django-rq==2.3.2

# -------------------------------------------------------------------------------------
# Install Netbox Plugin
# -------------------------------------------------------------------------------------
RUN mkdir -p /source
WORKDIR /source
COPY . /source

RUN pip install -r /source/requirements.txt

RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi

WORKDIR /opt/netbox/netbox/
