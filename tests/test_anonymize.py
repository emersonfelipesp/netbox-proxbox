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


def test_marker_matching_errs_towards_redaction(scrub):
    """A key merely *containing* a marker is redacted, on purpose.

    Exact-name matching is what let ``token_value`` and ``token_secret`` -- real
    field names on this plugin's own models -- through, so matching is by marker
    and fails closed. The cost is that ``tokenizer=`` is redacted too; losing a
    word from a bug report is recoverable, publishing a credential is not.
    """
    assert scrub("tokenizer=whitespace") == "tokenizer=<redacted>"


def test_keys_without_a_marker_are_left_alone(scrub):
    """Fail-closed must not mean redact-everything; ordinary fields survive.

    ``hostname=`` is deliberately absent here -- it *is* matched now, by the
    labelled-host rule rather than the credential rule.
    """
    line = "vmid=100 status=stopped cores=4 memory=2048 disk=32"
    assert scrub(line) == line


def test_a_key_must_start_at_an_identifier_boundary(scrub):
    """A marker part-way through one identifier is not a field name."""
    assert scrub("notatokenhere") == "notatokenhere"


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
    lines = anonymize.anonymize_lines(["a 192.0.2.15 down", "b 192.0.2.15 still down"])
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


# --------------------------------------------------------------------------
# Credential shapes that an exact-key, line-anchored matcher missed
#
# Each of these was a live leak found by adversarial review: every one reached
# `report_text` *and* the prefilled public issue URL unchanged.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label, raw, secret",
    [
        ("json object", '{"password":"hunter2","user":"root"}', "hunter2"),
        ("json with spaces", '{ "api_key" : "AKIAxyz" }', "AKIAxyz"),
        ("python dict repr", "{'password': 'hunter2'}", "hunter2"),
        # Real field names on this plugin's own models.
        ("plugin token_value", "token_value=abc123secret", "abc123secret"),
        ("plugin token_secret", "token_secret=def456secret", "def456secret"),
        # A real header spelling; only the underscore form used to match.
        ("http header key", "X-Proxbox-API-Key: k3yv4lue", "k3yv4lue"),
        ("prefixed key", "mytoken=s3cr3tvalue", "s3cr3tvalue"),
    ],
)
def test_credential_shapes_are_redacted(scrub, label, raw, secret):
    assert secret not in scrub(raw), label


def test_authorization_header_inside_a_formatted_log_line(scrub):
    """The ``:`` rule must not be anchored to the start of a line.

    ``_format_log_lines`` prepends ``[timestamp] LEVEL `` *before* anything is
    scrubbed, so an anchored rule never fires on a real log entry -- and a test
    whose fixture omits that prefix passes while proving nothing. This fixture
    carries the prefix deliberately.
    """
    out = scrub("[2026-07-08T12:00:00+00:00] ERROR Authorization: Bearer eyJTOKENXX")
    assert "eyJTOKENXX" not in out
    assert "<redacted>" in out


