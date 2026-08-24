"""Both redactors must honour the whole shared vocabulary.

``netbox_proxbox/redaction.py`` now owns the judgement of what counts as a
credential-bearing field. Owning it is not the same as *using* it: a consumer
can import the vocabulary and still fail to apply it, and that failure looks
exactly like success from the outside.

So this does not compare the two modules' constants -- that would only prove
they read the same list. Every marker is pushed through **both** redactors as
real input, and the canary must not survive either. The previous version of
this file only checked the public scrubber, and only against short single-line
assignments; it passed while the public path was leaking folded headers,
oversized values and doubly-escaped JSON.

Both modules are loaded by path (see ``tests/pure_loader.py``), which is also a
standing assertion that neither has acquired a Django dependency.
"""

from __future__ import annotations

import sys
import time

import pytest

from tests.pure_loader import load_anonymize, load_error_utils, load_redaction

_SECRET = "s3cr3tcanaryvalue"


@pytest.fixture()
def redaction(monkeypatch):
    return load_redaction(monkeypatch)


# ---------------------------------------------------------------------------
# The vocabulary itself
# ---------------------------------------------------------------------------


def test_both_representations_come_from_one_source(redaction):
    """Normalised and regex forms must describe the same set.

    A marker is needed twice -- ``apikey`` to compare against a folded key, and
    ``api[_-\\s]?key`` to find an assignment in raw text. Maintaining those
    separately is the same drift problem one level down, so both are generated
    from ``_MARKER_WORDS`` and this pins that they stay in step.
    """
    words = redaction._MARKER_WORDS
    assert len(redaction.SENSITIVE_KEY_MARKERS) == len(words)
    for entry in words:
        joined = "".join(entry)
        assert joined in redaction.SENSITIVE_KEY_MARKERS
        # Every separator spelling of the marker must fold to the same form.
        for separator in ("", "_", "-", " "):
            spelled = separator.join(entry)
            assert redaction.normalize_key(spelled) == joined


# Transcribed once, deliberately, as a fixed oracle. The per-marker sweeps
# below take their parameters *from* the vocabulary, so removing an entry
# silently removes its test cases too and every one of them still passes. Only a
# list written down independently catches a deletion.
_REQUIRED_MARKERS = frozenset(
    {
        "authorization",
        "credential",
        "passphrase",
        "password",
        "passwd",
        "session",
        "sshkeys",
        "secret",
        "cookie",
        "ticket",
        "token",
        "auth",
        "pwd",
        "apikey",
        "privatekey",
        "publickey",
        "encryptionkey",
        "secretkey",
        "signingkey",
        "hostkey",
        "sshkey",
    }
)

_REQUIRED_SCHEMES = frozenset(
    {"bearer", "basic", "token", "digest", "negotiate", "apikey"}
)


def test_no_marker_is_ever_dropped(redaction):
    """Deleting a marker must fail here, not merely shrink the sweeps below.

    Several entries are this plugin's own field and setting names, and each was
    added because something published a credential without it: ``token`` for
    ``token_value``/``token_secret``, ``apikey`` for ``X-Proxbox-API-Key``,
    ``encryptionkey`` for the plugin settings key, ``sshkeys`` for cloud-init.
    """
    missing = _REQUIRED_MARKERS - set(redaction.SENSITIVE_KEY_MARKERS)
    assert not missing, f"vocabulary lost: {sorted(missing)}"


def test_no_auth_scheme_is_ever_dropped(redaction):
    """``token`` in particular: it is the scheme NetBox's own API uses."""
    missing = _REQUIRED_SCHEMES - set(redaction.AUTH_SCHEMES)
    assert not missing, f"schemes lost: {sorted(missing)}"


def test_key_matching_folds_separators_and_case(redaction):
    """One field, several spellings -- all of them must match."""
    for spelling in ("api_key", "api-key", "API Key", "X-Proxbox-API-Key"):
        assert redaction.is_sensitive_key(spelling), spelling
    assert not redaction.is_sensitive_key("hostname")
    assert not redaction.is_sensitive_key(None)


