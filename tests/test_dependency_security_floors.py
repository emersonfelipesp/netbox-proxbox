"""Guard the declared dependency floors that carry a security meaning.

Bumping ``uv.lock`` protects CI, but the lock is neither shipped in the wheel nor
consulted by ``pip``. What protects an *installed* environment is the floor
declared in the manifest that environment installs from:

* ``pyproject.toml`` -- the metadata of the shipped distribution, for anyone
  running ``pip install netbox-proxbox[cli]``.
* ``requirements-docs.txt`` -- installed verbatim by the documentation
  workflows with ``pip install -r``, which never reads the lock.

A floor that still admits a version covered by a published advisory silently
re-introduces the vulnerability on the next fresh resolve, while a lockfile
scanner reports nothing.

The oracle is :data:`SECURITY_FLOORS` -- a fixed matrix transcribed once from the
published advisories, never derived from the manifests under test.

Design notes, all deliberate:

* **The safety check is structural, not a sample.** Enumerating a handful of
  affected versions and asserting they are refused is not enough: a specifier
  can exclude exactly those samples and still admit the rest of the advisory
  range. ``aiohttp>=3.13.0,!=3.14.0,!=3.14.1,!=3.14.2`` refuses every sampled
  version, admits the patched floor, and still admits the covered 3.13.5. So
  :func:`_effective_lower_bound` requires the specifier to *establish* a lower
  bound at or above the floor. ``!=`` clauses deliberately do not count as a
  floor -- excluding known-bad versions one at a time is what the bypass does.
* **Manifests are parsed with ``tomllib`` and ``packaging``, never a whole-file
  regex.** A regex scanning the whole document can match a decoy in an unrelated
  table and report a floor that is not the one in force. A false floor is worse
  than no guard, because it reports success.
* **Every check fails closed.** A missing file, unparseable manifest, absent
  table, undeclared dependency, duplicate declaration, or an install directive
  this parser cannot see into is a FAILURE, never a skip. Skipping is for a
  property that legitimately does not apply -- never for an inability to
  evaluate one.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS_DOCS = ROOT / "requirements-docs.txt"
NETBOX_REQUIREMENTS_DIR = ROOT / "ci" / "netbox-requirements"

# Location keys. Each names one manifest position a floor can be required in;
# _SPEC_SOURCES maps them to the accessor that reads that position.
RUNTIME_DEPENDENCIES = "pyproject.toml [project].dependencies"
CLI_EXTRA = "pyproject.toml [project.optional-dependencies].cli"
DEV_GROUP = "pyproject.toml [dependency-groups].dev"
DEV_EXTRA = "pyproject.toml [project.optional-dependencies].dev"
DOCS_REQUIREMENTS = "requirements-docs.txt"


class SecurityFloor:
    """One package's required floor and the manifests that must declare it."""

    def __init__(
        self,
        name: str,
        floor: str,
        affected: tuple[str, ...],
        advisories: tuple[str, ...],
        declared_in: tuple[str, ...],
    ) -> None:
        self.name = name
        self.floor = floor
        # Sample versions inside the advisory ranges. These back up the
        # structural check with a concrete, readable failure; they are not the
        # primary oracle, because a sample set can be excluded one by one.
        self.affected = affected
        self.advisories = advisories
        self.declared_in = declared_in


