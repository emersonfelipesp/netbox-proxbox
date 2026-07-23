"""Shared Django stand-ins for the test suite's ``backend_sync`` stub loaders.

Django is not installed in the test environment, so every module that gets
path-loaded runs against hand-built entries in ``sys.modules``.  Six independent
loaders path-load ``views/backend_sync.py`` — ``conftest.load_plugin_module()``,
``test_jobs.load_real_backend_sync()``, and ``_load_backend_sync_module()`` /
``backend_sync_module`` in ``test_multi_endpoint_scoping``,
``test_preflight_diagnosis``, ``test_backend_sync_placement``, and
``test_endpoint_enabled_guards`` — and each builds its own stub set from scratch.
``views/backend_sync.py`` imports ``DatabaseError`` and ``salted_hmac``, so every
one of them needs those two modules; this file is what keeps them from becoming
six divergent copies.

Each loader must install the pair **itself** rather than rely on a sibling's.
Some tests leak a partial ``django.db`` stub into ``sys.modules`` permanently
(``test_hardware_discovery_custom_fields_migration``), and a stub without
``DatabaseError`` fails as ``ImportError: cannot import name 'DatabaseError'
from 'django.db' (unknown location)`` in whichever unrelated test happens to run
next.  ``monkeypatch.setitem`` shadows the leaked entry for the duration of the
test, which is why ``install_django_stubs()`` is the normal entry point.

``salted_hmac`` in particular is implemented *faithfully* rather than stubbed to
a constant.  The code under test fingerprints credentials with it, and a
constant-returning stub would make every fingerprint compare equal — the exact
opposite of what the fingerprint exists to detect.

Only two dotted names are needed.  ``from django.db import DatabaseError`` and
``from django.utils.crypto import salted_hmac`` both hit ``sys.modules`` on the
**full** dotted name before any find-and-load runs, so neither a bare ``django``
entry nor a ``django.utils`` package is required.
"""

from __future__ import annotations

import hashlib
import hmac
import sys
import types

#: Stands in for ``settings.SECRET_KEY``.  Fixed so digests are reproducible
#: across runs and across every loader.
TEST_SECRET_KEY = b"netbox-proxbox-test-secret-key"


class DatabaseError(Exception):
    """Stand-in for ``django.db.DatabaseError`` (the base of ``ProgrammingError``)."""


def salted_hmac(key_salt, value, secret=None, *, algorithm="sha1"):
    """Reimplementation of ``django.utils.crypto.salted_hmac``.

    Same key derivation as Django's: hash ``key_salt + secret`` and use the
    digest as the HMAC key.  Equal inputs give equal digests, different inputs
    give different ones — which is the whole property the fingerprint tests rely
    on.
    """
    if secret is None:
        secret = TEST_SECRET_KEY
    if isinstance(key_salt, str):
        key_salt = key_salt.encode()
    if isinstance(secret, str):
        secret = secret.encode()
    if isinstance(value, str):
        value = value.encode()
    hasher = getattr(hashlib, algorithm)
    key = hasher(key_salt + secret).digest()
    return hmac.new(key, msg=value, digestmod=hasher)


def django_stub_modules(*, models_module=None) -> dict[str, types.ModuleType]:
    """Build the ``django.db`` / ``django.utils.crypto`` stub pair.

    ``models_module`` is attached as ``django.db.models`` when a loader has
    already built one, so ``django.db.models`` stays reachable as an attribute of
    its parent as well as through its own ``sys.modules`` entry.
    """
    django_db = types.ModuleType("django.db")
    django_db.DatabaseError = DatabaseError
    if models_module is not None:
        django_db.models = models_module

    django_utils_crypto = types.ModuleType("django.utils.crypto")
    django_utils_crypto.salted_hmac = salted_hmac

    return {
        "django.db": django_db,
        "django.utils.crypto": django_utils_crypto,
    }


def install_django_stubs(monkeypatch, *, models_module=None) -> None:
    """``monkeypatch.setitem`` the stub pair into ``sys.modules``.

    The normal entry point, for the ``monkeypatch``-based loaders of
    ``views/backend_sync.py``.  ``conftest.load_plugin_module()`` calls
    ``django_stub_modules()`` directly because it folds the pair into a larger
    stub dict it registers itself, and ``test_jobs.load_real_backend_sync()``
    writes ``sys.modules`` directly because it caches its module across tests and
    does its own save/restore.
    """
    for name, stub in django_stub_modules(models_module=models_module).items():
        monkeypatch.setitem(sys.modules, name, stub)
