# Developer Guide

This guide covers development setup, testing, and release processes for Proxbox.

## Prerequisites

- Python 3.12+
- Git
- A running NetBox 4.5.x instance (for integration testing)
- Proxmox VE (optional, for full integration tests)

## Development Environment Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/netdevopsbr/netbox-proxbox.git
   cd netbox-proxbox
   ```

2. Create a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -e ".[dev,test,cli]"
   ```

   Or install from requirements files:

   ```bash
   pip install -r requirements.txt
   pip install -r requirements-docs.txt
   ```

## Running Tests

Run all tests with pytest:

```bash
pytest tests/
```

Run with coverage:

```bash
pytest tests/ --cov=netbox_proxbox --cov-report=html
```

## Code Quality

### Linting

Run ruff linter:

```bash
ruff check .
```

### Syntax Check

Verify Python syntax:

```bash
python -m compileall netbox_proxbox tests
```

### Pre-commit

Install pre-commit hooks:

```bash
pre-commit install
```

Run pre-commit checks manually:

```bash
pre-commit run --all-files
```

## Building Documentation

Install docs dependencies:

```bash
pip install -r requirements-docs.txt
```

Serve documentation locally:

```bash
mkdocs serve
```

Build static site:

```bash
mkdocs build
```

The built site is output to `./site/`.

## Running the Plugin Locally

For local development, you need:

1. A NetBox 4.5.x installation
2. The plugin installed in NetBox's virtual environment
3. The Proxbox API backend running

### Plugin Installation

```bash
cd /opt/netbox/netbox
source venv/bin/activate
pip install -e /path/to/netbox-proxbox

# Run migrations
python manage.py migrate netbox_proxbox

# Collect static files
python manage.py collectstatic --no-input

# Restart NetBox
sudo systemctl restart netbox
```

Enable the plugin in `netbox/netbox/configuration.py`:

```python
PLUGINS = ["netbox_proxbox"]
```

### Backend Installation

```bash
mkdir -p /opt/proxbox-api
cd /opt/proxbox-api
python3 -m venv venv
source venv/bin/activate
pip install proxbox-api
uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800
```

### RQ Worker

For scheduled sync jobs, start the RQ worker:

```bash
cd /opt/netbox/netbox
source venv/bin/activate
python3 manage.py rqworker
```

## Project Structure

```
netbox-proxbox/
├── netbox_proxbox/      # NetBox plugin package
│   ├── api/             # REST API endpoints
│   ├── forms/           # Django forms
│   ├── migrations/      # Database migrations
│   ├── models/          # Database models
│   ├── tables/          # Table definitions
│   ├── templates/       # HTML templates
│   ├── views/           # UI views
│   └── static/          # CSS, JS, images
├── proxbox_cli/         # CLI tool package
├── docs/                # MkDocs documentation
├── tests/               # Test suite
└── CONTRIBUTING.md     # Community guidelines
```

## CLAUDE.md Files

The project includes detailed architecture documentation:

- [CLAUDE.md](./CLAUDE.md) — Top-level architecture
- [netbox_proxbox/CLAUDE.md](./netbox_proxbox/CLAUDE.md) — Plugin internals
- [netbox_proxbox/models/CLAUDE.md](./netbox_proxbox/models/CLAUDE.md) — Data models
- [netbox_proxbox/api/CLAUDE.md](./netbox_proxbox/api/CLAUDE.md) — API layer
- [netbox_proxbox/views/CLAUDE.md](./netbox_proxbox/views/CLAUDE.md) — Views

## Versioning

The project uses semantic versioning. Version is defined in:

- `pyproject.toml` — `version` field
- `netbox_proxbox/__init__.py` — `ProxboxConfig.version`

## Release Process

1. Update version in `pyproject.toml` and `netbox_proxbox/__init__.py`
2. Update release notes in `docs/release-notes/`
3. Run tests and linting
4. Build and verify documentation
5. Create a git tag:

   ```bash
   git tag -a v0.0.x -m "Release v0.0.x"
   git push origin v0.0.x
   ```

6. Build and publish to PyPI:

   ```bash
   pip install build
   python -m build
   twine upload dist/*
   ```

## Additional Resources

- [CONTRIBUTING.md](./CONTRIBUTING.md) — Community guidelines
- [MkDocs documentation](https://proxbox.readthedocs.io/)
