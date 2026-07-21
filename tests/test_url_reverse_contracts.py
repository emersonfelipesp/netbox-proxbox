"""Source contracts binding ``get_absolute_url()`` to actually-mounted URL names.

netbox-proxbox issue #618: opening a core ``virtualization.Cluster`` detail page
rendered

    An error occurred when loading content from plugin netbox_proxbox:
    NoReverseMatch("Reverse for 'proxmoxcluster' not found. ...")

``ProxmoxCluster.get_absolute_url()`` reverses
``plugins:netbox_proxbox:proxmoxcluster``, but ``urls.py`` never mounted
``get_model_urls()`` for that model, so the name did not exist. The plugin's
Sync-Now template extension calls ``get_absolute_url()`` on every core Cluster
(and Device) detail page, which is what surfaced the crash to the reporter.

These are pure source contracts -- the plugin test suite runs against a stubbed
Django, so the URLconf cannot be resolved for real here. They parse ``urls.py``
and the model modules and assert the two sets agree, which is enough to catch
the whole class of defect (a model reversing a name nobody mounted).
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "netbox_proxbox"
URLS_PY = PLUGIN_ROOT / "urls.py"
MODELS_DIR = PLUGIN_ROOT / "models"

# Models that deliberately have no detail page and whose get_absolute_url() is
# expected to degrade to "" via the NoReverseMatch guard.
#
# * PBSEndpoint     -- interim state, full scaffolding tracked separately (#449).
# * Firecracker*    -- API/automation-managed for NMS Cloud; no NetBox UI surface
#                      (no tables, no templates, no registered views).
# Anything NOT listed here must have its reversed name mounted in urls.py.
UNMOUNTED_BY_DESIGN = frozenset(
    {
        "pbsendpoint",
        "firecrackerhost",
        "firecrackerhostpool",
        "firecrackerimagetemplate",
        "firecrackermicrovm",
    }
)


def _mounted_url_names() -> set[str]:
    """Names reachable under the ``plugins:netbox_proxbox:`` namespace."""
    source = URLS_PY.read_text()
    names: set[str] = set()

    # path(..., name="foo")
    names.update(re.findall(r'\bname\s*=\s*["\'](\w+)["\']', source))

    # include(get_model_urls("netbox_proxbox", "foo")) registers the bare model
    # name for the detail view plus "<model>_<action>" for named actions.
    names.update(
        re.findall(
            r'get_model_urls\(\s*["\']netbox_proxbox["\']\s*,\s*["\'](\w+)["\']',
            source,
        )
    )
    return names


def _reversed_names_by_model_module() -> dict[str, list[tuple[str, int]]]:
    """Every ``plugins:netbox_proxbox:<name>`` reversed from ``models/``."""
    found: dict[str, list[tuple[str, int]]] = {}
    for path in sorted(MODELS_DIR.rglob("*.py")):
        source = path.read_text()
        for match in re.finditer(
            r'reverse\(\s*["\']plugins:netbox_proxbox:(\w+)["\']', source
        ):
            line = source[: match.start()].count("\n") + 1
            found.setdefault(match.group(1), []).append(
                (str(path.relative_to(REPO_ROOT)), line)
            )
    return found


def test_every_model_reverse_target_is_mounted():
    """A model must not reverse a URL name that ``urls.py`` never mounts."""
    mounted = _mounted_url_names()
    reversed_names = _reversed_names_by_model_module()

    assert reversed_names, "expected models/ to reverse at least one plugin URL name"

    unmounted = {
        name: sites
        for name, sites in reversed_names.items()
        if name not in mounted
        and name not in UNMOUNTED_BY_DESIGN
        # "<model>_<action>" names come from get_model_urls on the base model.
        and not any(name.startswith(f"{base}_") for base in mounted)
    }

    assert not unmounted, (
        "these models reverse URL names that urls.py never mounts, which raises "
        "NoReverseMatch (or silently yields an empty href behind the guard) on "
        "every page that renders them -- mount them with "
        "include(get_model_urls(...)) or add them to UNMOUNTED_BY_DESIGN:\n"
        + "\n".join(f"  {name}: {sites}" for name, sites in sorted(unmounted.items()))
    )


@pytest.mark.parametrize("model_name", ["proxmoxcluster", "proxmoxnode"])
def test_cluster_and_node_detail_routes_are_mounted(model_name):
    """Regression for #618: these two must stay mounted.

    They back the Sync Now button on core Cluster/Device detail pages, whose
    action URL is built as ``f"{obj.get_absolute_url()}proxbox-sync-now/"``.
    """
    assert model_name in _mounted_url_names(), (
        f"{model_name} detail route is not mounted in urls.py; "
        "ProxmoxCluster/ProxmoxNode.get_absolute_url() would break again"
    )


@pytest.mark.parametrize(
    ("template_name", "list_route"),
    [("proxmoxcluster.html", "clusters"), ("proxmoxnode.html", "nodes")],
)
def test_detail_templates_override_the_list_breadcrumb(template_name, list_route):
    """A template extending ``generic/object.html`` needs a ``<model>_list`` route.

    NetBox's ``generic/object.html`` breadcrumb block renders
    ``{% action_url object 'list' %}`` with **no** ``as`` clause, and
    ``ActionURLNode.render()`` only swallows ``NoReverseMatch`` when an ``as``
    variable is supplied — otherwise it re-raises. ProxmoxCluster and ProxmoxNode
    have no ``<model>_list`` route (their list pages are the bespoke ``clusters``
    and ``nodes`` views), so inheriting that breadcrumb would 500 the detail page
    with the very ``NoReverseMatch`` failure issue #618 reported — just moved
    from the linking page to the linked one.

    Both templates must therefore override ``breadcrumbs`` and point at the real
    list page.
    """
    template = (
        PLUGIN_ROOT / "templates" / "netbox_proxbox" / template_name
    ).read_text()

    assert "{% extends 'generic/object.html' %}" in template, (
        f"{template_name} is expected to extend generic/object.html"
    )
    assert "{% block breadcrumbs %}" in template, (
        f"{template_name} must override the breadcrumbs block; the inherited one "
        "reverses a <model>_list route this model does not have and will raise "
        "NoReverseMatch when the page is rendered"
    )
    assert f"plugins:netbox_proxbox:{list_route}" in template, (
        f"{template_name}'s breadcrumb must link to the existing "
        f"'{list_route}' list page"
    )


def test_sync_now_action_views_are_imported_so_they_register():
    """``sync_now`` views only register if something imports them eagerly.

    ``views/sync_now/__init__.py`` exposes them through a lazy ``__getattr__``,
    so their ``@register_model_view`` decorators never ran and the cluster,
    node, and storage Sync Now actions resolved to no URL at all. ``urls.py``
    must import the modules for that decorator side effect, and must do so
    before ``get_model_urls()`` is evaluated.
    """
    source = URLS_PY.read_text()
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == (
            "netbox_proxbox.views.sync_now"
        ):
            imported.update(alias.name for alias in node.names)

    for module in ("cluster", "node", "storage"):
        assert module in imported, (
            f"urls.py must import netbox_proxbox.views.sync_now.{module} so its "
            "@register_model_view decorator executes; otherwise the Sync Now "
            "action for that model registers no URL"
        )
