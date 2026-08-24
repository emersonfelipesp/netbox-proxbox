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

# Keys whose *value* is a credential. Matched case-insensitively, longest-first
# so ``access_token`` wins over ``token``.
_CREDENTIAL_KEYS = (
    "pveapitoken",
    "pveauthcookie",
    "csrfpreventiontoken",
    "authorization",
    "proxy-authorization",
    "access_token",
    "refresh_token",
    "id_token",
    "client_secret",
    "private_key",
    "secret_key",
    "api_key",
    "api-key",
    "apikey",
    "password",
    "passwd",
    "credentials",
    "credential",
    "session",
    "secret",
    "ticket",
    "token",
    "auth",
    "pwd",
)

_CRED_ALTERNATION = "|".join(
    re.escape(key) for key in sorted(_CREDENTIAL_KEYS, key=len, reverse=True)
)

# ``key=value`` / ``key = "value"``. The value is a single token, which is what
# an API-token assignment and a query-string pair both look like.
_CREDENTIAL_ASSIGN_RE = re.compile(
    rf"(?i)\b({_CRED_ALTERNATION})\b(\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&)\]}}]+)"
)

# ``Header: value`` consumes the rest of the line: an auth header's value is
# multi-token (``Bearer abc.def``) and over-redacting a trailing clause is the
# safe direction to err in.
_CREDENTIAL_HEADER_RE = re.compile(
    rf"(?i)^(\s*)({_CRED_ALTERNATION})\b(\s*:\s*)(.+)$", re.MULTILINE
)

_URL_RE = re.compile(
    r"(?i)\b([a-z][a-z0-9+.\-]*)://(?:([^/@\s]*)@)?([^/\s:?#]+)(:\d+)?"
)

# Proxmox realm principals: root@pam, svc@pve, backup@pbs.
_REALM_RE = re.compile(r"(?i)\b([A-Za-z0-9._%+\-]+)@(pam|pve|pbs|ldap|ad)\b")

_EMAIL_RE = re.compile(r"(?i)\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}\b")

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

_FQDN_RE = re.compile(
    r"(?<![A-Za-z0-9._\-])"
    r"((?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})"
    r"(?![A-Za-z0-9.\-])"
)


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

        value = _CREDENTIAL_ASSIGN_RE.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", value
        )
        value = _CREDENTIAL_HEADER_RE.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}", value
        )
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
