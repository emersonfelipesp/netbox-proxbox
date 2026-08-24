"""Shared vocabulary for recognising credential-bearing fields.

Two modules redact credentials, for two different audiences:

* :mod:`netbox_proxbox.views.error_utils` scrubs backend payloads on their way
  into the **job log**, where they are rendered in the NetBox UI.
* :mod:`netbox_proxbox.anonymize` scrubs a failed job's metadata, error and logs
  on their way into a **public issue tracker**.

They produce deliberately different output -- ``error_utils`` walks structured
payloads and replaces values with ``[redacted]``; ``anonymize`` rewrites free
text and assigns stable placeholders -- but they have to agree on *what counts
as a credential*. Keeping that judgement in two places is how a security rule
drifts quietly, and it did: an enumerated key list in ``anonymize`` missed
``token_value``, ``token_secret`` and ``X-Proxbox-API-Key`` while ``error_utils``
caught them, because only the latter matched by marker.

This module owns that judgement. It is deliberately dependency-free -- ``re``
and nothing else -- because ``anonymize`` must remain importable without Django
(``tests/test_bug_report.py`` exec-loads its consumer with only ``core.choices``
stubbed), and ``error_utils`` is reached through a package whose ``__init__``
does need Django.

**Both representations are generated from one list.** A marker is needed twice,
in two shapes: normalised (``apikey``) for comparing against a separator-folded
mapping key, and as a regex fragment (``api[_\\-\\s]?key``) for finding an
assignment in raw text. Writing those out separately is the same drift problem
one level down, so :data:`SENSITIVE_KEY_MARKERS` and
:data:`KEY_MARKER_PATTERN` are both derived from :data:`_MARKER_WORDS`.
"""

from __future__ import annotations

import re

__all__ = (
    "AUTH_SCHEMES",
    "KEY_MARKER_PATTERN",
    "MAX_SEPARATOR_RUN",
    "SCHEME_PATTERN",
    "SENSITIVE_KEY_MARKERS",
    "is_sensitive_key",
    "normalize_key",
)

# Each entry is a marker split into the words a field name may separate with
# ``-``, ``_`` or a space. Single-word entries have no separator to allow for.
#
# The list is the union of what both consumers previously knew, so adding it
# here makes each of them at least as strict as the other was. Several entries
# are this plugin's own field and setting names -- ``token_value`` and
# ``token_secret`` on the endpoint models, ``encryption_key`` on the plugin
# settings, ``sshkeys`` on the cloud-init model -- which is exactly the class an
# enumerated per-module list kept missing.
_MARKER_WORDS: tuple[tuple[str, ...], ...] = (
    ("authorization",),
    ("credential",),
    ("passphrase",),
    ("password",),
    ("passwd",),
    ("session",),
    ("sshkeys",),
    ("secret",),
    ("cookie",),
    ("ticket",),
    ("token",),
    ("auth",),
    ("pwd",),
    ("api", "key"),
    ("private", "key"),
    ("public", "key"),
    ("encryption", "key"),
    ("secret", "key"),
    ("signing", "key"),
    ("host", "key"),
    ("ssh", "key"),
)

# Separator-free forms, for matching against a normalised key.
SENSITIVE_KEY_MARKERS: tuple[str, ...] = tuple(
    "".join(words) for words in _MARKER_WORDS
)

# Regex alternation for matching a marker in raw text, where the separators are
# still present. Longest first so ``authorization`` is preferred over ``auth``
# and the captured key reads naturally in the output.
# One separator language, used by both representations. ``normalize_key``
# strips a run of *any* length, so the regex has to accept a run too -- an
# earlier version allowed at most one character, which made ``api__key`` a
# sensitive *key* that the raw-text matchers ignored, and the secret behind it
# reached the public issue body. The run is bounded because an unbounded one in
# front of a required literal is the quadratic shape documented in
# ``anonymize.py``; a field name with more than this many consecutive
# separators between words is still caught as a mapping key, just not in prose.
MAX_SEPARATOR_RUN = 8
_SEPARATOR_RUN_PATTERN = r"[_\-\s]{0,%d}" % MAX_SEPARATOR_RUN

KEY_MARKER_PATTERN: str = "|".join(
    _SEPARATOR_RUN_PATTERN.join(re.escape(word) for word in words)
    for words in sorted(_MARKER_WORDS, key=lambda w: -len("".join(w)))
)

# HTTP authentication schemes whose credential follows the scheme keyword.
# ``token`` matters specifically: it is the scheme NetBox's own API uses, and
# omitting it meant ``Authorization: Token nbt_...`` redacted the keyword and
# published the credential behind it.
AUTH_SCHEMES: tuple[str, ...] = (
    "bearer",
    "basic",
    "token",
    "digest",
    "negotiate",
    "apikey",
)

SCHEME_PATTERN: str = "|".join(AUTH_SCHEMES)

_SEPARATOR_RE = re.compile(r"[-_\s]+")


def normalize_key(key: str) -> str:
    """Fold a key to a separator-free lowercase form for marker matching.

    ``x-proxbox-api-key``, ``api_key`` and ``ApiKey`` are one field wearing three
    spellings; matching only the underscore form let the HTTP header spelling
    through unredacted.
    """
    return _SEPARATOR_RE.sub("", key.lower())


def is_sensitive_key(key: object) -> bool:
    """Return ``True`` when a mapping key names a credential-bearing field."""
    if not isinstance(key, str):
        return False
    normalized = normalize_key(key)
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)
