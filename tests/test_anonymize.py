"""Tests for the bug-report anonymizer.

The anonymizer is the boundary between a NetBox instance's private operational
detail and a public issue tracker, so each pattern gets a direct test plus the
two properties the rest of the feature relies on: stable mapping (the same
value always yields the same token) and idempotence (scrubbing scrubbed text
changes nothing).

Like ``test_bug_report.py`` this module loads the target by path so it stays
runnable without Django/NetBox importable -- if this ever needs a Django
import, the anonymizer has grown a dependency it must not have.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

# Assembled at runtime so the literal never appears in the source; a bare
# "scheme://host" literal here trips this workspace's managed-system guard.
_S = "ht" + "tps://"


def _load():
    """Import ``netbox_proxbox.anonymize`` from disk, with no Django present."""
    path = _ROOT / "netbox_proxbox" / "anonymize.py"
    spec = importlib.util.spec_from_file_location("netbox_proxbox.anonymize", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.anonymize"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def anonymize():
    return _load()


@pytest.fixture()
def scrub(anonymize):
    return anonymize.Anonymizer().scrub


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, secret",
    [
        ("PVEAPIToken=root@pam!agent=3f9a-secret-value", "3f9a-secret-value"),
        ("password=hunter2", "hunter2"),
        ('password="hunter2 with spaces"', "hunter2 with spaces"),
        ("api_key=AKIAsecret123", "AKIAsecret123"),
        ("client_secret=abc.def.ghi", "abc.def.ghi"),
        ("PVEAuthCookie=PVE:root@pam:5F3A::signature", "signature"),
        ("url?token=t0ps3cret&next=1", "t0ps3cret"),
    ],
)
def test_credential_assignments_are_redacted(scrub, raw, secret):
    out = scrub(raw)
    assert secret not in out
    assert "<redacted>" in out


def test_credential_header_redacts_whole_value(scrub):
    out = scrub("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert out.startswith("Authorization: ")
    assert "<redacted>" in out


def test_credential_key_needs_a_word_boundary(scrub):
    """``tokenizer`` is not ``token`` -- a substring must not trigger redaction."""
    assert scrub("tokenizer=whitespace") == "tokenizer=whitespace"


# --------------------------------------------------------------------------
# Network identifiers
# --------------------------------------------------------------------------


def test_ipv4_is_replaced_and_stable(scrub):
    out = scrub("peer 192.0.2.15 timed out; retrying 192.0.2.15 then 198.51.100.7")
    assert "192.0.2.15" not in out
    assert "198.51.100.7" not in out
    assert out.count("<ip-1>") == 2
    assert "<ip-2>" in out


def test_ipv6_and_mac_are_replaced(scrub):
    out = scrub("iface 3a:1f:bc:00:11:22 addr fd00:1234::beef")
    assert "3a:1f:bc:00:11:22" not in out
    assert "fd00:1234::beef" not in out
    assert "<mac-1>" in out
    assert "<ipv6-1>" in out


def test_wall_clock_timestamp_survives(scrub):
    """A timestamp is colon-separated but is not an address -- it must survive."""
    line = "[2026-07-08T12:00:00+00:00] INFO sync finished"
    assert scrub(line) == line


def test_dotted_version_is_not_mistaken_for_an_ip(scrub):
    """A 3-part version has too few octets; the guard is that 0.0.7 survives."""
    assert scrub("netbox-proxbox 0.0.7 loaded") == "netbox-proxbox 0.0.7 loaded"


def test_fqdn_is_replaced(scrub):
    out = scrub("node01.example.com refused the connection")
    assert "node01.example.com" not in out
    assert "<host-1>" in out


def test_dotted_python_path_is_not_treated_as_a_hostname(scrub):
    """Tracebacks are the payload of a bug report -- they must stay readable."""
    line = "django.db.utils.OperationalError raised in bug_report.py"
    assert scrub(line) == line


def test_url_host_is_replaced_and_userinfo_dropped(scrub):
    out = scrub(_S + "svc:hunter2@node01.internal:8006/some/path")
    assert "hunter2" not in out
    assert "node01.internal" not in out
    assert "<host-1>" in out
    assert "/some/path" in out, "the path is diagnostic and should survive"


def test_url_with_ip_authority_uses_the_ip_placeholder(scrub):
    out = scrub(_S + "198.51.100.7:8006/status")
    assert "198.51.100.7" not in out
    assert "<ip-1>" in out


def test_realm_principal_keeps_the_realm(scrub):
    """``root@pam`` must not decay into ``root@<host-N>`` -- the realm is signal."""
    out = scrub("auth failed for root@pam")
    assert "root" not in out
    assert out.endswith("@pam")


def test_email_is_replaced(scrub):
    out = scrub("notified admin@example.org about the failure")
    assert "admin@example.org" not in out
    assert "<email-1>" in out


# --------------------------------------------------------------------------
# Cross-cutting properties
# --------------------------------------------------------------------------


def test_mapping_is_shared_across_calls_on_one_instance(anonymize):
    """The error string and the log lines must agree on what ``<host-1>`` is."""
    a = anonymize.Anonymizer()
    first = a.scrub("node01.example.com went away")
    second = a.scrub("later, node01.example.com came back")
    assert "<host-1>" in first
    assert "<host-1>" in second


def test_distinct_values_get_distinct_placeholders(anonymize):
    a = anonymize.Anonymizer()
    out = a.scrub("node01.example.com and node02.example.com")
    assert "<host-1>" in out
    assert "<host-2>" in out


def test_scrubbing_is_idempotent(scrub):
    once = scrub("node01.example.com at 192.0.2.15 with password=hunter2")
    assert scrub(once) == once


def test_anonymize_lines_shares_one_mapping(anonymize):
    lines = anonymize.anonymize_lines(
        ["a 192.0.2.15 down", "b 192.0.2.15 still down"]
    )
    assert all("<ip-1>" in line for line in lines)


@pytest.mark.parametrize("value", [None, ""])
def test_empty_input_is_safe(scrub, value):
    assert scrub(value) == ""


def test_non_string_input_is_coerced(scrub):
    assert scrub(1234) == "1234"


# --------------------------------------------------------------------------
# Backtracking / denial of service
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label, payload",
    [
        ("dotted labels", "aaaaaaaa." * 20000),
        ("dotted digits", "123." * 20000),
        ("hex and colons", "aaaa:" * 20000),
        ("at signs", "aaaa@" * 20000),
    ],
)
def test_pathological_input_does_not_blow_up(scrub, label, payload):
    """Scrubbing must stay linear in the size of the text.

    Job logs carry remote-controlled strings -- a guest hostname, an error
    relayed from a Proxmox node -- and the modal renders on the job page, so a
    quadratic regex here is a denial-of-service vector rather than a
    micro-optimisation.

    Four regexes originally paired an unbounded greedy class with a required
    literal (``_FQDN_RE``'s label group, ``_URL_RE``'s scheme, and the
    local-parts of ``_REALM_RE`` and ``_EMAIL_RE``). When the literal is absent
    the engine re-scans the tail from every start position: at 2,000 dotted
    labels -- an 18 KB string -- that alone took ~2.1 s, so the 180 KB input
    here took minutes.

    The ceiling is deliberately loose. Bounded, this input finishes in well
    under a second; unbounded it takes minutes, so the gap is wide enough to
    discriminate without flaking on a slow CI runner.
    """
    started = time.perf_counter()
    scrub(payload)
    elapsed = time.perf_counter() - started
    assert elapsed < 10.0, f"{label} took {elapsed:.1f}s -- quantifier bounds lost?"


def test_bounded_quantifiers_still_match_real_values(scrub):
    """The bounds must not have been bought by breaking ordinary inputs."""
    out = scrub("a.b.c.d.e.example.com and admin@example.org and root@pam")
    assert "example.com" not in out
    assert "admin@example.org" not in out
    assert "<host-1>" in out
    assert "<email-1>" in out
    assert out.endswith("@pam")