# ---------------------------------------------------------------------------
# Both consumers, against every marker
# ---------------------------------------------------------------------------


def _markers(monkeypatch_factory):
    """Marker list for parametrisation, read without a fixture."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "netbox_proxbox" / "redaction.py"
    spec = importlib.util.spec_from_file_location("_redaction_for_params", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.SENSITIVE_KEY_MARKERS


@pytest.mark.parametrize("marker", _markers(None))
def test_public_scrubber_redacts_every_marker(monkeypatch, marker):
    """The public path publishes; it must honour the whole vocabulary."""
    scrub = load_anonymize(monkeypatch).Anonymizer().scrub
    for line in (f"{marker}={_SECRET}", f"{marker}: {_SECRET}"):
        assert _SECRET not in scrub(line), f"{marker!r} survived {line!r}"


@pytest.mark.parametrize("marker", _markers(None))
def test_job_log_redactor_redacts_every_marker(monkeypatch, marker):
    """The internal path writes to a long-lived, user-visible job log."""
    module = load_error_utils(monkeypatch)
    # As a mapping key, which is how a backend payload usually carries it.
    redacted = module.redact_sensitive({marker: _SECRET})
    assert _SECRET not in repr(redacted), f"{marker!r} survived as a mapping key"
    # And rendered into prose, which key matching cannot reach.
    assert _SECRET not in module.redact_sensitive_text(f"{marker}={_SECRET}")


@pytest.mark.parametrize("scheme", ["Bearer", "Basic", "Token", "Digest", "ApiKey"])
def test_both_redactors_sweep_every_auth_scheme(monkeypatch, scheme):
    """``Token`` is the scheme NetBox's own API uses -- omitting it leaked."""
    token = "nbt_s3cr3tschemevalue"
    scrub = load_anonymize(monkeypatch).Anonymizer().scrub
    assert token not in scrub(f"Authorization: {scheme} {token}")

    module = load_error_utils(monkeypatch)
    assert token not in module.redact_sensitive_text(f"Authorization: {scheme} {token}")


def test_neither_redactor_eats_ordinary_fields(monkeypatch):
    """Fail-closed must not mean redact-everything."""
    line = "vmid=100 status=stopped cores=4 memory=2048"
    assert load_anonymize(monkeypatch).Anonymizer().scrub(line) == line
    assert load_error_utils(monkeypatch).redact_sensitive_text(line) == line


def test_modules_import_without_django(monkeypatch):
    """Both are loaded by path here; that is the assertion.

    If either grows a Django import, every test in this file fails at load --
    which is the point. ``anonymize`` must stay importable without Django for
    ``tests/test_bug_report.py``, and the shared module must stay pure for both.
    """
    assert load_anonymize(monkeypatch) is not None
    assert load_error_utils(monkeypatch) is not None
    assert load_redaction(monkeypatch) is not None


def test_the_loader_leaves_no_modules_behind(monkeypatch):
    """``sys.modules`` must be restored to whatever it held before the load.

    The loader originally assigned ``sys.modules`` directly, so the modules it
    path-loaded stayed registered for every later test in the session. Nothing
    broke *yet*, but that is precisely the arrangement in which a test passes
    only because an earlier one left the right object behind, and it would
    shadow a genuine import of either module.

    The assertion is *restoration*, not absence: ``conftest.py`` installs its
    own ``netbox_proxbox`` stubs for the whole session, so several of these
    names are legitimately present before this test starts. An earlier version
    asserted absence, passed when run alone, and failed inside the full suite --
    which is the same class of mistake it exists to catch.
    """
    names = (
        "netbox_proxbox",
        "netbox_proxbox.views",
        "netbox_proxbox.redaction",
        "netbox_proxbox.anonymize",
        "netbox_proxbox.views.error_utils",
    )
    before = {name: sys.modules.get(name) for name in names}

    load_anonymize(monkeypatch)
    load_error_utils(monkeypatch)
    assert "netbox_proxbox.redaction" in sys.modules, "seeded during the test"

    monkeypatch.undo()

    after = {name: sys.modules.get(name) for name in names}
    changed = [name for name in names if after[name] is not before[name]]
    assert not changed, f"the loader left {changed} altered in sys.modules"


