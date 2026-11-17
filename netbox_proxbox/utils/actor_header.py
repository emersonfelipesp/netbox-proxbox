"""Encode the audit actor name for the ``X-Proxbox-Actor`` request header."""

from __future__ import annotations

from urllib.parse import quote

__all__ = ("header_safe_actor",)

# Printable Latin-1 without "%". A raw value therefore never contains "%",
# and an encoded value always does, so the two forms cannot collide.
_RAW_SAFE = frozenset(
    chr(code) for code in (*range(0x20, 0x7F), *range(0xA0, 0x100)) if chr(code) != "%"
)


def header_safe_actor(actor: str) -> str:
    """Return ``actor`` in a form an HTTP header can carry without ambiguity.

    HTTP header values are Latin-1 and must not contain control characters.
    A name made only of printable Latin-1 characters other than ``%``, with no
    leading or trailing whitespace, is sent unchanged. Every other name is
    percent-encoded as UTF-8, which also escapes ``%`` itself. HTTP clients
    reject a header value that starts or ends with whitespace, including the
    non-breaking space. A receiver decodes a value exactly when it contains
    ``%``.
    """
    if actor == actor.strip() and all(character in _RAW_SAFE for character in actor):
        return actor
    return quote(actor, safe="")
