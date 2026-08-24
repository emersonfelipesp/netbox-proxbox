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

**There is deliberately only one matcher.** An earlier design also published a
regex fragment so a marker could be found *inside* a larger string, which meant
maintaining two spellings of the same idea -- and they disagreed: the fragment
allowed at most one separator between compound words while :func:`normalize_key`
strips a run of any length, so ``api__key`` was a sensitive key that no raw-text
matcher recognised. Both consumers now capture a whole candidate identifier and
ask :func:`is_sensitive_key` about it, so there is one definition of what a
credential-bearing name looks like and nothing to keep in step.
"""

from __future__ import annotations

import re

__all__ = (
    "ASSIGNMENT_KEY_RE",
    "AUTH_SCHEMES",
    "SCHEME_PATTERN",
    "SENSITIVE_KEY_MARKERS",
    "is_sensitive_key",
    "redact_assignments",
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


# A candidate field name followed by its assignment separator. The *marker* is
# deliberately not part of this pattern: :func:`redact_assignments` captures a
# whole name and asks :func:`is_sensitive_key` about it.
#
# Searching for the marker inside the key is what made the previous design both
# wrong and slow. Slow, because every occurrence of ``token`` inside a long
# identifier run started a fresh scan to the end of it -- quadratic, and
# ``"token_aaaa" * 20000`` took ~34 s. Wrong, because the caps added to hide
# that cost silently dropped longer names, and because the marker fragment and
# :func:`normalize_key` disagreed about separators.
#
# The run is possessive, so a name that never reaches a separator fails at once
# instead of re-trying every length.
#
# A name may **not** span a space. Allowing even a few space-joined words looked
# like it would catch ``SSH Keys``, and instead did two bad things: it redacted
# the tail of ordinary prose (``token_version mismatch: expected 2 got 1``,
# where the key becomes "token_version mismatch"), and it produced candidates
# that overlapped the next real assignment and hid it. Nothing is lost against
# the previous design either -- its marker fragment could not cross a space for
# a single-word marker like ``sshkeys`` in prose. A key containing a space is
# still recognised where it actually occurs: as a *mapping* key, which
# :func:`normalize_key` folds before matching.
ASSIGNMENT_KEY_RE = re.compile(
    r"""(?ix)
    (?<![a-z0-9_\-])
    (?P<key>[a-z0-9_\-]++)
    (?P<quote_end>\\?['"]?)
    (?P<sep>\s*[:=]\s*)
    """
)


def redact_assignments(text, value_re, render):
    """Replace the value of every credential-named assignment in *text*.

    *value_re* matches a value at a given offset; *render* receives the matched
    value text and returns its replacement.

    The scan is a single left-to-right pass. A name that is not a credential is
    simply skipped, and scanning resumes immediately **after its separator** --
    not after its value. That matters twice over: it is what keeps the pass
    linear on input like ``a:a:a:...`` (where a value would otherwise swallow
    the rest of the string), and it is what lets an assignment nested inside a
    non-credential one still be found. A Pydantic error rendering
    ``input_value={'token': 'nbt_...'}`` is exactly that shape, and consuming
    the outer value hid the inner credential completely.
    """
    out: list[str] = []
    written = 0
    position = 0
    while True:
        match = ASSIGNMENT_KEY_RE.search(text, position)
        if match is None:
            break
        if not is_sensitive_key(match.group("key")):
            # Resume immediately after the separator, never after the value: a
            # value may itself contain an assignment, and consuming it hid the
            # credential in ``input_value={'token': 'nbt_...'}`` entirely. The
            # key holds no separator of its own, so nothing can be skipped past.
            position = match.end()
            continue
        value = value_re.match(text, match.end())
        if value is None:
            position = match.end()
            continue
        out.append(text[written : match.end()])
        out.append(render(value.group(0)))
        written = position = value.end()
    out.append(text[written:])
    return "".join(out)