# ---------------------------------------------------------------------------
# The two representations must agree in practice, not just in principle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("separator_run", list(range(0, 9)))
def test_separator_runs_agree_across_both_representations(monkeypatch, separator_run):
    """``normalize_key`` strips a run of any length; the regex must accept one.

    An earlier version joined compound markers with ``[_\\-\\s]?`` -- at most one
    character -- so ``api__key`` was a sensitive *key* that neither raw-text
    matcher recognised, and the secret behind it reached the decoded public
    issue body. Key matching and text matching have to describe the same field
    names or the stricter one is decorative.
    """
    redaction = load_redaction(monkeypatch)
    key = "api" + ("_" * separator_run) + "key"

    assert redaction.is_sensitive_key(key)
    assert _SECRET not in load_anonymize(monkeypatch).Anonymizer().scrub(
        f"{key}={_SECRET}"
    )
    assert _SECRET not in load_error_utils(monkeypatch).redact_sensitive_text(
        f"{key}={_SECRET}"
    )


@pytest.mark.parametrize(
    "key", ["api-_key", "api _key", "API__Key", "X-Proxbox-API-Key", "api-key"]
)
def test_mixed_separator_spellings_are_matched_in_text(monkeypatch, key):
    """Real field names mix ``-``, ``_`` and spaces, in any case."""
    assert _SECRET not in load_anonymize(monkeypatch).Anonymizer().scrub(
        f"{key}={_SECRET}"
    )
    assert _SECRET not in load_error_utils(monkeypatch).redact_sensitive_text(
        f"{key}={_SECRET}"
    )


def test_the_separator_bound_is_documented_not_accidental(monkeypatch):
    """Past the bound the key is still caught as a *key*, just not in prose.

    The run is bounded because an unbounded one in front of a required literal
    is the quadratic shape this module already fixed elsewhere. That trade-off
    is deliberate, so it is pinned rather than left to be rediscovered.
    """
    redaction = load_redaction(monkeypatch)
    over = "api" + ("_" * (redaction.MAX_SEPARATOR_RUN + 1)) + "key"
    assert redaction.is_sensitive_key(over), "key matching is unbounded by design"
    assert _SECRET in load_anonymize(monkeypatch).Anonymizer().scrub(
        f"{over}={_SECRET}"
    )


# ---------------------------------------------------------------------------
# Neither matcher may be quadratic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("length", [4000, 32000])
def test_job_log_redaction_stays_linear(monkeypatch, length):
    """Marker-free text must not cost more than a scan.

    Pairing two unbounded key runs around the 21-way alternation was quadratic:
    8 KB of one repeated character took ~12.8 s, and SSE error frames are
    redacted here *before* the 600-character log truncation, so a modest error
    frame could pin an RQ worker. The identifier-start guard and the bounded and
    possessive runs bring it to ~0.4 ms.
    """
    module = load_error_utils(monkeypatch)
    started = time.perf_counter()
    module.redact_sensitive_text("a" * length)
    assert time.perf_counter() - started < 5.0


def test_job_log_redaction_still_redacts_after_the_speedup(monkeypatch):
    """The bounds must not have been bought by matching less."""
    module = load_error_utils(monkeypatch)
    for line in (f"password={_SECRET}", f"Authorization: Token {_SECRET}"):
        assert _SECRET not in module.redact_sensitive_text(line)
    assert module.redact_sensitive_text("vmid=100 status=stopped") == (
        "vmid=100 status=stopped"
    )
