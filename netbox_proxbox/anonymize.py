"""Best-effort scrubbing of identifying data out of Proxbox bug reports.

A failed sync job's ``error`` string and ``log_entries`` routinely embed details
an operator should not publish to a public issue tracker: Proxmox node
hostnames and FQDNs, management IP addresses, API URLs, ``user@pam`` realm
principals, ``PVEAPIToken`` values, and ``Authorization`` headers. The bug
report feature exists to get that text *out* of the NetBox instance and into
the public issue tracker, so scrubbing has to happen before the text is handed
to the operator -- not after.

Two properties drive the design:

* **Stable placeholders.** The same input value always maps to the same token
  (``<ip-1>``, ``<host-2>``) for the lifetime of one :class:`Anonymizer`, so a
  reader can still tell "the node that timed out is the same one that failed
  the storage check" without learning what it is called.
* **No Django.** ``tests/test_bug_report.py`` exec-loads
  :mod:`netbox_proxbox.bug_report` with only ``core.choices`` stubbed, so this
  module -- which that one imports -- must stay pure ``re`` + stdlib.

Scrubbing is deliberately **fail-closed**: an ambiguous match is redacted
rather than preserved. It is still best-effort, and the modal says so. In
particular, a bare single-label Proxmox node name (``pve-node-01``) appearing
in prose is indistinguishable from any other identifier and is only caught when
it appears in a URL or another positionally-identifiable slot.

Every quantifier that precedes a required literal is **bounded**. Log text is
remote-controlled, so an unbounded greedy class in front of an absent literal
is a denial-of-service vector, not a style question -- see ``_URL_RE`` and
``_FQDN_RE`` for the measurements.
"""

from __future__ import annotations

import re
from typing import Iterable

__all__ = (
    "Anonymizer",
    "anonymize_lines",
    "anonymize_text",
)

REDACTED = "<redacted>"

