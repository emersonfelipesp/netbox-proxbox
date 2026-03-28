# Installing The Backend From Source

Use this path if you want to work on the backend itself rather than consume the published package.

## Clone And Install

```bash
cd /opt
git clone https://github.com/emersonfelipesp/proxbox-api.git
cd /opt/proxbox-api

python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Start

```bash
/opt/proxbox-api/venv/bin/uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800 --app-dir /opt/proxbox-api
```

## When To Use This

Prefer this workflow when:

- you need backend changes that are not yet packaged
- you are debugging backend behavior
- you want an editable development install