# Transcribed from the published advisories through 2026-10-21. Do not regenerate any
# of this from the manifests -- that would make the tests assert only that the
# code agrees with itself.
SECURITY_FLOORS: dict[str, SecurityFloor] = {
    "aiohttp": SecurityFloor(
        name="aiohttp",
        floor="3.14.4",
        # GHSA-9xw5-w5jj-pvcg covers >= 2.0.0, < 3.14.4 and the other 3.14.4
        # advisories cover <= 3.14.3; GHSA-cq5v-8q36-5273 covers <= 3.14.2 and
        # the remaining two cover <= 3.14.1.
        affected=("3.12.15", "3.13.5", "3.14.0", "3.14.1", "3.14.2", "3.14.3"),
        advisories=(
            "GHSA-cq5v-8q36-5273",  # OOB heap read, C HTTP response parser
            "GHSA-mfx4-hv73-q22v",  # request smuggling via WebSocket upgrade
            "GHSA-mq44-7p77-q5h7",  # unnegotiated permessage-deflate
            "GHSA-9xw5-w5jj-pvcg",  # multipart file descriptor exhaustion
            "GHSA-2g87-pp6c-29x5",  # unbounded memory/CPU use
            "GHSA-5wr8-gcqf-gqf3",  # no initial request/header timeout
            "GHSA-pqxq-w44r-73xw",  # pure-Python parser request smuggling
            "GHSA-f9xw-jh8m-3mwq",  # absolute-form target spoofs scheme
            "GHSA-6cjc-53gc-5rqm",  # connector pool exhaustion, Max-Age overflow
            "GHSA-gx76-c99x-2c96",  # subdomain cookie removes host-only scope
            "GHSA-494j-54xm-rwp3",  # Secure attribute not enforced, shared cookie
        ),
        # Reached by proxbox_cli/client.py in the shipped extra, and installed
        # by the documentation workflows.
        declared_in=(CLI_EXTRA, DOCS_REQUIREMENTS),
    ),
    "cryptography": SecurityFloor(
        name="cryptography",
        floor="50.0.0",
        # GHSA-g6cj-pr64-35w5 covers >= 44.0.0, < 50.0.0.
        affected=("44.0.0", "48.0.1", "49.0.0"),
        advisories=("GHSA-g6cj-pr64-35w5",),
        # This is a shipped runtime dependency. The wheel does not include or
        # consult uv.lock, so the floor must be present in project metadata.
        declared_in=(RUNTIME_DEPENDENCIES,),
    ),
    "pymdown-extensions": SecurityFloor(
        name="pymdown-extensions",
        floor="11.0.1",
        # GHSA-gm37-52c6-37mw covers <= 11.0.0; GHSA-9xwg-3r6f-jcx2 <= 10.21.3.
        affected=("10.2", "10.21.3", "11.0.0"),
        advisories=(
            "GHSA-gm37-52c6-37mw",  # backtracking ReDoS in inline processors
            "GHSA-9xwg-3r6f-jcx2",  # path traversal in the b64 extension
        ),
        # Only ever a transitive dependency of the documentation toolchain, and
        # mkdocs-material asks merely for >=10.2 -- which admits both advisory
        # ranges. A pip install of the docs requirements consults no lock, so
        # the floor has to be declared explicitly in both docs manifests.
        declared_in=(DEV_GROUP, DOCS_REQUIREMENTS),
    ),
    "mkdocs-material": SecurityFloor(
        name="mkdocs-material",
        floor="9.7.7",
        # GHSA-xvg9-69gf-fjrf covers >= 7.2.0, < 9.7.7.
        affected=("9.7.6",),
        advisories=("GHSA-xvg9-69gf-fjrf",),
        declared_in=(DEV_GROUP, DOCS_REQUIREMENTS),
    ),
    "virtualenv": SecurityFloor(
        name="virtualenv",
        floor="21.14.9",
        # Known unpatched: GHSA-4f8h-vr72-p32c (>= 21.14.8, symlink seeding with
        # temporary app-data) has no fixed release, so no floor can clear it.
        # Raise this floor when one is published.
        # GHSA-c978-59m8-c77v (POSIX launcher destination paths) covers exactly
        # 21.14.8. GHSA-vxj4-q4g9-crj7 (bash activate) covers <= 21.14.6,
        # GHSA-5vjq-rrrf-7h2q (zsh activate) covers <= 21.14.3, and
        # GHSA-c947-3pg5-gm8q (fish activate) plus GHSA-8rjx-v5ww-45pp
        # (placeholder in the path) cover <= 21.14.1. The earlier
        # activation-script issue covers <= 21.7.12; the seed-wheel and
        # prompt-injection advisories cover earlier subsets of the same range.
        affected=(
            "20.36.1",
            "21.7.10",
            "21.7.11",
            "21.7.12",
            "21.7.13",
            "21.14.1",
            "21.14.3",
            "21.14.6",
            "21.14.8",
        ),
        advisories=(
            "GHSA-94p9-xgh2-xp45",
            "GHSA-9h9j-4vrj-gf7g",
            "GHSA-p58f-9548-mpm2",
            "GHSA-x78j-v8h9-3j2q",
            "GHSA-5vjq-rrrf-7h2q",
            "GHSA-vxj4-q4g9-crj7",
            "GHSA-c947-3pg5-gm8q",
            "GHSA-8rjx-v5ww-45pp",
            "GHSA-c978-59m8-c77v",
        ),
        declared_in=(DEV_GROUP, DEV_EXTRA),
    ),
    "certifi": SecurityFloor(
        name="certifi",
        floor="2026.10.19",
        # GHSA-6q48-6c7w-9gw2 covers >= 2019.03.09, < 2026.10.19.
        affected=("2019.3.9", "2025.8.3", "2026.7.22"),
        advisories=("GHSA-6q48-6c7w-9gw2",),
        # Transitive through requests/httpx in the documentation install, which
        # admits every affected bundle and does not consult uv.lock. Deliberately
        # NOT a shipped runtime floor: the plugin installs into an existing
        # NetBox environment whose certifi belongs to NetBox, and a package
        # deploy that verifies Requires-Dist against that environment would
        # refuse the plugin until NetBox itself is upgraded. Every lock pins a
        # fixed bundle (TRANSITIVE_LOCK_FLOORS), and the NetBox environment
        # should take certifi>=2026.10.19 through its own upgrade path.
        declared_in=(DOCS_REQUIREMENTS,),
    ),
    "multidict": SecurityFloor(
        name="multidict",
        floor="6.9.1",
        # GHSA-54p9-h82j-f925 covers >= 6.7.0, <= 6.9.0.
        affected=("6.7.0", "6.8.0", "6.9.0"),
        advisories=("GHSA-54p9-h82j-f925",),
        # Transitive through aiohttp/yarl in the shipped cli extra and the
        # documentation install, which both admit the affected releases.
        declared_in=(CLI_EXTRA, DOCS_REQUIREMENTS),
    ),
    "urllib3": SecurityFloor(
        name="urllib3",
        floor="2.8.0",
        affected=("1.26.20", "2.6.2", "2.7.0"),
        advisories=(
            "GHSA-8988-9cw3-xx77",
            "GHSA-gh4c-6fx4-qh6g",
            "GHSA-vxq7-64xx-v4gw",
        ),
        declared_in=(RUNTIME_DEPENDENCIES,),
    ),
}


