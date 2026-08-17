"""Every registered plugin list view must actually render on the running NetBox.

This module exists because of a defect that passed the entire test suite and
would still have 500'd in production on NetBox 4.7.

NetBox 4.6 accepted a legacy ``actions = {"add": {"add"}, ...}`` mapping on list
views, converted it internally, and emitted a ``FutureWarning`` naming 4.7 as
the removal release. NetBox 4.7 removed the conversion, so
``ActionsMixin.get_permitted_actions()`` iterates ``self.actions`` and reads
``permissions_required`` off each element — a dict yields its string keys and
the view raises ``AttributeError: 'str' object has no attribute
'permissions_required'`` on every render.

Sixteen declarations across eleven modules were affected. Nothing caught it:
``test_detail_view_templates_django.py`` renders **detail** views, and these are
**list** views. An *empty* dict also happens to survive (iterating it yields
nothing), so the read-only lists kept working and the failure signature was
uneven.

The lesson generalises past that one API: a list view is a large integration
surface — table, filterset, actions, template, permissions — and the only test
that covers all of it at once is rendering it. So this walks NetBox's populated
runtime registry rather than a hand-maintained list, and GETs every plugin list
view. A newly added list view is covered automatically; a NetBox release that
changes any part of that contract fails here rather than in production.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = REPO_ROOT.parent / "netbox" / "netbox"

for candidate in (REPO_ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

try:
    import django
except ModuleNotFoundError:
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - depends on external test services
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client, TestCase  # noqa: E402
from django.urls import NoReverseMatch, reverse  # noqa: E402
from django.utils.module_loading import import_string  # noqa: E402

from netbox.registry import registry  # noqa: E402
from netbox.views.generic import ObjectListView  # noqa: E402

_PLUGIN_MODULE_PREFIX = "netbox_proxbox"

#: Guards against the registry walk silently finding nothing — a broken import
#: or a registry shape change would otherwise turn this whole module into a
#: vacuous pass. Deliberately a floor, not an equality, so adding a list view
#: does not fail the suite.
_MINIMUM_EXPECTED_LIST_VIEWS = 30


def _registered_plugin_list_views() -> tuple[tuple[str, type[ObjectListView]], ...]:
    """Every plugin ObjectListView in NetBox's populated runtime registry."""
    importlib.import_module("netbox_proxbox.urls")

    found: list[tuple[str, type[ObjectListView]]] = []
    for app_label, model_views in registry["views"].items():
        for model_name, view_configs in model_views.items():
            for config in view_configs:
                view_class = config["view"]
                if isinstance(view_class, str):
                    view_class = import_string(view_class)
                if not isinstance(view_class, type) or not issubclass(
                    view_class, ObjectListView
                ):
                    continue
                if not view_class.__module__.startswith(_PLUGIN_MODULE_PREFIX):
                    continue
                view_name = config.get("name") or "list"
                found.append((f"{app_label}:{model_name}_{view_name}", view_class))

    found.sort(key=lambda item: item[0])
    return tuple(found)


class PluginListViewRenderTest(TestCase):
    """GET every registered plugin list view and require a non-error response."""

    @classmethod
    def setUpTestData(cls) -> None:
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(
            username="list-view-render-probe",
            password="probe",  # noqa: S106 — throwaway test credential
            is_superuser=True,
        )

    def setUp(self) -> None:
        self.client = Client()
        self.client.force_login(self.user)

    def test_the_registry_walk_finds_the_list_views(self) -> None:
        """A vacuous pass is the failure mode this module must not have."""
        registrations = _registered_plugin_list_views()
        assert len(registrations) >= _MINIMUM_EXPECTED_LIST_VIEWS, (
            f"expected at least {_MINIMUM_EXPECTED_LIST_VIEWS} plugin list views, "
            f"found {len(registrations)} — the registry walk is probably broken, "
            f"which would make every assertion below vacuous"
        )

    def test_every_registered_list_view_renders(self) -> None:
        registrations = _registered_plugin_list_views()
        failures: list[str] = []
        rendered = 0

        for identifier, _view_class in registrations:
            app_label, view_name = identifier.split(":", 1)
            try:
                url = reverse(f"plugins:{app_label}:{view_name}")
            except NoReverseMatch:
                # Some list views are reachable only as an object tab; those are
                # covered by the detail-view suite. Not reversible standalone is
                # not a defect.
                continue

            with self.subTest(view=identifier, url=url):
                response = self.client.get(url)
                rendered += 1
                if response.status_code >= 400:
                    failures.append(
                        f"{identifier} ({url}) -> HTTP {response.status_code}"
                    )
                self.assertLess(
                    response.status_code,
                    400,
                    f"{identifier} at {url} returned HTTP {response.status_code}. "
                    f"A list view is a whole integration surface — table, "
                    f"filterset, actions, template, permissions — so this is "
                    f"usually a NetBox API contract that moved.",
                )

        assert rendered >= _MINIMUM_EXPECTED_LIST_VIEWS, (
            f"only {rendered} list views were actually requested; the rest failed "
            f"to reverse, so this test proved almost nothing"
        )
        assert not failures, f"list views returned error responses: {failures}"