# Credential matching mirrors ``views/error_utils.py``'s redaction rather than
# inventing a second scheme: that module already learned these lessons against
# real backend payloads. It cannot simply be imported -- it pulls in Django, and
# this module must not (see the note above) -- so the shape is duplicated
# deliberately. Keep the two in step.
#
# Three properties matter, and an earlier exact-key/line-anchored version failed
# all three:
#
# * **The key is matched by marker, not by exact name.** ``token_value`` and
#   ``token_secret`` are real field names on this plugin's own models, and
#   ``X-Proxbox-API-Key`` is a real header; an enumerated key list missed every
#   one of them.
# * **Assignments are found anywhere in the text, in both ``:`` and ``=``
#   forms.** Anchoring the ``:`` form to the start of a line made it dead code
#   in practice: ``_format_log_lines`` prepends ``[timestamp] LEVEL `` before
#   anything is scrubbed, so a log message that *begins* with an
#   ``Authorization:`` header is never at column zero by the time it gets here.
#   That also means a passing test can prove nothing unless its fixture carries
#   the prefix a real log line has.
# * **A bare ``Bearer <jwt>`` is swept independently**, because a credential
#   quoted into prose has no key in front of it to match on.
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    # A key starts at an identifier boundary, never part-way through one. That
    # is what it means for something to be a field name, and it also collapses
    # the search: without it the leading run is retried at every character of a
    # long marker-bearing string, and ``"token_aaaa" * 20000`` cost seconds.
    (?<![a-z0-9_\-])
    # The trailing run is *possessive*. Its character class excludes ``:`` and
    # ``=``, so it can never need to give a character back for the separator to
    # match -- but a backtracking suffix multiplied against the prefix. The
    # leading run must stay backtracking: it has to be able to give ground for
    # the marker itself to match (``mytoken=x``).
    (?P<key>[a-z0-9_\-]{0,64}
        (?:token|password|passwd|pwd|secret|api[_\-\s]?key|private[_\-\s]?key
           |sshkeys|authorization|credential|cookie|ticket)
        [a-z0-9_\-]{0,64}+)
    (?P<quote_end>['"]?)
    (?P<sep>\s*[:=]\s*)
    # The scheme alternative must come first. ``Authorization: Bearer <jwt>``
    # otherwise matches with the value ``Bearer`` alone, which redacts the
    # *keyword* and leaves the token behind it in the clear -- and then hides it
    # from the bearer sweep below, which no longer sees a scheme to anchor on.
    (?P<value>(?:bearer|basic)\s+[^\s,;)}\]]{1,4096}
        |'[^']{0,4096}'|"[^"]{0,4096}"|[^\s,;&)}\]]{1,4096})
    """
)

# ``Bearer <jwt>`` with no credential-named key in front of it -- a request
# header quoted into a message, say. The assignment sweep cannot see those.
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+([a-z0-9._\-+/=]{8,4096})")

# Key material spans lines, and the assignment rule's value stops at the first
# whitespace -- so ``private_key: -----BEGIN RSA PRIVATE KEY-----\nMIIE...``
# redacted the word ``-----BEGIN`` and published the key. This plugin stores
# SSH private keys (``NodeSSHCredential``) and cloud-init ``sshkeys``, so that
# material genuinely reaches job errors and logs.
#
# An *unterminated* block is redacted to the end of the text: after a BEGIN
# marker every remaining byte is key material, and a truncated log is exactly
# where the END marker goes missing.
# Deliberately two anchors scanned in a loop rather than one regex spanning the
# block. A single lazy ``[\s\S]{0,65536}?`` with an end-of-text fallback is
# quadratic on repeated BEGIN markers -- each one re-scans the tail looking for
# an END that is not there -- and ``"-----BEGIN A-----" * 20000`` took ~45 s.
# The loop below is a plain forward scan.
_PEM_BEGIN_RE = re.compile(r"-----BEGIN [A-Z0-9 ]{1,64}-----")
_PEM_END_RE = re.compile(r"-----END [A-Z0-9 ]{1,64}-----")

# An OpenSSH public key and its trailing comment. The key is not secret, but it
# names the estate and the operator as surely as a hostname does.
_SSH_PUBLIC_KEY_RE = re.compile(
    r"\b(ssh-(?:rsa|dss|ed25519)|ecdsa-sha2-nistp(?:256|384|521))"
    r"\s+[A-Za-z0-9+/=]{20,4096}"
    r"(?:\s+\S{1,256})?"
)

# Every quantifier that precedes a required literal is bounded, for the same
# quadratic-backtracking reason as ``_FQDN_RE`` below: an unbounded greedy class
# in front of a literal that is absent re-scans the tail at every start
# position. The bounds are the real-world limits (RFC 3986 schemes are short;
# RFC 5321 caps an address local-part at 64 octets), so nothing valid is lost.
# The bracketed-IPv6 authority alternative must come first and is matched
# atomically. A plain ``[^/\s:?#]+`` authority stops at the literal's first
# colon, so a management address embedded in a URL came out as
# ``<host-1>:1234::beef]`` -- host token replaced, address still published --
# and the later IPv6 pass could not recover the fragment because the bracketed
# literal had already been split.
_URL_RE = re.compile(
    r"(?i)\b([a-z][a-z0-9+.\-]{0,15})://(?:([^/@\s]{0,255})@)?"
    r"(\[[0-9A-Fa-f:.]{2,45}(?:%[0-9A-Za-z._\-]{1,32})?\]|[^/\s:?#]{1,255})"
    r"(:\d{1,5})?"
)

# Proxmox realm principals: root@pam, svc@pve, backup@pbs.
_REALM_RE = re.compile(r"(?i)\b([A-Za-z0-9._%+\-]{1,64})@(pam|pve|pbs|ldap|ad)\b")

_EMAIL_RE = re.compile(
    r"(?i)\b[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,24}\b"
)

_MAC_RE = re.compile(r"(?i)\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b")

# Every branch but the first requires a ``::``, and the first requires all
# eight groups -- so a wall-clock timestamp (``12:00:00``) can never match.
_IPV6_RE = re.compile(
    r"(?<![0-9A-Fa-f:.])("
    r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,6}:[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,5}(?::[0-9A-Fa-f]{1,4}){1,2}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,4}(?::[0-9A-Fa-f]{1,4}){1,3}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,3}(?::[0-9A-Fa-f]{1,4}){1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,2}(?::[0-9A-Fa-f]{1,4}){1,5}"
    r"|[0-9A-Fa-f]{1,4}:(?::[0-9A-Fa-f]{1,4}){1,6}"
    r"|:(?:(?::[0-9A-Fa-f]{1,4}){1,7}|:)"
    r")(?![0-9A-Fa-f:.])"
)

_IPV4_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
_IPV4_RE = re.compile(
    rf"(?<![0-9A-Za-z.\-])(?:{_IPV4_OCTET}\.){{3}}{_IPV4_OCTET}(?![0-9A-Za-z.\-])"
)

# Hostname matching is anchored on a curated public/internal suffix list rather
# than "any trailing word". Accepting any suffix turned every dotted Python
# path in a traceback (``django.db.utils.OperationalError``) into ``<host-N>``,
# which destroys exactly the text a maintainer needs. Labels are matched
# lowercase-only for the same reason.
_HOST_SUFFIXES = frozenset(
    """
    com net org io dev cloud ai app co info biz xyz tech tools systems site
    online me tv cc sh gg edu gov mil int arpa
    local lan internal intranet corp home localdomain test example invalid onion
    br us uk de fr eu pt es it nl ca au jp cn in ru se no fi dk pl ch at be ie
    nz za mx ar cl
    """.split()
)

# The label group is bounded rather than ``+``. With an unbounded ``+`` a long
# dotted run that never reaches a valid TLD -- ``"aaaaaaaa." * 2000``, or any
# digits-only run like an IPv4 list -- makes the engine consume every label at
# every start position before failing, which is quadratic: 800 labels took
# ~330 ms and 2000 took ~2.1 s. Job logs carry remote-controlled text (a guest
# hostname, a Proxmox error string), so that is a denial-of-service vector on
# the job page, not a micro-optimisation. Eight labels is far past any real
# FQDN; a longer one is only missed when it appears bare, since a host inside a
# URL is matched positionally by ``_URL_RE`` instead.
_MAX_HOST_LABELS = 8

_FQDN_RE = re.compile(
    r"(?<![A-Za-z0-9._\-])"
    r"((?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.){1,%d}[a-z]{2,24})"
    r"(?![A-Za-z0-9.\-])" % _MAX_HOST_LABELS
)


def _redact_pem_blocks(text: str) -> str:
    """Replace every ``-----BEGIN ...-----`` block with a single placeholder.

    An unterminated block consumes the rest of the text: past a BEGIN marker
    every remaining byte is key material, and a truncated log is exactly where
    the END marker goes missing.
    """
    parts: list[str] = []
    position = 0
    while True:
        begin = _PEM_BEGIN_RE.search(text, position)
        if begin is None:
            parts.append(text[position:])
            return "".join(parts)
        parts.append(text[position : begin.start()])
        parts.append(REDACTED)
        end = _PEM_END_RE.search(text, begin.end())
        if end is None:
            return "".join(parts)
        position = end.end()


def _is_ip_literal(value: str) -> bool:
    """Return ``True`` when *value* is a bare IPv4/IPv6 address."""
    return bool(_IPV4_RE.fullmatch(value) or _IPV6_RE.fullmatch(value.strip("[]")))


class Anonymizer:
    """Replace identifying values with stable, per-instance placeholders.

    One instance should scrub every field of a single report so that a value
    appearing in both the error string and a log line gets the same token.
    """

    def __init__(self) -> None:
        self._maps: dict[str, dict[str, str]] = {}

    def placeholder(self, kind: str, value: str) -> str:
        """Return the stable ``<kind-N>`` token for *value*."""
        bucket = self._maps.setdefault(kind, {})
        key = value.lower()
        token = bucket.get(key)
        if token is None:
            token = f"<{kind}-{len(bucket) + 1}>"
            bucket[key] = token
        return token

    def _host_token(self, host: str) -> str:
        """Map a URL authority to an ip/host placeholder as appropriate."""
        bare = host.strip("[]")
        if _is_ip_literal(bare):
            kind = "ipv6" if ":" in bare else "ip"
            return self.placeholder(kind, bare)
        return self.placeholder("host", bare)

    def scrub(self, text: object) -> str:
        """Return *text* with identifying values replaced by placeholders.

        Order matters: credentials are redacted before URLs (so a token in a
        query string never survives as part of an authority), and emails and
        realm principals before hostnames (so ``root@pam`` does not decay into
        ``root@<host-1>``).
        """
        if text is None:
            return ""
        value = text if isinstance(text, str) else str(text)
        if not value:
            return value

        # Multi-line key material first: the assignment rule's value stops at
        # the first whitespace, so it would redact the BEGIN marker and leave
        # the body behind.
        value = _redact_pem_blocks(value)
        value = _SSH_PUBLIC_KEY_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", value)
        value = _SENSITIVE_ASSIGNMENT_RE.sub(
            lambda m: (
                f"{m.group('key')}{m.group('quote_end')}{m.group('sep')}{REDACTED}"
            ),
            value,
        )
        value = _BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", value)
        value = _URL_RE.sub(self._sub_url, value)
        value = _REALM_RE.sub(
            lambda m: f"{self.placeholder('user', m.group(1))}@{m.group(2)}", value
        )
        value = _EMAIL_RE.sub(lambda m: self.placeholder("email", m.group(0)), value)
        value = _MAC_RE.sub(lambda m: self.placeholder("mac", m.group(0)), value)
        value = _IPV6_RE.sub(lambda m: self.placeholder("ipv6", m.group(0)), value)
        value = _IPV4_RE.sub(lambda m: self.placeholder("ip", m.group(0)), value)
        value = _FQDN_RE.sub(self._sub_fqdn, value)
        return value

    def _sub_url(self, match: re.Match[str]) -> str:
        scheme, userinfo, host, port = match.groups()
        token = self._host_token(host)
        # The ``user:password@`` slot never survives: the user half becomes a
        # stable placeholder, the secret half is dropped outright.
        if userinfo:
            user = self.placeholder("user", userinfo.split(":")[0])
            credentials = f"{user}:{REDACTED}@"
        else:
            credentials = ""
        return f"{scheme}://{credentials}{token}{port or ''}"

    def _sub_fqdn(self, match: re.Match[str]) -> str:
        host = match.group(1)
        if host.rsplit(".", 1)[-1] not in _HOST_SUFFIXES:
            return match.group(0)
        return self.placeholder("host", host)


def anonymize_text(text: object, anonymizer: Anonymizer | None = None) -> str:
    """Scrub a single string with a throwaway (or supplied) anonymizer."""
    return (anonymizer or Anonymizer()).scrub(text)


def anonymize_lines(
    lines: Iterable[object], anonymizer: Anonymizer | None = None
) -> list[str]:
    """Scrub each line, sharing one placeholder map across the whole sequence."""
    shared = anonymizer or Anonymizer()
    return [shared.scrub(line) for line in lines]
