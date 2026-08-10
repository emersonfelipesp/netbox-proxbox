"""Guard the declared dependency floors that carry a security meaning.

Bumping ``uv.lock`` protects CI, but the lock is neither shipped in the wheel nor
consulted by ``pip``. What protects an *installed* environment is the floor
declared in ``pyproject.toml`` (and, for the documentation toolchain,
``requirements-docs.txt``). A floor that still admits a version covered by a
published advisory silently re-introduces the vulnerability on the next fresh
resolve, while the lockfile scanner reports nothing.

The oracle here is :data:`SECURITY_FLOORS` — a fixed matrix transcribed once from
the published advisories, not derived from the manifests under test. Each entry
names concrete versions that MUST be rejected, so the assertions cannot be
satisfied by whatever the manifest happens to say.

Design notes, deliberate:

* Manifests are parsed with ``tomllib`` and ``packaging``, never with a
  whole-file regex. A regex that scans the whole document can match a decoy in
  an unrelated table and report a floor that is not the one in force. A false
  floor is worse than no guard, because it reports success.
* Every check **fails closed**. A missing file, an unparseable manifest, an
  absent table, or a dependency that cannot be found is a FAILURE, never a
  ``pytest.skip``. Skipping is reserved for a property that legitimately does not
  apply, never for an inability to evaluate one.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS_DOCS = ROOT / "requirements-docs.txt"


class SecurityFloor:
    """One package's required floor plus the versions it must refuse.

    ``rejected`` is the load-bearing field: it is transcribed from the advisory
    ranges, so the assertion cannot be trivially satisfied by the manifest.
    """

    def __init__(
        self,
        name: str,
        floor: str,
        rejected: tuple[str, ...],
        advisories: tuple[str, ...],
    ) -> None:
        self.name = name
        self.floor = floor
        self.rejected = rejected
        self.advisories = advisories


# Transcribed from the published advisories on 2026-08-10. Do not regenerate
# this from the manifests -- that would make the test assert only that the code
# agrees with itself.
SECURITY_FLOORS: dict[str, SecurityFloor] = {
    "aiohttp": SecurityFloor(
        name="aiohttp",
        floor="3.14.3",
        # GHSA-cq5v-8q36-5273 covers <= 3.14.2; the other two cover <= 3.14.1.
        rejected=("3.12.15", "3.14.0", "3.14.1", "3.14.2"),
        advisories=(
            "GHSA-cq5v-8q36-5273",  # OOB heap read, C HTTP response parser
            "GHSA-mfx4-hv73-q22v",  # request smuggling via WebSocket upgrade
            "GHSA-mq44-7p77-q5h7",  # unnegotiated permessage-deflate
        ),
    ),
}

# ``cryptography`` is deliberately absent. Its advisory (GHSA-g6cj-pr64-35w5)
# covers >= 44.0.0, < 50.0.0, so the declared ``cryptography>=48.0.1`` runtime
# floor does admit affected versions -- but this project's only surface is
# ``Fernet``/``InvalidToken``, which the PKCS#7 ``EnvelopedData`` defect does not
# touch, and raising a *runtime* floor forces an upgrade inside the production
# NetBox virtualenv on deploy. That trade-off is tracked separately rather than
# silently enforced here. Add an entry above when it is decided.


def _load_pyproject() -> dict:
    """Parse ``pyproject.toml``, failing loudly if it cannot be read."""
    if not PYPROJECT.is_file():
        pytest.fail(f"pyproject.toml is missing at {PYPROJECT}")
    try:
        return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        pytest.fail(f"pyproject.toml is not valid TOML: {exc}")


def _requirement_from(specs: list[str], package: str, origin: str) -> Requirement:
    """Return the single requirement for ``package``, failing closed."""
    matches = []
    for raw in specs:
        try:
            requirement = Requirement(raw)
        except Exception as exc:  # noqa: BLE001 - any parse failure must fail
            pytest.fail(f"{origin}: cannot parse requirement {raw!r}: {exc}")
        if requirement.name.lower().replace("_", "-") == package:
            matches.append(requirement)

    if not matches:
        pytest.fail(
            f"{origin}: no requirement found for {package!r}. The guard cannot "
            f"evaluate the floor, so it fails rather than passing vacuously."
        )
    if len(matches) > 1:
        pytest.fail(
            f"{origin}: {package!r} is declared {len(matches)} times "
            f"({[str(m) for m in matches]}); the effective floor is ambiguous."
        )
    return matches[0]


def _cli_extra_specs() -> list[str]:
    data = _load_pyproject()
    extras = data.get("project", {}).get("optional-dependencies")
    if not isinstance(extras, dict):
        pytest.fail("pyproject.toml has no [project.optional-dependencies] table")
    specs = extras.get("cli")
    if not isinstance(specs, list) or not specs:
        pytest.fail(
            "pyproject.toml declares no non-empty 'cli' optional-dependency group"
        )
    return specs


def _docs_specs() -> list[str]:
    if not REQUIREMENTS_DOCS.is_file():
        pytest.fail(f"requirements-docs.txt is missing at {REQUIREMENTS_DOCS}")
    specs = []
    for line in REQUIREMENTS_DOCS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        specs.append(stripped)
    if not specs:
        pytest.fail("requirements-docs.txt contains no requirements to check")
    return specs


def _assert_floor(requirement: Requirement, floor: SecurityFloor, origin: str) -> None:
    """Assert the declared specifier refuses every known-affected version."""
    specifier = requirement.specifier

    for bad in floor.rejected:
        assert not specifier.contains(Version(bad), prereleases=True), (
            f"{origin}: {requirement} still admits {floor.name} {bad}, which is "
            f"covered by {', '.join(floor.advisories)}. Raise the floor to "
            f">={floor.floor}."
        )

    assert specifier.contains(Version(floor.floor), prereleases=True), (
        f"{origin}: {requirement} excludes the patched {floor.name} "
        f"{floor.floor}, so nothing installable satisfies it safely."
    )


@pytest.mark.parametrize("package", sorted(SECURITY_FLOORS))
def test_cli_extra_refuses_affected_versions(package: str) -> None:
    """The shipped ``cli`` extra must not admit an affected release."""
    floor = SECURITY_FLOORS[package]
    requirement = _requirement_from(
        _cli_extra_specs(),
        package,
        "pyproject.toml [project.optional-dependencies].cli",
    )
    _assert_floor(requirement, floor, "pyproject.toml 'cli' extra")


@pytest.mark.parametrize("package", sorted(SECURITY_FLOORS))
def test_requirements_docs_refuses_affected_versions(package: str) -> None:
    """The documentation toolchain must not admit an affected release either.

    ``requirements-docs.txt`` is installed by the documentation workflows, so a
    stale floor here is a real install path, not dead configuration.
    """
    floor = SECURITY_FLOORS[package]
    specs = _docs_specs()
    if not any(Requirement(raw).name.lower() == floor.name for raw in specs):
        # Legitimately absent: this manifest simply does not install the package.
        # That is a property that does not apply, so skipping is correct here --
        # unlike an inability to parse, which fails above.
        pytest.skip(f"requirements-docs.txt does not install {floor.name}")
    requirement = _requirement_from(specs, package, "requirements-docs.txt")
    _assert_floor(requirement, floor, "requirements-docs.txt")


@pytest.mark.parametrize("package", sorted(SECURITY_FLOORS))
def test_cli_extra_and_docs_floors_agree(package: str) -> None:
    """The two manifests must not drift apart on a security floor.

    They previously disagreed (``>=3.14.1`` in the extra versus ``>=3.12.15`` in
    the docs requirements), which is how the stale docs floor survived a bump of
    the extra.
    """
    floor = SECURITY_FLOORS[package]
    docs_specs = _docs_specs()
    if not any(Requirement(raw).name.lower() == floor.name for raw in docs_specs):
        pytest.skip(f"requirements-docs.txt does not install {floor.name}")

    cli_requirement = _requirement_from(
        _cli_extra_specs(),
        package,
        "pyproject.toml [project.optional-dependencies].cli",
    )
    docs_requirement = _requirement_from(docs_specs, package, "requirements-docs.txt")

    assert str(cli_requirement.specifier) == str(docs_requirement.specifier), (
        f"{floor.name} floor drifted: 'cli' extra says "
        f"{cli_requirement.specifier} but requirements-docs.txt says "
        f"{docs_requirement.specifier}."
    )


def test_locked_versions_satisfy_the_declared_floors() -> None:
    """``uv.lock`` must resolve to a version the declared floor accepts.

    Catches the inverse mistake of the one above: raising a floor while leaving
    the lock pinned below it, which makes ``uv sync --locked`` inconsistent.
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
        entry["name"]: entry["version"]
        for entry in packages
        if isinstance(entry, dict) and "name" in entry and "version" in entry
    }

    for package, floor in sorted(SECURITY_FLOORS.items()):
        if package not in locked:
            pytest.fail(
                f"uv.lock does not pin {package!r}, so its floor is unverifiable"
            )
        assert Version(locked[package]) >= Version(floor.floor), (
            f"uv.lock pins {package} {locked[package]}, below the required "
            f"security floor {floor.floor} ({', '.join(floor.advisories)})."
        )