# The matrix inputs begin with the exact requirements from each immutable
# NetBox commit, then apply reviewed security overrides. These floors are kept
# separate from SECURITY_FLOORS because the matrix files are CI fixtures, not
# install manifests shipped to users.
_COMMON_NETBOX_MATRIX_FLOORS = {
    "djangorestframework": "3.17.2",
    "mkdocs-material": "9.7.7",
    "oauthlib": "4.0.0",
    # Known unpatched: GHSA-654x-cwwv-5j9c (11.2.1 through 13.0.0, Arrow export
    # with PILLOW_ALIGNMENT > 1) has no fixed release yet.
    "pillow": "13.0.0",
    "pyjwt": "2.15.0",
    "strawberry-graphql": "0.327.2",
    "tablib": "3.10.0",
    "urllib3": "2.8.0",
}
NETBOX_MATRIX_SECURITY_FLOORS = {
    "v4.5.8-py312-linux-x86_64.in": {
        "django": "5.2.17",
        **_COMMON_NETBOX_MATRIX_FLOORS,
    },
    "v4.5.10-py312-linux-x86_64.in": {
        "django": "5.2.17",
        **_COMMON_NETBOX_MATRIX_FLOORS,
    },
    "v4.6.0-py312-linux-x86_64.in": {
        "django": "6.0.8",
        **_COMMON_NETBOX_MATRIX_FLOORS,
    },
    "v4.6.6-py312-linux-x86_64.in": {
        "django": "6.0.8",
        **_COMMON_NETBOX_MATRIX_FLOORS,
    },
    "v4.7.0-beta2-py312-linux-x86_64.in": {
        "django": "6.1.1",
        **_COMMON_NETBOX_MATRIX_FLOORS,
    },
    "v4.7.0-py312-linux-x86_64.in": {
        "django": "6.1.1",
        **_COMMON_NETBOX_MATRIX_FLOORS,
    },
}
NETBOX_MATRIX_AUTH_CHAINS = {
    "v4.5.8-py312-linux-x86_64.in": {
        "oauthlib": "4.0.0",
        "pyjwt": "2.15.0",
        "requests": "2.34.2",
        "social-auth-app-django": "6.0.1",
        "social-auth-core": "5.1.0",
        "urllib3": "2.8.0",
    },
    "v4.5.10-py312-linux-x86_64.in": {
        "oauthlib": "4.0.0",
        "pyjwt": "2.15.0",
        "requests": "2.34.2",
        "social-auth-app-django": "6.0.1",
        "social-auth-core": "5.1.0",
        "urllib3": "2.8.0",
    },
    "v4.6.0-py312-linux-x86_64.in": {
        "oauthlib": "4.0.0",
        "pyjwt": "2.15.0",
        "requests": "2.34.2",
        "social-auth-app-django": "6.0.1",
        "social-auth-core": "5.1.0",
        "urllib3": "2.8.0",
    },
    "v4.6.6-py312-linux-x86_64.in": {
        "oauthlib": "4.0.0",
        "pyjwt": "2.15.0",
        "requests": "2.34.2",
        "social-auth-app-django": "6.0.1",
        "social-auth-core": "5.1.0",
        "urllib3": "2.8.0",
    },
    "v4.7.0-beta2-py312-linux-x86_64.in": {
        "oauthlib": "4.0.0",
        "pyjwt": "2.15.0",
        "requests": "2.34.2",
        "social-auth-app-django": "6.0.1",
        "social-auth-core": "5.1.0",
        "urllib3": "2.8.0",
    },
    "v4.7.0-py312-linux-x86_64.in": {
        "oauthlib": "4.0.0",
        "pyjwt": "2.15.0",
        "requests": "2.34.2",
        "social-auth-app-django": "6.0.1",
        "social-auth-core": "5.1.0",
        "urllib3": "2.8.0",
    },
}
NETBOX_MATRIX_SECURITY_ADVISORIES = {
    "django": (
        "PYSEC-2026-3717",
        "GHSA-3h9f-r86x-qvjx",
        "GHSA-5hrc-gvxj-w55p",
        "GHSA-7h2m-m8vj-598h",
        "GHSA-8cjm-8mp7-r2xf",
        "GHSA-8qcx-xf44-272x",
        "GHSA-923m-gv2p-w5qp",
        "GHSA-crhf-3pfg-w68w",
        "GHSA-h7pc-vwp9-298g",
        "GHSA-mm6v-q8q9-pgcf",
        "GHSA-qpc8-7fxc-cm4p",
        "GHSA-w26r-rmm8-9c29",
    ),
    "djangorestframework": ("GHSA-2m8g-3cmr-wg3w", "GHSA-g47c-3xmw-q6m2"),
    "mkdocs-material": ("GHSA-xvg9-69gf-fjrf",),
    "oauthlib": ("GHSA-hj66-6f7g-4r5v", "GHSA-xpv3-w29h-x7cv"),
    "pillow": (
        "GHSA-45hq-cxwh-f6vc",
        "GHSA-4x4j-2g7c-83w6",
        "GHSA-5x94-69rx-g8h2",
        "GHSA-62p4-gmf7-7g93",
        "GHSA-6r8x-57c9-28j4",
        "GHSA-8v84-f9pq-wr9x",
        "GHSA-9hw9-ch79-4vh6",
        "GHSA-fj7v-r99m-22gq",
        "GHSA-jjj6-mw9f-p565",
        "GHSA-pg7v-jwj7-p798",
        "GHSA-phj9-mv4w-65pm",
        "GHSA-vjc4-5qp5-m44j",
        "GHSA-xj96-63gp-2gmr",
        "GHSA-8g5g-8vmr-9782",
        "GHSA-c6hw-5grf-ff96",
        "GHSA-p4wg-p73j-c528",
        "GHSA-pchr-8j38-3x4p",
        "GHSA-q45j-58j2-45rg",
        "GHSA-65qm-jvmh-6pqg",
        "GHSA-58r4-6rv3-gfh8",
        "GHSA-462x-pgg6-55fp",
        "GHSA-vx6w-vv9f-6gvg",
    ),
    "pyjwt": (
        "GHSA-2gx3-rcp4-g85q",
        "GHSA-42vr-xj54-vc7v",
        "GHSA-8wjv-2p76-3863",
        "GHSA-9j54-fg26-wv3r",
        "GHSA-9v7f-9g4p-ffgj",
        "GHSA-ffc3-869f-jxw9",
        "GHSA-gvp8-978c-rx2q",
        "GHSA-hxm8-2xgr-2p9m",
        "GHSA-jwrc-g2q2-pq5p",
        "GHSA-p4g4-x82p-q773",
        "GHSA-r6x4-923q-g947",
        "GHSA-w2cx-738m-mc7w",
        "GHSA-w6j9-cwv2-h6wq",
    ),
    "strawberry-graphql": (
        "GHSA-fr49-mhgj-crfc",
        "GHSA-qfwv-87qj-98xq",
        "GHSA-x97m-qp5c-w9xj",
        "GHSA-pfvf-fwfp-25mp",
        "GHSA-m952-2w3f-6r8h",
    ),
    "tablib": ("GHSA-gqgw-jghv-mxwx",),
    "urllib3": (
        "GHSA-8988-9cw3-xx77",
        "GHSA-gh4c-6fx4-qh6g",
        "GHSA-vxq7-64xx-v4gw",
    ),
}


# Packages that no NetBox matrix input (``v*.in``) declares, so the input-floor
# checks above cannot see them. Each generated lock that names one must pin it
# at or above the floor, and the locks listed in ``required_in`` must name it at
# all: a lock that silently drops a package it still installs would otherwise
# pass. Transcribed from the published advisories through 2026-10-21.
_ALL_MATRIX_LOCKS = (
    "v4.5.8-py312-linux-x86_64.txt",
    "v4.5.10-py312-linux-x86_64.txt",
    "v4.6.0-py312-linux-x86_64.txt",
    "v4.6.6-py312-linux-x86_64.txt",
    "v4.6.6-pdm-3408441672bf-py312-linux-x86_64.txt",
    "v4.7.0-beta2-py312-linux-x86_64.txt",
    "v4.7.0-py312-linux-x86_64.txt",
    "v4.7.0-all-companions-py312-linux-x86_64.txt",
    "v4.7.0-openbao-58677ef-py312-linux-x86_64.txt",
)
UV_LOCK = "uv.lock"
TRANSITIVE_LOCK_FLOORS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    # package: (floor, advisories, locks that must pin it)
    "certifi": (
        "2026.10.19",
        ("GHSA-6q48-6c7w-9gw2",),  # emSign roots with compromised intermediates
        (*_ALL_MATRIX_LOCKS, UV_LOCK),
    ),
    "aiohttp": (
        "3.14.4",
        SECURITY_FLOORS["aiohttp"].advisories,
        (
            "v4.6.6-pdm-3408441672bf-py312-linux-x86_64.txt",
            "v4.7.0-all-companions-py312-linux-x86_64.txt",
            UV_LOCK,
        ),
    ),
    "multidict": (
        "6.9.1",
        ("GHSA-54p9-h82j-f925",),  # items-view union/subtraction reference leak
        (
            "v4.6.6-pdm-3408441672bf-py312-linux-x86_64.txt",
            "v4.7.0-all-companions-py312-linux-x86_64.txt",
            UV_LOCK,
        ),
    ),
}


def _load_pyproject() -> dict:
    """Parse ``pyproject.toml``, failing loudly if it cannot be read."""
    if not PYPROJECT.is_file():
        pytest.fail(f"pyproject.toml is missing at {PYPROJECT}")
    try:
        return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        pytest.fail(f"pyproject.toml is not valid TOML: {exc}")


