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

# Location keys. Each names one manifest position a floor can be required in;
# _SPEC_SOURCES maps them to the accessor that reads that position.
CLI_EXTRA = "pyproject.toml [project.optional-dependencies].cli"
DEV_GROUP = "pyproject.toml [dependency-groups].dev"
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


# Transcribed from the published advisories on 2026-08-10. Do not regenerate any
# of this from the manifests -- that would make the tests assert only that the
# code agrees with itself.
SECURITY_FLOORS: dict[str, SecurityFloor] = {
    "aiohttp": SecurityFloor(
        name="aiohttp",
        floor="3.14.3",
        # GHSA-cq5v-8q36-5273 covers <= 3.14.2; the other two cover <= 3.14.1.
        affected=("3.12.15", "3.13.5", "3.14.0", "3.14.1", "3.14.2"),
        advisories=(
            "GHSA-cq5v-8q36-5273",  # OOB heap read, C HTTP response parser
            "GHSA-mfx4-hv73-q22v",  # request smuggling via WebSocket upgrade
            "GHSA-mq44-7p77-q5h7",  # unnegotiated permessage-deflate
        ),
        # Reached by proxbox_cli/client.py in the shipped extra, and installed
        # by the documentation workflows.
        declared_in=(CLI_EXTRA, DOCS_REQUIREMENTS),
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
}

# ``cryptography`` is deliberately absent. Its advisory (GHSA-g6cj-pr64-35w5)
# covers >= 44.0.0, < 50.0.0, so the declared ``cryptography>=48.0.1`` runtime
# floor does admit affected versions -- but this project's only surface is
# ``Fernet``/``InvalidToken``, which the PKCS#7 ``EnvelopedData`` defect does not
# touch, and raising a *runtime* floor changes what an installed NetBox
# deployment resolves on its next deploy. That trade-off is decided separately.
# Add an entry above once it is.


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


def _cli_extra_specs() -> list[str]:
    return _pyproject_list(("project", "optional-dependencies", "cli"), CLI_EXTRA)


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
    CLI_EXTRA: _cli_extra_specs,
    DEV_GROUP: _dev_group_specs,
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
    lock_path = ROOT / "uv.lock"
    if not lock_path.is_file():
        pytest.fail(f"uv.lock is missing at {lock_path}")
    try:
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        pytest.fail(f"uv.lock is not valid TOML: {exc}")

    packages = lock.get("package")
    if not isinstance(packages, list) or not packages:
        pytest.fail("uv.lock has no [[package]] entries")

    locked = {
        _canonical(entry["name"]): entry["version"]
        for entry in packages
        if isinstance(entry, dict) and "name" in entry and "version" in entry
    }

    for package, floor in sorted(SECURITY_FLOORS.items()):
        key = _canonical(package)
        if key not in locked:
            pytest.fail(
                f"uv.lock does not pin {package!r}, so its floor is unverifiable"
            )
        assert Version(locked[key]) >= Version(floor.floor), (
            f"uv.lock pins {package} {locked[key]}, below the required security "
            f"floor {floor.floor} ({', '.join(floor.advisories)})."
        )


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
