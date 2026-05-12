"""Shared django/management stubs for tests under tests/management/.

The plugin's management commands import ``from django.core.management.base
import BaseCommand, CommandError`` at module load. Tests here do not
bootstrap Django, so we install minimal stubs at conftest import time —
before pytest collects the test files — so the imports resolve to
lightweight Python classes.
"""

from __future__ import annotations

import sys
import types


def _install_django_management_stubs() -> None:
    if "django.core.management.base" in sys.modules:
        return

    django_module = sys.modules.setdefault("django", types.ModuleType("django"))
    django_core = sys.modules.setdefault(
        "django.core", types.ModuleType("django.core")
    )
    django_core_management = sys.modules.setdefault(
        "django.core.management", types.ModuleType("django.core.management")
    )

    base_mod = types.ModuleType("django.core.management.base")

    class CommandError(Exception):
        """Stub mirroring django.core.management.base.CommandError."""

    class BaseCommand:
        """Stub mirroring django.core.management.base.BaseCommand."""

        help: str = ""

        def add_arguments(self, parser) -> None:  # pragma: no cover - overridden
            return None

        def handle(self, *args, **kwargs) -> None:  # pragma: no cover - overridden
            raise NotImplementedError

    base_mod.BaseCommand = BaseCommand
    base_mod.CommandError = CommandError

    sys.modules["django.core.management.base"] = base_mod

    django_core_management.base = base_mod
    django_core.management = django_core_management
    django_module.core = django_core

    # django.contrib.auth — populated with a placeholder get_user_model so
    # monkeypatch.setattr("django.contrib.auth.get_user_model", ...) can resolve
    # the dotted path. Tests override get_user_model per case.
    django_contrib = sys.modules.setdefault(
        "django.contrib", types.ModuleType("django.contrib")
    )
    django_auth = sys.modules.setdefault(
        "django.contrib.auth", types.ModuleType("django.contrib.auth")
    )

    def _placeholder_get_user_model():  # pragma: no cover - overridden per test
        raise RuntimeError("django.contrib.auth.get_user_model not stubbed for this test")

    if not hasattr(django_auth, "get_user_model"):
        django_auth.get_user_model = _placeholder_get_user_model

    django_contrib.auth = django_auth
    django_module.contrib = django_contrib


_install_django_management_stubs()