def _canonical(name: str) -> str:
    """Normalise a distribution name per PEP 503.

    Every name comparison in this module goes through here, so that a package
    spelled ``pymdown_extensions`` in one manifest and ``pymdown-extensions`` in
    another is still recognised as the same distribution.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _pyproject_list(path: tuple[str, ...], origin: str) -> list[str]:
    """Read a list of requirement strings out of ``pyproject.toml``."""
    node: object = _load_pyproject()
    for key in path:
        if not isinstance(node, dict) or key not in node:
            pytest.fail(f"pyproject.toml has no {'.'.join(path)} table ({origin})")
        node = node[key]
    if not isinstance(node, list) or not node:
        pytest.fail(f"{origin}: {'.'.join(path)} is not a non-empty list")
    return [str(item) for item in node]


def _runtime_dependency_specs() -> list[str]:
    return _pyproject_list(("project", "dependencies"), RUNTIME_DEPENDENCIES)


def _cli_extra_specs() -> list[str]:
    return _pyproject_list(("project", "optional-dependencies", "cli"), CLI_EXTRA)


def _dev_extra_specs() -> list[str]:
    return _pyproject_list(("project", "optional-dependencies", "dev"), DEV_EXTRA)


def _dev_group_specs() -> list[str]:
    return _pyproject_list(("dependency-groups", "dev"), DEV_GROUP)


# pip directives this line parser cannot see through. ``-r``/``-c`` pull in
# whole files; ``-e``/``--editable`` *is* an install requirement, so ignoring it
# would let an editable VCS reference to an affected version slip past. If any
# appears, the guard can no longer prove the full install set is safe and must
# fail rather than report success on the subset it can read.
_OPAQUE_DIRECTIVES = ("-r", "-c", "--requirement", "--constraint", "-e", "--editable")


def _docs_specs() -> list[str]:
    if not REQUIREMENTS_DOCS.is_file():
        pytest.fail(f"requirements-docs.txt is missing at {REQUIREMENTS_DOCS}")

    # Join backslash continuations so a requirement split across lines is not
    # read as two unparseable fragments.
    raw_text = REQUIREMENTS_DOCS.read_text(encoding="utf-8").replace("\\\n", " ")

    specs = []
    for line in raw_text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        if stripped.startswith(_OPAQUE_DIRECTIVES):
            pytest.fail(
                f"requirements-docs.txt uses the install directive {stripped!r}, "
                f"which this guard cannot see through. It can no longer prove "
                f"the full install set is safe. Teach it to resolve the "
                f"directive before adding one."
            )
        if stripped.startswith("-"):
            # A pip *option* (--index-url, --find-links, --pre, ...). It
            # declares no requirement, so it is irrelevant to a floor check.
            continue
        specs.append(stripped)

    if not specs:
        pytest.fail("requirements-docs.txt contains no requirements to check")
    return specs


_SPEC_SOURCES = {
    RUNTIME_DEPENDENCIES: _runtime_dependency_specs,
    CLI_EXTRA: _cli_extra_specs,
    DEV_GROUP: _dev_group_specs,
    DEV_EXTRA: _dev_extra_specs,
    DOCS_REQUIREMENTS: _docs_specs,
}

# Operators that can establish a lower bound. ``!=`` is deliberately excluded:
# excluding known-bad versions one at a time is exactly the bypass this guard
# exists to reject.
_LOWER_BOUND_OPERATORS = frozenset({">=", ">", "==", "===", "~="})


def _effective_lower_bound(specifier: SpecifierSet) -> Version | None:
    """Return the lowest version the specifier can admit, or ``None``.

    ``None`` means the specifier establishes no lower bound at all -- an
    unpinned or exclusion-only requirement -- which callers must treat as
    unsafe rather than as "no problem found".

    Clauses are ANDed, so the effective bound is the greatest of the individual
    bounds. A trailing ``.*`` wildcard is truncated, which is the conservative
    reading: ``==3.14.*`` can admit 3.14.0.
    """
    bounds: list[Version] = []
    for clause in specifier:
        if clause.operator not in _LOWER_BOUND_OPERATORS:
            continue
        raw = clause.version
        if raw.endswith(".*"):
            raw = raw[: -len(".*")]
        try:
            bounds.append(Version(raw))
        except InvalidVersion:
            # Unparseable pin: we cannot reason about it, so fail closed.
            return None
    return max(bounds) if bounds else None


def _supported_python_versions() -> tuple[str, ...]:
    """Python versions to evaluate markers against, from ``requires-python``.

    Derived rather than hardcoded so the matrix cannot drift out of step with
    the project's own floor: if ``requires-python`` were ever lowered, a
    hardcoded list would stop testing the newly supported interpreters and a
    marker that is inert on them would pass unnoticed.

    Three minor versions past the floor are included so a marker that holds only
    on today's interpreters -- and would silently lapse on the next one -- is
    still caught.
    """
    data = _load_pyproject()
    raw = data.get("project", {}).get("requires-python")
    if not isinstance(raw, str) or not raw.strip():
        pytest.fail(
            "pyproject.toml declares no requires-python, so the set of "
            "supported interpreters cannot be derived and markers cannot be "
            "checked against it."
        )
    lower = _effective_lower_bound(SpecifierSet(raw))
    if lower is None:
        pytest.fail(f"requires-python {raw!r} establishes no lower bound")
    major, minor = lower.release[0], (lower.release[1] if len(lower.release) > 1 else 0)
    return tuple(f"{major}.{minor + offset}" for offset in range(4))


# Environments a declaration must hold in to count as a floor: every supported
# interpreter crossed with the platform axes a marker can legally branch on.
def _supported_environments() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "python_version": py,
            "python_full_version": f"{py}.0",
            "implementation_name": "cpython",
            "implementation_version": f"{py}.0",
            "sys_platform": sys_platform,
            "os_name": "nt" if sys_platform == "win32" else "posix",
            "platform_system": {
                "linux": "Linux",
                "darwin": "Darwin",
                "win32": "Windows",
            }[sys_platform],
            "platform_machine": machine,
        }
        for py in _supported_python_versions()
        for sys_platform in ("linux", "darwin", "win32")
        for machine in ("x86_64", "aarch64")
    )


def _inactive_environment(requirement: Requirement) -> dict[str, str] | None:
    """Return a supported environment where this declaration does not apply.

    A requirement carrying an environment marker only constrains the
    environments its marker selects. A marker that is false somewhere -- or
    everywhere, as in ``pymdown-extensions>=11.0.1; python_version < "3"`` --
    leaves the floor inert there, and whatever a transitive dependency asks for
    governs instead. So a marker is acceptable only when it holds across every
    supported environment; otherwise this returns the first counterexample.
    """
    marker = requirement.marker
    if marker is None:
        return None

    for environment in _supported_environments():
        try:
            active = marker.evaluate(environment)
        except Exception:  # noqa: BLE001 - an unevaluable marker must fail
            return environment
        if not active:
            return environment
    return None


def _requirement_from(specs: list[str], package: str, origin: str) -> Requirement:
    """Return the single requirement for ``package``, failing closed."""
    matches = []
    for raw in specs:
        try:
            requirement = Requirement(raw)
        except Exception as exc:  # noqa: BLE001 - any parse failure must fail
            pytest.fail(f"{origin}: cannot parse requirement {raw!r}: {exc}")
        if _canonical(requirement.name) == _canonical(package):
            matches.append(requirement)

    if not matches:
        pytest.fail(
            f"{origin}: {package!r} is not declared, so its floor cannot be "
            f"enforced there. A transitive dependency is still installed -- an "
            f"undeclared package means whatever upstream asks for wins, which "
            f"is how an affected version gets in. Declare it explicitly."
        )
    if len(matches) > 1:
        pytest.fail(
            f"{origin}: {package!r} is declared {len(matches)} times "
            f"({[str(m) for m in matches]}); the effective floor is ambiguous."
        )
    return matches[0]


@pytest.mark.parametrize(
    ("package", "location"),
    [
        (package, location)
        for package, floor in sorted(SECURITY_FLOORS.items())
        for location in floor.declared_in
    ],
)
def test_declared_floor_establishes_a_safe_lower_bound(
    package: str, location: str
) -> None:
    """Every manifest that installs the package must floor it above the range.

    This is the primary assertion. It checks the *structure* of the specifier,
    so an exclusion-only requirement that dodges the sampled versions below
    cannot pass.
    """
    floor = SECURITY_FLOORS[package]
    required = Version(floor.floor)
    requirement = _requirement_from(_SPEC_SOURCES[location](), package, location)

    # A declaration guarded by a marker that is false somewhere is not a floor
    # there, so check that before believing the specifier.
    inactive = _inactive_environment(requirement)
    assert inactive is None, (
        f"{location}: {requirement} carries an environment marker that is not "
        f"active for {floor.name} on Python {inactive['python_version']} / "  # type: ignore[index]
        f"{inactive['sys_platform']} / {inactive['platform_machine']}, so the "  # type: ignore[index]
        f"floor is inert there and whatever a transitive dependency asks for "
        f"governs instead. Declare the floor unconditionally."
    )

    lower = _effective_lower_bound(requirement.specifier)
    assert lower is not None, (
        f"{location}: {requirement} establishes no lower bound on "
        f"{floor.name}, so it admits every version covered by "
        f"{', '.join(floor.advisories)}. Declare >={floor.floor}."
    )
    assert lower >= required, (
        f"{location}: {requirement} can admit {floor.name} {lower}, below the "
        f"security floor {floor.floor} required by "
        f"{', '.join(floor.advisories)}. Note that '!=' exclusions do not count "
        f"as a floor -- declare >={floor.floor} (or a higher exact or "
        f"compatible-release pin)."
    )


@pytest.mark.parametrize(
    ("package", "location"),
    [
        (package, location)
        for package, floor in sorted(SECURITY_FLOORS.items())
        for location in floor.declared_in
    ],
)
def test_declared_floor_refuses_known_affected_versions(
    package: str, location: str
) -> None:
    """Back the structural check with concrete versions from the advisories.

    Redundant with the bound check by design: this one names a real affected
    version in its failure message, which makes a regression obvious.
    """
    floor = SECURITY_FLOORS[package]
    requirement = _requirement_from(_SPEC_SOURCES[location](), package, location)

    for bad in floor.affected:
        assert not requirement.specifier.contains(Version(bad), prereleases=True), (
            f"{location}: {requirement} still admits {floor.name} {bad}, which "
            f"is covered by {', '.join(floor.advisories)}."
        )


def test_locked_versions_satisfy_the_declared_floors() -> None:
    """``uv.lock`` must pin at or above every declared floor.

    Catches the inverse mistake: raising a declared floor while leaving the lock
    pinned below it, which makes ``uv sync --locked`` inconsistent.
    """
    locked = _uv_lock_versions()

    for package, floor in sorted(SECURITY_FLOORS.items()):
        key = _canonical(package)
        if key not in locked:
            pytest.fail(
                f"uv.lock does not pin {package!r}, so its floor is unverifiable"
            )
        assert locked[key] >= Version(floor.floor), (
            f"uv.lock pins {package} {locked[key]}, below the required security "
            f"floor {floor.floor} ({', '.join(floor.advisories)})."
        )


def _uv_lock_versions() -> dict[str, Version]:
    """Read every ``[[package]]`` pin from ``uv.lock``, failing loudly."""
    lock_path = ROOT / UV_LOCK
    if not lock_path.is_file():
        pytest.fail(f"uv.lock is missing at {lock_path}")
    try:
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        pytest.fail(f"uv.lock is not valid TOML: {exc}")

    packages = lock.get("package")
    if not isinstance(packages, list) or not packages:
        pytest.fail("uv.lock has no [[package]] entries")

    return _lowest_locked_versions(packages)


def _lowest_locked_versions(packages: list[object]) -> dict[str, Version]:
    """Map each ``uv.lock`` package to the lowest version it pins.

    A universal lock may hold several entries for one name, one per resolved
    environment. A floor holds only when every entry clears it, so the lowest
    version is the one to check; keeping any other entry would let a vulnerable
    split hide behind a safe one.
    """
    lowest: dict[str, Version] = {}
    for index, entry in enumerate(packages):
        if not isinstance(entry, dict):
            pytest.fail(f"uv.lock [[package]] entry {index} is not a table")
        name = entry.get("name")
        raw_version = entry.get("version")
        if not isinstance(name, str) or not isinstance(raw_version, str):
            pytest.fail(
                f"uv.lock [[package]] entry {index} has no string name and version"
            )
        try:
            version = Version(raw_version)
        except InvalidVersion:
            pytest.fail(f"uv.lock pins {name} to invalid version {raw_version!r}")
        key = _canonical(name)
        if key not in lowest or version < lowest[key]:
            lowest[key] = version
    return lowest


def _transitive_lock_versions(lock_name: str) -> dict[str, Version]:
    """Read the pins of ``uv.lock`` or of one generated matrix lock."""
    if lock_name == UV_LOCK:
        return _uv_lock_versions()
    return _matrix_lock_versions(NETBOX_REQUIREMENTS_DIR / lock_name)


def _assert_transitive_lock_floors(
    lock_name: str, lock_versions: dict[str, Version]
) -> None:
    """Require one lock to clear every transitive floor that applies to it."""
    for package, (floor_raw, advisories, required_in) in sorted(
        TRANSITIVE_LOCK_FLOORS.items()
    ):
        locked = lock_versions.get(_canonical(package))
        if locked is None:
            assert lock_name not in required_in, (
                f"{lock_name} does not pin {package}, so its "
                f"{floor_raw} security floor is unverifiable"
            )
            continue
        assert locked >= Version(floor_raw), (
            f"{lock_name} pins {package} {locked}, below the {floor_raw} "
            f"security floor required by {', '.join(advisories)}"
        )


def test_transitive_floor_table_covers_every_generated_matrix_lock() -> None:
    """A new generated lock must be added to the transitive-floor table."""
    on_disk = {path.name for path in NETBOX_REQUIREMENTS_DIR.glob("*.txt")}
    assert on_disk, f"no generated matrix locks found in {NETBOX_REQUIREMENTS_DIR}"
    assert on_disk == set(_ALL_MATRIX_LOCKS)


@pytest.mark.parametrize("lock_name", [*_ALL_MATRIX_LOCKS, UV_LOCK])
def test_locks_clear_transitive_security_floors(lock_name: str) -> None:
    """Every lock pins transitive advisory packages at or above their floor."""
    _assert_transitive_lock_floors(lock_name, _transitive_lock_versions(lock_name))


@pytest.mark.parametrize(
    ("package", "vulnerable"),
    [
        ("certifi", "2026.7.22"),
        ("aiohttp", "3.14.3"),
        ("multidict", "6.9.0"),
    ],
)
@pytest.mark.parametrize("lock_name", [*_ALL_MATRIX_LOCKS, UV_LOCK])
def test_transitive_lock_downgrade_is_rejected(
    lock_name: str, package: str, vulnerable: str
) -> None:
    """A lock moved back into an advisory range fails the transitive guard."""
    required_in = TRANSITIVE_LOCK_FLOORS[package][2]
    lock_versions = dict(_transitive_lock_versions(lock_name))
    if _canonical(package) not in lock_versions and lock_name not in required_in:
        pytest.skip(f"{lock_name} legitimately does not install {package}")
    lock_versions[_canonical(package)] = Version(vulnerable)
    with pytest.raises(AssertionError, match=f"(?i){package}"):
        _assert_transitive_lock_floors(lock_name, lock_versions)


def test_certifi_is_not_a_shipped_runtime_dependency() -> None:
    """certifi stays out of the wheel's Requires-Dist on purpose.

    The plugin installs into an existing NetBox environment that owns certifi.
    A runtime floor would make a package deploy that verifies every
    Requires-Dist against that environment refuse the plugin until NetBox is
    upgraded. The floor lives in the documentation install and the locks.
    """
    names = {_canonical(Requirement(spec).name) for spec in _runtime_dependency_specs()}
    assert "certifi" not in names


@pytest.mark.parametrize("vulnerable_first", [True, False])
def test_uv_lock_duplicate_entries_are_judged_by_the_lowest_version(
    vulnerable_first: bool,
) -> None:
    """A vulnerable split entry cannot hide behind a safe one in either order."""
    packages = tomllib.loads((ROOT / UV_LOCK).read_text(encoding="utf-8"))["package"]
    vulnerable = {"name": "certifi", "version": "2026.7.22"}
    entries = [vulnerable, *packages] if vulnerable_first else [*packages, vulnerable]
    lowest = _lowest_locked_versions(entries)
    assert lowest["certifi"] == Version("2026.7.22")
    with pytest.raises(AssertionError, match="(?i)certifi"):
        _assert_transitive_lock_floors(UV_LOCK, lowest)


@pytest.mark.parametrize(
    "entry",
    [
        "not-a-table",
        {"name": "certifi"},
        {"version": "2026.10.19"},
        {"name": "certifi", "version": "not a version"},
    ],
)
def test_uv_lock_malformed_entries_fail_closed(entry: object) -> None:
    """An entry the guard cannot read is a failure, never silently skipped."""
    with pytest.raises(pytest.fail.Exception):
        _lowest_locked_versions([entry])


@pytest.mark.parametrize("package", sorted(TRANSITIVE_LOCK_FLOORS))
def test_transitive_lock_missing_required_pin_is_rejected(package: str) -> None:
    """Dropping a required transitive pin is a failure, not a pass."""
    lock_name = TRANSITIVE_LOCK_FLOORS[package][2][0]
    lock_versions = dict(_transitive_lock_versions(lock_name))
    assert lock_versions.pop(_canonical(package), None) is not None
    with pytest.raises(AssertionError, match=f"(?i)does not pin {package}"):
        _assert_transitive_lock_floors(lock_name, lock_versions)


def _matrix_input_specs(path: Path) -> list[str]:
    """Read a matrix input whose lines must all be visible requirements."""
    if not path.is_file():
        pytest.fail(f"NetBox matrix input is missing at {path}")
    specs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        if stripped.startswith("-"):
            pytest.fail(
                f"{path}: install directive {stripped!r} hides dependencies "
                "from the matrix security-floor guard"
            )
        specs.append(stripped)
    if not specs:
        pytest.fail(f"NetBox matrix input contains no requirements: {path}")
    return specs


def _matrix_lock_versions(path: Path) -> dict[str, Version]:
    """Read exact top-level pins from one generated, hash-locked matrix file."""
    if not path.is_file():
        pytest.fail(f"NetBox matrix lock is missing at {path}")
    text = path.read_text(encoding="utf-8")
    if "--hash=sha256:" not in text:
        pytest.fail(f"NetBox matrix lock has no artifact hashes: {path}")

    versions: dict[str, Version] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line[:1].isspace():
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^ ]+) \\", line)
        if match is None:
            pytest.fail(
                f"{path}:{line_number}: unsupported top-level install line "
                f"{line!r}; locks may contain only exact index pins"
            )
        package = _canonical(match.group(1))
        if package in versions:
            pytest.fail(f"{path}: duplicate locked package {package!r}")
        versions[package] = Version(match.group(2))
    if not versions:
        pytest.fail(f"NetBox matrix lock contains no exact package pins: {path}")
    return versions


def _assert_matrix_input_matches_lock(
    input_path: Path,
    input_specs: list[str],
    lock_versions: dict[str, Version],
) -> None:
    """Require every direct matrix input declaration to govern its lock pin."""
    seen: set[str] = set()
    for raw in input_specs:
        requirement = Requirement(raw)
        package = _canonical(requirement.name)
        assert requirement.url is None, (
            f"{input_path}: direct URLs are not permitted for {package}; "
            "the reviewed index lock must select the artifact"
        )
        assert requirement.marker is None, (
            f"{input_path}: environment markers are not permitted for {package}; "
            "each fixed Python 3.12/Linux matrix input must apply unconditionally"
        )
        assert package not in seen, f"{input_path}: duplicate input package {package!r}"
        seen.add(package)
        assert package in lock_versions, (
            f"{input_path.with_suffix('.txt')}: missing direct input package {package}"
        )
        locked = lock_versions[package]
        assert not locked.is_prerelease, (
            f"{input_path.with_suffix('.txt')} pins prerelease {package} {locked}"
        )
        assert requirement.specifier.contains(locked, prereleases=False), (
            f"{input_path.with_suffix('.txt')} pins {package} {locked}, which "
            f"does not satisfy its reviewed input declaration {requirement}"
        )


@pytest.mark.parametrize("filename", sorted(NETBOX_MATRIX_SECURITY_FLOORS))
def test_netbox_matrix_inputs_and_locks_enforce_security_floors(
    filename: str,
) -> None:
    """Every reviewed matrix input and generated lock must clear its advisories."""
    input_path = NETBOX_REQUIREMENTS_DIR / filename
    input_specs = _matrix_input_specs(input_path)
    lock_versions = _matrix_lock_versions(input_path.with_suffix(".txt"))
    _assert_matrix_input_matches_lock(input_path, input_specs, lock_versions)

    for package, floor_raw in NETBOX_MATRIX_SECURITY_FLOORS[filename].items():
        floor = Version(floor_raw)
        advisories = ", ".join(NETBOX_MATRIX_SECURITY_ADVISORIES[package])
        requirement = _requirement_from(input_specs, package, str(input_path))
        lower = _effective_lower_bound(requirement.specifier)
        assert lower is not None and lower >= floor, (
            f"{input_path}: {requirement} does not establish the {floor} "
            f"security floor required by {advisories}"
        )
        assert not lower.is_prerelease, (
            f"{input_path}: {requirement} uses a prerelease security floor"
        )

        key = _canonical(package)
        assert key in lock_versions, (
            f"{input_path.with_suffix('.txt')}: missing {package}"
        )
        locked = lock_versions[key]
        assert not locked.is_prerelease, (
            f"{input_path.with_suffix('.txt')} pins prerelease {package} {locked}"
        )
        assert locked >= floor, (
            f"{input_path.with_suffix('.txt')} pins {package} {locked}, below "
            f"the {floor} security floor required by {advisories}"
        )
        assert requirement.specifier.contains(locked, prereleases=False), (
            f"{input_path.with_suffix('.txt')} pins {package} {locked}, which "
            f"does not satisfy its reviewed input declaration {requirement}"
        )

    for package, expected_raw in NETBOX_MATRIX_AUTH_CHAINS[filename].items():
        expected = Version(expected_raw)
        requirement = _requirement_from(input_specs, package, str(input_path))
        assert str(requirement.specifier) == f"=={expected}", (
            f"{input_path}: expected the reviewed authentication-chain pin "
            f"{package}=={expected}, found {requirement}"
        )
        assert lock_versions[_canonical(package)] == expected, (
            f"{input_path.with_suffix('.txt')}: expected the reviewed "
            f"authentication-chain pin {package}=={expected}"
        )


# Composed CI locks that install a companion plugin on top of one NetBox
# matrix input. Each must clear the same floors and authentication chain as
# the base input it extends, or a coherent-looking regeneration could
# reintroduce a vulnerable dependency that only the companion cell installs.
NETBOX_COMPANION_LOCKS = {
    "v4.6.6-pdm-3408441672bf-py312-linux-x86_64.txt": "v4.6.6-py312-linux-x86_64.in",
    "v4.7.0-all-companions-py312-linux-x86_64.txt": "v4.7.0-py312-linux-x86_64.in",
    "v4.7.0-openbao-58677ef-py312-linux-x86_64.txt": "v4.7.0-py312-linux-x86_64.in",
}


def _assert_companion_lock_clears_floors(
    lock_name: str, lock_versions: dict[str, Version]
) -> None:
    """Require a composed lock to satisfy its base input's floors and chain."""
    base = NETBOX_COMPANION_LOCKS[lock_name]
    base_path = NETBOX_REQUIREMENTS_DIR / base
    # Security floors are not monotonic across Django series, so a scalar
    # lower bound is not enough: every reviewed base pin (including the exact
    # Django series) must govern the composed lock as well.
    _assert_matrix_input_matches_lock(
        base_path, _matrix_input_specs(base_path), lock_versions
    )
    for package, floor_raw in NETBOX_MATRIX_SECURITY_FLOORS[base].items():
        locked = lock_versions.get(_canonical(package))
        assert locked is not None, f"{lock_name}: missing {package}"
        assert locked >= Version(floor_raw), (
            f"{lock_name} pins {package} {locked}, below the {floor_raw} "
            f"security floor required by "
            f"{', '.join(NETBOX_MATRIX_SECURITY_ADVISORIES[package])}"
        )
    for package, expected_raw in NETBOX_MATRIX_AUTH_CHAINS[base].items():
        assert lock_versions.get(_canonical(package)) == Version(expected_raw), (
            f"{lock_name}: expected the reviewed authentication-chain pin "
            f"{package}=={expected_raw}"
        )