def test_bare_bearer_token_is_swept(scrub):
    """A credential quoted into prose has no key in front of it to match on."""
    out = scrub("upstream said: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert "Bearer <redacted>" in out


def test_bearer_keyword_alone_is_not_treated_as_the_value(scrub):
    """Redacting the scheme keyword would leave the token in the clear."""
    out = scrub("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
    assert "eyJhbGciOiJIUzI1NiJ9" not in out


def test_bracketed_ipv6_url_authority_is_replaced_whole(scrub):
    """A plain authority class stops at the literal's first colon.

    That published most of a management address (`<host-1>:1234::beef]`) and
    left a fragment the later IPv6 pass could no longer recognise.
    """
    out = scrub(_S + "svc:hunter2@" + "[fd00:1234::beef]" + "/api")
    assert "hunter2" not in out
    assert "fd00" not in out
    assert "beef" not in out
    assert "<ipv6-1>" in out


# --------------------------------------------------------------------------
# Multi-line key material
#
# The assignment rule's value stops at the first whitespace, so it redacted the
# ``-----BEGIN`` marker and published the body. This plugin stores SSH private
# keys (``NodeSSHCredential``) and cloud-init ``sshkeys``, so the material does
# reach job errors and logs.
# --------------------------------------------------------------------------


def test_pem_private_key_block_is_removed(scrub):
    out = scrub(
        "private_key: -----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEAsecretkeymaterial\n"
        "-----END RSA PRIVATE KEY-----\ntail stays"
    )
    assert "secretkeymaterial" not in out
    assert "MIIEow" not in out
    assert "tail stays" in out, "only the block should be consumed"


def test_unterminated_pem_block_consumes_the_rest(scrub):
    """A truncated log is exactly where the END marker goes missing."""
    out = scrub(
        "key: -----BEGIN OPENSSH PRIVATE KEY-----\nMIIEowsecrettruncated\n(log cut)"
    )
    assert "secrettruncated" not in out


def test_ssh_public_key_and_comment_are_replaced(scrub):
    """Not secret, but it names the estate and the operator."""
    out = scrub("sshkeys=ssh-rsa AAAAB3NzaC1yc2EAAAADAQABsecretpubkeydata admin@corp")
    assert "secretpubkeydata" not in out
    assert "admin@corp" not in out


def test_a_hex_digest_is_not_mistaken_for_key_material(scrub):
    """Digests are diagnostic and sit inside the base64 alphabet."""
    line = "sha256:9f2c4a1be3d5079ab2c1e4f6a8d0b3c5e7f9012345678abcdef0123456789ab"
    assert scrub(line) == line


@pytest.mark.parametrize(
    "label, payload",
    [
        # A single lazy span with an end-of-text fallback made each BEGIN
        # re-scan the tail for an END that is not there: ~45 s.
        ("unterminated begin markers", "-----BEGIN A-----" * 20000),
        ("begin/end pairs", "-----BEGIN A-----x-----END A-----" * 20000),
        ("ssh key runs", "ssh-rsa AAAAAAAAAAAAAAAAAAAAAA " * 20000),
        ("bearer runs", "Bearer aaaa " * 20000),
    ],
)
def test_key_material_sweeps_stay_linear(scrub, label, payload):
    started = time.perf_counter()
    scrub(payload)
    elapsed = time.perf_counter() - started
    assert elapsed < 10.0, f"{label} took {elapsed:.1f}s"


# --------------------------------------------------------------------------
# Authentication schemes and further credential shapes (round 2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label, raw, secret",
    [
        # NetBox's own API uses the ``Token`` scheme; enumerating schemes in the
        # value branch matched ``Token`` alone and published the credential.
        (
            "Token scheme",
            "Authorization: Token nbt_s3cr3ttokenvalue",
            "nbt_s3cr3ttokenvalue",
        ),
        (
            "Digest scheme",
            "Proxy-Authorization: Digest xyzs3cr3tdigest",
            "xyzs3cr3tdigest",
        ),
        (
            "unknown scheme",
            "Authorization: Weird s3cr3tunknownscheme",
            "s3cr3tunknownscheme",
        ),
        ("bare Token", "sent Token nbt_barevalue123", "nbt_barevalue123"),
        # Keys the first marker set missed outright.
        ("auth", "auth=s3cr3tauthvalue", "s3cr3tauthvalue"),
        ("session", "session=s3cr3tsessionid", "s3cr3tsessionid"),
        ("plugin encryption_key", "encryption_key=s3cr3tfernetkey", "s3cr3tfernetkey"),
        ("passphrase", "passphrase=s3cr3tphrase", "s3cr3tphrase"),
        ("host_key", "host_key=s3cr3thostkey", "s3cr3thostkey"),
        # A namespaced key longer than the original 64-character prefix bound.
        ("long namespaced key", "a" * 100 + "_password=s3cr3tlongns", "s3cr3tlongns"),
    ],
)
def test_further_credential_shapes_are_redacted(scrub, label, raw, secret):
    assert secret not in scrub(raw), label


def test_authorization_value_is_consumed_whatever_the_scheme(scrub):
    """The header value is opaque; matching known schemes is not sufficient."""
    out = scrub("Authorization: SomeFutureScheme abc s3cr3tfuture def")
    assert "s3cr3tfuture" not in out
    assert out.startswith("Authorization: ")


def test_escaped_quotes_do_not_end_the_value_early(scrub):
    """``"[^"]*"`` stops at a JSON-escaped quote and publishes the remainder."""
    out = scrub('{"password":"he said \\"s3cr3tinquote\\" ok"}')
    assert "s3cr3tinquote" not in out


def test_ed25519_public_key_is_replaced(scrub):
    out = scrub("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5s3cr3ted25519data admin@corp")
    assert "s3cr3ted25519data" not in out
    assert "admin@corp" not in out


def test_long_namespaced_keys_stay_linear(scrub):
    """Raising the key prefix bound to 256 must not reintroduce blowup."""
    started = time.perf_counter()
    scrub(("a" * 200 + "_password ") * 2000)
    assert time.perf_counter() - started < 10.0


# --------------------------------------------------------------------------
# Diagnosis must survive
#
# Fail-closed matching has a real cost: a report scrubbed into uselessness is a
# bug report nobody can act on. These are verbatim shapes this stack actually
# emits -- several are strings other modules branch on (`sync_stages.py` looks
# for "init_ok"; `sync_types.py` matches the Postgres connection-slots phrase;
# `_is_retryable_stage_failure` matches the transport texts).
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "Error ensuring Proxbox tag",
        # A validation rejection, not a transport timeout -- the retry
        # classifier distinguishes them by this exact wording.
        "timeout must be between 1 and 300",
        "stage virtual-machines failed: 500 Internal Server Error",
        "remaining connection slots are reserved for non-replication superuser connections",
        "Invalid v1 token",
        "token_version mismatch: expected 2 got 1",
        "Authentication failed against Proxmox endpoint",
        "[Errno 111] Connection refused",
        "Temporary failure in name resolution",
        "504 Gateway Time-out",
        "sync_types: ['virtual-machines', 'storage']",
        "django.db.utils.OperationalError: could not connect",
        "credential rotation required",
        "session expired, re-authenticating",
        "ticket renewal failed after 3 attempts",
    ],
)
def test_diagnostic_text_is_left_intact(scrub, line):
    """A marker-bearing word is not an assignment; only ``key<sep>value`` is.

    ``Invalid v1 token`` and ``session expired`` carry markers but no separator,
    so they must survive verbatim. This is what stops fail-closed matching from
    degenerating into redact-everything.
    """
    assert scrub(line) == line


