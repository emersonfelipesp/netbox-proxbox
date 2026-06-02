"""NetBox-side bootstrap helpers for Proxbox supporting objects."""

from __future__ import annotations

BOOTSTRAP_ONLY_TAG_SLUG = "bootstrap-only"

PROXBOX_TAG_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "name": "Proxbox",
        "slug": "proxbox",
        "color": "4caf50",
        "description": (
            "Objects discovered and managed by Proxbox sync. Assign this tag to a "
            "pre-existing NetBox object (e.g. a Device for a physical hypervisor) to "
            "let Proxbox reuse it during sync instead of creating a duplicate."
        ),
    },
    {
        "name": "Bootstrap only",
        "slug": BOOTSTRAP_ONLY_TAG_SLUG,
        "color": "9e9e9e",
        "description": (
            "Objects created by Proxbox bootstrap-only sync mode; future syncs "
            "leave them untouched."
        ),
    },
)


def ensure_proxbox_tags() -> dict[str, object]:
    """Create the NetBox tags Proxbox sync relies on and return them by slug."""
    from extras.models import Tag

    tags: dict[str, object] = {}
    for definition in PROXBOX_TAG_DEFINITIONS:
        defaults = {
            "name": definition["name"],
            "color": definition["color"],
            "description": definition["description"],
        }
        tag, _created = Tag.objects.get_or_create(
            slug=definition["slug"],
            defaults=defaults,
        )
        tags[definition["slug"]] = tag
    return tags


def ensure_bootstrap_only_tag() -> object:
    """Return the bootstrap-only tag, creating it alongside Proxbox tags."""
    return ensure_proxbox_tags()[BOOTSTRAP_ONLY_TAG_SLUG]