@pytest.mark.parametrize("lock_name", sorted(NETBOX_COMPANION_LOCKS))
def test_netbox_companion_locks_enforce_security_floors(lock_name: str) -> None:
    """Every composed companion lock clears its base input's advisories."""
    lock_versions = _matrix_lock_versions(NETBOX_REQUIREMENTS_DIR / lock_name)
    _assert_companion_lock_clears_floors(lock_name, lock_versions)


@pytest.mark.parametrize(
    ("package", "vulnerable"),
    [
        ("oauthlib", "3.3.1"),
        ("pyjwt", "2.14.0"),
        ("urllib3", "2.7.0"),
        ("django", "6.0.7"),
        ("django", "6.1.0"),
    ],
)
@pytest.mark.parametrize("lock_name", sorted(NETBOX_COMPANION_LOCKS))
def test_netbox_companion_lock_downgrade_is_rejected(
    lock_name: str, package: str, vulnerable: str
) -> None:
    """A companion lock downgraded to a vulnerable pin fails the guard."""
    lock_versions = dict(_matrix_lock_versions(NETBOX_REQUIREMENTS_DIR / lock_name))
    lock_versions[_canonical(package)] = Version(vulnerable)
    with pytest.raises(AssertionError, match=f"(?i){package}"):
        _assert_companion_lock_clears_floors(lock_name, lock_versions)