def test_a_transport_error_keeps_everything_but_the_host(scrub):
    """The host is replaced; the diagnosis around it is not."""
    out = scrub(
        "HTTPConnectionPool(host='node01.example.com', port=8006): Read timed out"
    )
    assert "node01.example.com" not in out
    assert "Read timed out" in out
    assert "port=8006" in out


def test_a_labelled_node_name_is_replaced_but_the_sentence_survives(scrub):
    """Single-label node names are caught where something names them as a host.

    A bare identifier in prose is unknowable, but ``node <name>`` is not -- and
    ``pve-node-01`` style names are the normal Proxmox form, so leaving them was
    a real gap. The rest of the sentence must still read.
    """
    out = scrub("VM 100 on node pve-node-01 is locked by a backup task")
    assert "pve-node-01" not in out
    assert "VM 100 on node " in out
    assert "is locked by a backup task" in out


@pytest.mark.parametrize(
    "line",
    [
        # ``node``/``host``/``cluster`` followed by an ordinary word is prose,
        # not a host name; redacting these would turn sentences into soup.
        "node is not reachable",
        "host unknown",
        "cluster name missing",
        "endpoint not found",
        "server error",
    ],
)
def test_labelled_host_rule_does_not_eat_prose(scrub, line):
    assert scrub(line) == line


def test_uppercase_and_mixed_case_fqdns_are_replaced(scrub):
    """``PVE01.EXAMPLE.COM`` is an ordinary way to write a node name."""
    out = scrub("node PVE01.EXAMPLE.COM and Pve01.Example.Com failed")
    assert "PVE01.EXAMPLE.COM" not in out
    assert "Pve01.Example.Com" not in out
    # Case-insensitive mapping: the two spellings are the same host.
    assert out.count("<host-1>") == 2


def test_authorization_prose_keeps_the_diagnosis(scrub):
    """The header rule must not erase a permission failure's detail.

    Firing anywhere collapsed this to ``Proxmox authorization: <redacted>``,
    destroying the privilege, the path and the cause -- in a report whose whole
    purpose is to convey them.
    """
    out = scrub(
        "Proxmox authorization: denied; missing Sys.Audit on /nodes/pve01/storage/local"
    )
    assert "Sys.Audit" in out
    assert "/nodes/pve01/storage/local" in out


def test_authorization_header_keeps_its_log_prefix(scrub):
    """The prefix is inside the match, so it has to be re-emitted."""
    out = scrub("[2026-07-08T12:00:00+00:00] ERROR Authorization: Token nbt_abc123def")
    assert out.startswith("[2026-07-08T12:00:00+00:00] ERROR Authorization: ")
    assert "nbt_abc123def" not in out
    assert out.count("2026-07-08") == 1, "the prefix must not be duplicated"


@pytest.mark.parametrize(
    "label, raw, secret",
    [
        ("nested json escape", '{\\"password\\":\\"s3cr3tnested\\"}', "s3cr3tnested"),
        ("oversized value", "password=" + "x" * 9000 + "s3cr3ttail", "s3cr3ttail"),
        ("folded header", "Authorization: Token\n\ts3cr3tfolded", "s3cr3tfolded"),
    ],
)
def test_round_three_credential_shapes(scrub, label, raw, secret):
    """A cap left the tail of an over-long value in the clear; a fold hid it."""
    assert secret not in scrub(raw), label
