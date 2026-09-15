"""Verify standalone VM-console browser assets in built distributions."""

from __future__ import annotations

from pathlib import Path
import sys
import tarfile
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
NOVNC_SOURCE = (
    REPO_ROOT / "netbox_proxbox" / "static" / "netbox_proxbox" / "vendor" / "novnc"
)
PACKAGE_PREFIX = "netbox_proxbox/static/netbox_proxbox/vendor/novnc"


def expected_package_files() -> set[str]:
    """Return the runtime and provenance files required in each archive."""
    manifest = (NOVNC_SOURCE / "RUNTIME_FILES.txt").read_text(encoding="utf-8")
    runtime = {line.strip() for line in manifest.splitlines() if line.strip()}
    return {
        f"{PACKAGE_PREFIX}/{relative_path}"
        for relative_path in {*runtime, "RUNTIME_FILES.txt", "SOURCE.md"}
    }


def wheel_members(path: Path) -> set[str]:
    """Return normalized paths from a wheel archive."""
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def sdist_members(path: Path) -> set[str]:
    """Return paths below the sdist's generated root directory."""
    with tarfile.open(path, mode="r:gz") as archive:
        return {name.split("/", 1)[-1] for name in archive.getnames()}


def require_files(archive: Path, members: set[str], expected: set[str]) -> None:
    """Fail with the exact missing asset paths for one archive."""
    missing = sorted(expected - members)
    if missing:
        joined = "\n  ".join(missing)
        raise SystemExit(f"{archive.name} is missing VM-console assets:\n  {joined}")


def verify_distributions(dist_dir: Path) -> tuple[Path, Path]:
    """Verify the single wheel and sdist produced by a clean package build."""
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit("expected exactly one wheel and one sdist")
    expected = expected_package_files()
    require_files(wheels[0], wheel_members(wheels[0]), expected)
    require_files(sdists[0], sdist_members(sdists[0]), expected)
    return wheels[0], sdists[0]


def main(argv: list[str]) -> int:
    """Run the distribution check from CI or a local release gate."""
    dist_dir = Path(argv[1]).resolve() if len(argv) > 1 else REPO_ROOT / "dist"
    wheel, sdist = verify_distributions(dist_dir)
    print(f"Verified VM-console assets in {wheel.name} and {sdist.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