@pytest.mark.parametrize(
    ("filename", "vulnerable"),
    [
        ("v4.5.8-py312-linux-x86_64.in", "6.0.7"),
        ("v4.6.6-py312-linux-x86_64.in", "6.1.0"),
    ],
)
def test_netbox_matrix_lock_off_series_django_is_rejected(
    filename: str, vulnerable: str
) -> None:
    """A lock moved to another or vulnerable Django release fails the guard."""
    input_path = NETBOX_REQUIREMENTS_DIR / filename
    lock_versions = dict(_matrix_lock_versions(input_path.with_suffix(".txt")))
    lock_versions["django"] = Version(vulnerable)
    with pytest.raises(AssertionError, match="(?i)django"):
        _assert_matrix_input_matches_lock(
            input_path, _matrix_input_specs(input_path), lock_versions
        )


@pytest.mark.parametrize(
    ("original", "replacement", "message"),
    [
        (
            "social-auth-core==5.1.0",
            "social-auth-core==4.8.7",
            "does not satisfy",
        ),
        (
            "requests==2.34.2",
            'requests==2.34.2; python_version < "3"',
            "environment markers are not permitted",
        ),
        (
            "django-filter==25.2",
            "django-filter @ https://example.invalid/django-filter-0.0.1.tar.gz",
            "direct URLs are not permitted",
        ),
    ],
)
def test_netbox_matrix_input_provenance_bypasses_are_rejected(
    original: str,
    replacement: str,
    message: str,
) -> None:
    """Prove that stale locks, inactive markers, and direct URLs fail closed."""
    input_path = NETBOX_REQUIREMENTS_DIR / "v4.5.10-py312-linux-x86_64.in"
    input_specs = _matrix_input_specs(input_path)
    mutated_specs = [replacement if spec == original else spec for spec in input_specs]
    lock_versions = _matrix_lock_versions(input_path.with_suffix(".txt"))

    with pytest.raises(AssertionError, match=message):
        _assert_matrix_input_matches_lock(input_path, mutated_specs, lock_versions)


@pytest.mark.parametrize("mutation", ["direct-url", "alternate-index"])
def test_netbox_matrix_lock_provenance_bypasses_are_rejected(
    tmp_path: Path, mutation: str
) -> None:
    """Reject non-index artifacts and unreviewed indexes in generated locks."""
    source = NETBOX_REQUIREMENTS_DIR / "v4.5.10-py312-linux-x86_64.txt"
    lock_text = source.read_text(encoding="utf-8")
    if mutation == "direct-url":
        lock_text = lock_text.replace(
            "asgiref==3.12.1 \\",
            "asgiref @ https://example.invalid/asgiref-3.12.1.tar.gz \\",
            1,
        )
    else:
        lock_text = "--extra-index-url https://example.invalid/simple\n" + lock_text

    mutated = tmp_path / "mutated.txt"
    mutated.write_text(lock_text, encoding="utf-8")

    with pytest.raises(
        pytest.fail.Exception, match="unsupported top-level install line"
    ):
        _matrix_lock_versions(mutated)


@pytest.mark.parametrize(
    ("specifier", "expected"),
    [
        # Establishes a real floor.
        (">=3.14.3", "3.14.3"),
        ("==3.14.3", "3.14.3"),
        ("===3.14.3", "3.14.3"),
        ("~=3.14.3", "3.14.3"),
        (">=3.14.3,<4", "3.14.3"),
        # Several lower bounds AND together; the greatest one wins.
        (">=3.13,>=3.14.3", "3.14.3"),
        # A wildcard is read conservatively as its lowest member.
        ("==3.14.*", "3.14"),
        # The bypass this function exists to catch: excluding the known-bad
        # versions individually must NOT read as a floor above them.
        (">=3.13.0,!=3.14.0,!=3.14.1,!=3.14.2", "3.13.0"),
        # Exclusions alone establish nothing.
        ("!=3.14.1", None),
        ("<4", None),
        ("", None),
    ],
)
def test_effective_lower_bound_reads_specifiers_correctly(
    specifier: str, expected: str | None
) -> None:
    """Unit-test the safety predicate itself.

    The whole guard rests on this function, so it is pinned directly rather than
    only through the manifests it happens to be pointed at today.
    """
    bound = _effective_lower_bound(SpecifierSet(specifier))
    assert bound == (None if expected is None else Version(expected))


@pytest.mark.parametrize(
    ("requirement", "always_active"),
    [
        # No marker at all: unconditionally active.
        ("aiohttp>=3.14.3", True),
        # True across every supported environment, so still a real floor. These
        # are deliberately true for *any* plausible matrix rather than only for
        # today's requires-python, so this table tests the predicate and does not
        # quietly become a second assertion about the project's Python floor.
        ('aiohttp>=3.14.3; python_version >= "3"', True),
        ('aiohttp>=3.14.3; implementation_name == "cpython"', True),
        # The reproduced bypass: never true on any supported interpreter.
        ('pymdown-extensions>=11.0.1; python_version < "3"', False),
        # Subtler: true today but false on a supported future interpreter, so
        # the floor would silently lapse.
        ('aiohttp>=3.14.3; python_version < "3.14"', False),
        # Platform-conditional floors are inert on the other platforms.
        ('aiohttp>=3.14.3; sys_platform == "linux"', False),
        ('aiohttp>=3.14.3; platform_machine == "x86_64"', False),
        ('aiohttp>=3.14.3; os_name == "posix"', False),
    ],
)
def test_inactive_environment_markers_are_detected(
    requirement: str, always_active: bool
) -> None:
    """A floor only counts where its marker applies.

    Regression test for a guard fail-open: ``_requirement_from()`` used to
    accept a matching declaration without evaluating its marker, so an inert
    ``; python_version < "3"`` floor passed both assertions while the weaker
    transitive requirement actually governed.
    """
    assert (_inactive_environment(Requirement(requirement)) is None) is always_active


def test_exclusion_only_specifier_is_rejected_even_though_it_dodges_the_samples() -> (
    None
):
    """Regression test for the demonstrated sampled-oracle bypass.

    ``>=3.13.0,!=3.14.0,!=3.14.1,!=3.14.2`` refuses every version in aiohttp's
    ``affected`` list and admits the patched floor, so a sample-only guard
    passes it -- while it still admits the covered 3.13.5. The structural bound
    check is what rejects it, and this test fails if that check is ever
    softened back to sampling.
    """
    floor = SECURITY_FLOORS["aiohttp"]
    bypass = SpecifierSet(">=3.13.0,!=3.14.0,!=3.14.1,!=3.14.2")

    # It really does dodge the old oracle, on both counts.
    assert all(
        not bypass.contains(Version(bad), prereleases=True)
        for bad in ("3.12.15", "3.14.0", "3.14.1", "3.14.2")
    )
    assert bypass.contains(Version(floor.floor), prereleases=True)

    # And it really does still admit an advisory-covered version.
    assert bypass.contains(Version("3.13.5"), prereleases=True)

    # The structural check is therefore the one that must reject it.
    bound = _effective_lower_bound(bypass)
    assert bound is not None and bound < Version(floor.floor)
