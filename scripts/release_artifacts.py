#!/usr/bin/env python3
"""Create, verify, and retrieve one immutable Python release artifact set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_SOURCE_FILES = 50_000
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ReleaseArtifactError(ValueError):
    """The artifact or promotion evidence violates the release contract."""


class RegistryNotFound(ReleaseArtifactError):
    """The registry authoritatively reported the object does not exist.

    Kept distinct from every other registry failure because "absent" and
    "could not be determined" must not be conflated. A timeout, an
    authentication failure, or a corrupt payload all mean the caller does not
    know what is published; treating those as absence and re-uploading strands
    an immutable version on the resulting conflict.
    """


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def canonical_name(value: str) -> str:
    """Return the PEP 503 spelling used by the registry contract."""
    return re.sub(r"[-_.]+", "-", value).lower()


def validate_build_source(*, source: Path, package: str, version: str) -> None:
    """Require a passive Hatchling source tree before building it."""
    pyproject = source / "pyproject.toml"
    metadata = pyproject.lstat()
    if (
        pyproject.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > MAX_RESPONSE_BYTES
    ):
        raise ReleaseArtifactError("Candidate pyproject.toml is unsafe")
    try:
        document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseArtifactError("Candidate pyproject.toml is invalid") from exc

    project = document.get("project")
    build_system = document.get("build-system")
    hatch_build = document.get("tool", {}).get("hatch", {}).get("build")
    expected_hatch_build = {
        "targets": {
            "wheel": {"packages": ["netbox_proxbox", "proxbox_cli"]},
        }
    }
    expected_project_fields = {
        "authors",
        "classifiers",
        "dependencies",
        "description",
        "license",
        "license-files",
        "name",
        "optional-dependencies",
        "readme",
        "requires-python",
        "scripts",
        "urls",
        "version",
    }
    if (
        not isinstance(project, dict)
        or set(project) != expected_project_fields
        or project.get("name") != package
        or project.get("version") != version
        or project.get("readme") != "README.md"
        or project.get("license") != "Apache-2.0"
        or project.get("license-files") != ["LICENSE"]
        or build_system
        != {
            "requires": ["hatchling>=1.27,<1.32"],
            "build-backend": "hatchling.build",
        }
        or hatch_build != expected_hatch_build
    ):
        raise ReleaseArtifactError(
            "Candidate build metadata is not the reviewed passive Hatchling contract"
        )


def _validated_source_file(path: Path, source_root: Path) -> os.stat_result:
    """Return stable metadata for one regular file beneath the source root."""
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size > MAX_ARTIFACT_BYTES
        or not path.resolve(strict=True).is_relative_to(source_root)
    ):
        raise ReleaseArtifactError("Candidate source contains an unsafe file")
    return metadata


def _copy_source_file(
    *, source: Path, destination: Path, metadata: os.stat_result
) -> None:
    """Copy one file through no-follow descriptors and detect replacement."""
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if no_follow == 0:
        raise ReleaseArtifactError("No-follow file access is unavailable")
    source_fd = os.open(source, os.O_RDONLY | no_follow)
    try:
        opened = os.fstat(source_fd)
        if (
            opened.st_dev != metadata.st_dev
            or opened.st_ino != metadata.st_ino
            or opened.st_mode != metadata.st_mode
            or opened.st_size != metadata.st_size
        ):
            raise ReleaseArtifactError("Candidate source changed while being copied")
        target_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | no_follow,
            0o600 | (metadata.st_mode & 0o111),
        )
        try:
            while chunk := os.read(source_fd, 1024 * 1024):
                remaining = memoryview(chunk)
                while remaining:
                    remaining = remaining[os.write(target_fd, remaining) :]
        finally:
            os.close(target_fd)
    finally:
        os.close(source_fd)


def sanitize_build_source(
    *, source: Path, destination: Path, package: str, version: str
) -> None:
    """Copy a bounded regular-file source tree for passive package building."""
    source_root = source.resolve(strict=True)
    destination_root = destination.resolve(strict=False)
    if source.is_symlink() or not source_root.is_dir() or destination.exists():
        raise ReleaseArtifactError(
            "Candidate source or sanitized destination is unsafe"
        )
    if destination_root == source_root or destination_root.is_relative_to(source_root):
        raise ReleaseArtifactError(
            "Sanitized destination must be outside candidate source"
        )

    files: list[tuple[Path, Path, os.stat_result]] = []
    total_size = 0
    for current, directories, names in os.walk(source_root, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(name for name in directories if name != ".git")
        for name in directories:
            directory = current_path / name
            metadata = directory.lstat()
            if directory.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise ReleaseArtifactError(
                    "Candidate source contains an unsafe directory"
                )
        for name in sorted(names):
            if name == ".git":
                continue
            path = current_path / name
            metadata = _validated_source_file(path, source_root)
            total_size += metadata.st_size
            relative = path.relative_to(source_root)
            files.append((path, relative, metadata))
            if len(files) > MAX_SOURCE_FILES or total_size > MAX_SOURCE_BYTES:
                raise ReleaseArtifactError(
                    "Candidate source exceeds its bounded inventory"
                )

    destination.mkdir(mode=0o700)
    for path, relative, metadata in files:
        target = destination / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _copy_source_file(source=path, destination=target, metadata=metadata)
    validate_build_source(source=destination, package=package, version=version)


def _is_release_tag_ruleset(value: object, repository: str) -> bool:
    """Return whether one ruleset makes release-tag reservations immutable."""
    if not isinstance(value, dict):
        return False
    if value.get("source_type") != "Repository" or value.get("source") != repository:
        return False
    if value.get("target") != "tag" or value.get("enforcement") != "active":
        return False
    if value.get("bypass_actors") != []:
        return False
    conditions = value.get("conditions")
    if not isinstance(conditions, dict):
        return False
    ref_name = conditions.get("ref_name")
    if ref_name != {"exclude": [], "include": ["refs/tags/v*"]}:
        return False
    rules = value.get("rules")
    if not isinstance(rules, list):
        return False
    rule_types = {rule.get("type") for rule in rules if isinstance(rule, dict)}
    return {"deletion", "non_fast_forward"}.issubset(rule_types)


def validate_github_tag_rulesets(*, rulesets: Path, repository: str) -> None:
    """Require an active, no-bypass immutable release-tag ruleset."""
    if not rulesets.is_dir() or rulesets.is_symlink():
        raise ReleaseArtifactError("GitHub ruleset directory is unsafe")
    for path in sorted(rulesets.iterdir()):
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > MAX_RESPONSE_BYTES
        ):
            raise ReleaseArtifactError("GitHub ruleset response is unsafe")
        try:
            value = json.loads(path.read_bytes())
        except json.JSONDecodeError as exc:
            raise ReleaseArtifactError("GitHub ruleset response is not JSON") from exc
        if _is_release_tag_ruleset(value, repository):
            return
    raise ReleaseArtifactError(
        "No active no-bypass ruleset protects release tags from update and deletion"
    )


def _record(path: Path) -> dict[str, object]:
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or SAFE_NAME_RE.fullmatch(path.name) is None
        or metadata.st_size > MAX_ARTIFACT_BYTES
    ):
        raise ReleaseArtifactError(f"Unsafe release artifact: {path.name!r}")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_ARTIFACT_BYTES:
                raise ReleaseArtifactError("Release artifact exceeds its size bound")
            digest.update(chunk)
    return {"name": path.name, "sha256": digest.hexdigest(), "size": size}


def _manifest_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def create_manifest(
    *, dist: Path, package: str, version: str, source_sha: str
) -> dict[str, Any]:
    """Describe exactly one wheel and one source distribution."""
    if SHA_RE.fullmatch(source_sha) is None:
        raise ReleaseArtifactError("Source SHA must be canonical lowercase 40-hex")
    files = sorted(path for path in dist.iterdir() if path.is_file())
    wheel = [path for path in files if path.name.endswith(".whl")]
    sdist = [path for path in files if path.name.endswith(".tar.gz")]
    if len(files) != 2 or len(wheel) != 1 or len(sdist) != 1:
        raise ReleaseArtifactError(
            "Release set must contain exactly one wheel and one sdist"
        )
    normalized = canonical_name(package).replace("-", "_")
    expected_prefix = f"{normalized}-{version}"
    if not all(path.name.startswith(expected_prefix) for path in files):
        raise ReleaseArtifactError("Artifact filename does not match package/version")
    return {
        "artifacts": [_record(path) for path in files],
        "package": canonical_name(package),
        "schema": 1,
        "source_sha": source_sha,
        "version": version,
    }


def write_manifest(
    *, dist: Path, package: str, version: str, source_sha: str, output: Path
) -> dict[str, Any]:
    """Create a canonical manifest and return it."""
    manifest = create_manifest(
        dist=dist, package=package, version=version, source_sha=source_sha
    )
    output.write_bytes(_manifest_bytes(manifest))
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    """Load an exact-schema canonical manifest."""
    raw = path.read_bytes()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ReleaseArtifactError("Manifest exceeds its size bound")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReleaseArtifactError("Manifest is not valid JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "artifacts",
        "package",
        "schema",
        "source_sha",
        "version",
    }:
        raise ReleaseArtifactError("Manifest schema is not exact")
    if value.get("schema") != 1 or _manifest_bytes(value) != raw:
        raise ReleaseArtifactError("Manifest is not canonical schema 1 JSON")
    return value


def verify_manifest(
    *, manifest_path: Path, dist: Path, package: str, version: str, source_sha: str
) -> dict[str, Any]:
    """Require a manifest to match independently hashed local files."""
    expected = create_manifest(
        dist=dist, package=package, version=version, source_sha=source_sha
    )
    actual = load_manifest(manifest_path)
    if actual != expected:
        raise ReleaseArtifactError("Manifest does not match the local artifact bytes")
    return actual


def manifest_sha256(manifest: dict[str, Any]) -> str:
    """Return the digest operators place in final promotion evidence."""
    return hashlib.sha256(_manifest_bytes(manifest)).hexdigest()


def release_manifest_package(manifest: dict[str, Any]) -> str:
    """Return the immutable generic-package identity for build provenance."""
    return f"{manifest['package']}-release-manifest"


def _request(
    url: str,
    *,
    token: str,
    maximum: int,
    method: str = "GET",
    payload: bytes | None = None,
) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "git.nmulti.cloud":
        raise ReleaseArtifactError("Only the canonical HTTPS Gitea origin is allowed")
    headers = {"Accept": "application/json", "User-Agent": "release-artifacts/1"}
    if token:
        headers["Authorization"] = f"token {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.build_opener(_NoRedirect).open(
            request, timeout=30
        ) as response:
            if not 200 <= response.status < 300:
                raise ReleaseArtifactError(f"Registry returned HTTP {response.status}")
            content = response.read(maximum + 1)
    except urllib.error.HTTPError as exc:
        # Only an authenticated 404 is evidence of absence. Everything else --
        # 401, 403, 5xx -- means the state is unknown, and callers that decide
        # whether to upload must be able to tell the two apart.
        if exc.code == 404:
            raise RegistryNotFound("Registry object does not exist") from exc
        raise ReleaseArtifactError("Registry request failed") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ReleaseArtifactError("Registry request failed") from exc
    if len(content) > maximum:
        raise ReleaseArtifactError("Registry response exceeds its size bound")
    return content


def _quoted(value: str) -> str:
    if SAFE_NAME_RE.fullmatch(value) is None:
        raise ReleaseArtifactError("Registry identity contains unsafe characters")
    return urllib.parse.quote(value, safe="")


def _registry_json(raw: bytes, description: str) -> object:
    """Decode a bounded registry response into the workflow error contract."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReleaseArtifactError(f"Registry {description} is not valid JSON") from exc


def _registry_origin(registry: str) -> str:
    parsed = urllib.parse.urlsplit(registry)
    return f"{parsed.scheme}://{parsed.netloc}"


def verify_gitea_token_identity(*, registry: str, owner: str, token: str) -> None:
    """Require an authenticated registry principal matching the package owner."""
    if not token:
        raise ReleaseArtifactError("Gitea package token is unavailable")
    try:
        identity = json.loads(
            _request(
                f"{_registry_origin(registry)}/api/v1/user",
                token=token,
                maximum=MAX_RESPONSE_BYTES,
            )
        )
    except json.JSONDecodeError as exc:
        raise ReleaseArtifactError("Gitea token identity is not valid JSON") from exc
    if not isinstance(identity, dict) or identity.get("login") != owner:
        raise ReleaseArtifactError("Gitea package token identity does not match owner")


def fetch_gitea_manifest(
    *, owner: str, repository: str, package: str, version: str, token: str = ""
) -> dict[str, Any]:
    """Fetch the original repository-linked manifest created by the builder."""
    manifest_package = f"{canonical_name(package)}-release-manifest"
    base = (
        "https://git.nmulti.cloud/api/v1/packages/"
        f"{_quoted(owner)}/generic/{_quoted(manifest_package)}/{_quoted(version)}"
    )
    metadata = _registry_json(
        _request(base, token=token, maximum=MAX_RESPONSE_BYTES), "metadata"
    )
    files = _registry_json(
        _request(f"{base}/files", token=token, maximum=MAX_RESPONSE_BYTES),
        "file inventory",
    )
    repo = metadata.get("repository") if isinstance(metadata, dict) else None
    if (
        not isinstance(metadata, dict)
        or metadata.get("type") != "generic"
        or metadata.get("name") != manifest_package
        or metadata.get("version") != version
        or not isinstance(repo, dict)
        or repo.get("full_name") != f"{owner}/{repository}"
        or not isinstance(files, list)
        or len(files) != 1
        or not isinstance(files[0], dict)
        or files[0].get("name") != "release-manifest.json"
    ):
        raise ReleaseArtifactError("Gitea release manifest identity is invalid")
    size, digest = files[0].get("size"), files[0].get("sha256")
    if (
        isinstance(size, bool)
        or not isinstance(size, int)
        or not 0 < size <= MAX_RESPONSE_BYTES
        or not isinstance(digest, str)
        or DIGEST_RE.fullmatch(digest.lower()) is None
    ):
        raise ReleaseArtifactError("Gitea release manifest inventory is invalid")
    url = (
        "https://git.nmulti.cloud/api/packages/"
        f"{_quoted(owner)}/generic/{_quoted(manifest_package)}/{_quoted(version)}/"
        "release-manifest.json"
    )
    raw = _request(url, token=token, maximum=size)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest.lower():
        raise ReleaseArtifactError(
            "Downloaded release manifest differs from Gitea inventory"
        )
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReleaseArtifactError("Gitea release manifest is not valid JSON") from exc
    if not isinstance(value, dict) or _manifest_bytes(value) != raw:
        raise ReleaseArtifactError("Gitea release manifest is not canonical JSON")
    return cast(dict[str, Any], value)


def link_gitea_package(
    *,
    registry: str,
    owner: str,
    repository: str,
    package_type: str,
    package: str,
    token: str,
) -> None:
    """Associate a published package with its repository. Idempotent.

    A twine upload does not create this association, but
    ``fetch_gitea_artifacts`` -- the consumer behind both the package deploy
    source and ``promote-final-tag.yml`` -- requires the PyPI package's
    metadata to name ``<owner>/<repository>`` before it will download a single
    artifact. Every version published so far is therefore unlinked and would be
    rejected by that consumer, independently of the manifest.

    The producer creates the link rather than the verifier relaxing the
    requirement: the requirement is what binds published bytes to the
    repository they were built from, and dropping it to match the current
    output would remove a provenance check instead of satisfying it.

    Linking an already-linked package is accepted as success, because this runs
    on a re-run path where the previous attempt may have got this far.
    """
    if not token:
        raise ReleaseArtifactError("Gitea package token is unavailable")
    url = (
        registry
        + f"{_quoted(owner)}/{_quoted(package_type)}/{_quoted(canonical_name(package))}"
        f"/-/link/{_quoted(repository)}"
    )
    try:
        _request(
            url, token=token, maximum=MAX_RESPONSE_BYTES, method="POST", payload=b""
        )
    except ReleaseArtifactError:
        # Fall through to verification rather than failing here: the link may
        # already exist, which some registry versions report as a conflict.
        # verify_gitea_package_artifacts is the actual gate and it requires the
        # link to be present, so a genuinely failed link still fails the run.
        return


def _require_gitea_package_identity(
    *, metadata: object, owner: str, repository: str, package: str, version: str
) -> None:
    """Require the exact package, version, type, and repository association."""
    repo = metadata.get("repository") if isinstance(metadata, dict) else None
    actual = (
        metadata.get("type") if isinstance(metadata, dict) else None,
        canonical_name(str(metadata.get("name", "")))
        if isinstance(metadata, dict)
        else "",
        metadata.get("version") if isinstance(metadata, dict) else None,
        repo.get("full_name") if isinstance(repo, dict) else None,
    )
    if actual != ("pypi", canonical_name(package), version, f"{owner}/{repository}"):
        raise ReleaseArtifactError("Published package identity or link is invalid")


def _manifest_artifact_inventory(
    manifest: dict[str, Any],
) -> dict[str, tuple[int, str]]:
    """Return the validated artifact identity map from one release manifest."""
    expected: dict[str, tuple[int, str]] = {}
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReleaseArtifactError("Release manifest artifact inventory is invalid")
    for record in artifacts:
        if not isinstance(record, dict):
            raise ReleaseArtifactError("Release manifest artifact inventory is invalid")
        name, size, digest = (
            record.get("name"),
            record.get("size"),
            record.get("sha256"),
        )
        if (
            not isinstance(name, str)
            or SAFE_NAME_RE.fullmatch(name) is None
            or name in expected
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not 0 <= size <= MAX_ARTIFACT_BYTES
            or not isinstance(digest, str)
            or DIGEST_RE.fullmatch(digest.lower()) is None
        ):
            raise ReleaseArtifactError("Release manifest artifact inventory is invalid")
        expected[name] = (size, digest.lower())
    return expected


def _published_artifact_inventory(files: object) -> dict[str, tuple[int, str]]:
    """Return the validated artifact identity map from the registry response."""
    if not isinstance(files, list):
        raise ReleaseArtifactError("Published package inventory is invalid")
    published: dict[str, tuple[int, str]] = {}
    for entry in files:
        if not isinstance(entry, dict):
            raise ReleaseArtifactError("Published package inventory is invalid")
        name, size, digest = entry.get("name"), entry.get("size"), entry.get("sha256")
        if (
            not isinstance(name, str)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not isinstance(digest, str)
            or DIGEST_RE.fullmatch(digest.lower()) is None
        ):
            raise ReleaseArtifactError("Published package inventory is invalid")
        if name in published:
            raise ReleaseArtifactError("Published package inventory repeats a file")
        published[name] = (size, digest.lower())
    return published


def _download_and_verify_gitea_artifacts(
    *,
    registry: str,
    owner: str,
    package: str,
    version: str,
    expected: dict[str, tuple[int, str]],
    token: str,
) -> None:
    """Download each published distribution and compare its actual bytes."""
    for name, (size, digest) in expected.items():
        download = (
            f"{_registry_origin(registry)}/api/packages/"
            f"{_quoted(owner)}/pypi/files/{_quoted(canonical_name(package))}/"
            f"{_quoted(version)}/{_quoted(name)}"
        )
        content = _request(download, token=token, maximum=size)
        if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
            raise ReleaseArtifactError(
                "Downloaded artifact differs from the release manifest"
            )


def verify_gitea_package_artifacts(
    *,
    registry: str,
    owner: str,
    repository: str,
    package: str,
    version: str,
    manifest: dict[str, Any],
    token: str,
) -> None:
    """Require the registry to hold the exact downloaded manifest artifact set."""
    base = (
        registry
        + f"{_quoted(owner)}/pypi/{_quoted(canonical_name(package))}/{_quoted(version)}"
    )
    metadata = _registry_json(
        _request(base, token=token, maximum=MAX_RESPONSE_BYTES), "metadata"
    )
    files = _registry_json(
        _request(f"{base}/files", token=token, maximum=MAX_RESPONSE_BYTES),
        "file inventory",
    )
    _require_gitea_package_identity(
        metadata=metadata,
        owner=owner,
        repository=repository,
        package=package,
        version=version,
    )
    expected = _manifest_artifact_inventory(manifest)
    published = _published_artifact_inventory(files)

    if published != expected:
        raise ReleaseArtifactError(
            "Published artifacts do not match the release manifest"
        )

    _download_and_verify_gitea_artifacts(
        registry=registry,
        owner=owner,
        package=package,
        version=version,
        expected=expected,
        token=token,
    )


def verify_gitea_package_artifacts_with_retry(
    *,
    registry: str,
    owner: str,
    repository: str,
    package: str,
    version: str,
    manifest: dict[str, Any],
    token: str,
    attempts: int,
    delay_seconds: float,
) -> None:
    """Wait a bounded interval for an exact, repository-linked artifact set."""
    if not 1 <= attempts <= 30:
        raise ReleaseArtifactError(
            "Registry verification attempts must be 1 through 30"
        )
    if not 0 <= delay_seconds <= 60:
        raise ReleaseArtifactError(
            "Registry verification delay must be 0 through 60 seconds"
        )

    last_error: ReleaseArtifactError | None = None
    for attempt in range(1, attempts + 1):
        try:
            link_gitea_package(
                registry=registry,
                owner=owner,
                repository=repository,
                package_type="pypi",
                package=package,
                token=token,
            )
            verify_gitea_package_artifacts(
                registry=registry,
                owner=owner,
                repository=repository,
                package=package,
                version=version,
                manifest=manifest,
                token=token,
            )
            return
        except ReleaseArtifactError as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(delay_seconds)

    raise ReleaseArtifactError(
        f"Published artifacts did not match after {attempts} attempts"
    ) from last_error


def prepare_gitea_package_upload(
    *,
    registry: str,
    owner: str,
    repository: str,
    package: str,
    version: str,
    manifest: dict[str, Any],
    token: str,
    resume_existing: bool,
    attempts: int,
    delay_seconds: float,
) -> str:
    """Authorize either one fresh upload or reuse of one exact existing set."""
    verify_gitea_token_identity(registry=registry, owner=owner, token=token)
    if resume_existing:
        try:
            verify_gitea_package_artifacts_with_retry(
                registry=registry,
                owner=owner,
                repository=repository,
                package=package,
                version=version,
                manifest=manifest,
                token=token,
                attempts=attempts,
                delay_seconds=delay_seconds,
            )
        except ReleaseArtifactError as exc:
            if isinstance(exc.__cause__, RegistryNotFound):
                return "upload"
            raise
        return "reuse"

    try:
        verify_gitea_package_artifacts(
            registry=registry,
            owner=owner,
            repository=repository,
            package=package,
            version=version,
            manifest=manifest,
            token=token,
        )
    except RegistryNotFound:
        return "upload"
    except ReleaseArtifactError as exc:
        raise ReleaseArtifactError(
            "Cannot prove the package version is absent; refusing a fresh upload"
        ) from exc
    raise ReleaseArtifactError(
        "The package version already exists; use resume mode only with identical bytes"
    )


def publish_gitea_manifest(
    *,
    registry: str,
    owner: str,
    repository: str,
    manifest: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    """Publish the builder's original manifest and verify its immutable bytes."""
    if not token:
        raise ReleaseArtifactError("Gitea package token is unavailable")
    package = release_manifest_package(manifest)
    version = str(manifest["version"])
    raw = _manifest_bytes(manifest)

    # Uploading, linking and reading back are separate requests, so a timeout
    # or a dropped connection after the server has already accepted one of them
    # is ambiguous: the workflow fails, but the manifest may exist. Package
    # versions here are immutable, and unlike every other post-upload step a
    # missing manifest is unrecoverable -- that exact release can then never be
    # deployed from the package source nor promoted, because both verify
    # provenance against it. So an already-present manifest is tolerated, but
    # only when it is byte-for-byte the one being published and carries the
    # expected repository link; anything else stays fatal rather than being
    # overwritten or accepted.
    def _published() -> dict[str, Any]:
        return fetch_gitea_manifest(
            owner=owner,
            repository=repository,
            package=str(manifest["package"]),
            version=version,
            token=token,
        )

    try:
        existing: dict[str, Any] | None = _published()
    except RegistryNotFound:
        # The only state that authorizes an upload: the registry answered, and
        # the object is genuinely not there.
        existing = None
    except ReleaseArtifactError:
        # Anything else means the manifest may exist in a partial state -- most
        # plausibly uploaded but not yet linked, which is exactly what an
        # interrupted previous run leaves behind and what fetch rejects. Repair
        # the one operation that can be missing and look again. If it still
        # does not resolve, the original failure is propagated rather than
        # being retried as an upload, because re-PUTting an immutable version
        # conflicts instead of repairing and strands the release.
        link_gitea_package(
            registry=registry,
            owner=owner,
            repository=repository,
            package_type="generic",
            package=package,
            token=token,
        )
        existing = _published()
    if existing is not None:
        if existing != manifest:
            raise ReleaseArtifactError(
                "A different release manifest is already published for this version"
            )
        return existing

    upload_url = (
        "https://git.nmulti.cloud/api/packages/"
        f"{_quoted(owner)}/generic/{_quoted(package)}/{_quoted(version)}/release-manifest.json"
    )
    _request(
        upload_url,
        token=token,
        maximum=MAX_RESPONSE_BYTES,
        method="PUT",
        payload=raw,
    )
    link_url = (
        "https://git.nmulti.cloud/api/v1/packages/"
        f"{_quoted(owner)}/generic/{_quoted(package)}/-/link/{_quoted(repository)}"
    )
    _request(
        link_url,
        token=token,
        maximum=MAX_RESPONSE_BYTES,
        method="POST",
        payload=b"",
    )
    verified = fetch_gitea_manifest(
        owner=owner,
        repository=repository,
        package=str(manifest["package"]),
        version=version,
        token=token,
    )
    if verified != manifest:
        raise ReleaseArtifactError("Published release manifest changed")
    return verified


def fetch_gitea_artifacts(
    *,
    owner: str,
    repository: str,
    package: str,
    version: str,
    source_sha: str,
    dist: Path,
    token: str = "",
) -> dict[str, Any]:
    """Download and verify the exact repository-linked Gitea artifact set."""
    package = canonical_name(package)
    published_manifest = fetch_gitea_manifest(
        owner=owner,
        repository=repository,
        package=package,
        version=version,
        token=token,
    )
    if (
        published_manifest.get("package") != package
        or published_manifest.get("version") != version
        or published_manifest.get("source_sha") != source_sha
    ):
        raise ReleaseArtifactError(
            "Gitea release manifest does not match the protected tag"
        )
    base = (
        "https://git.nmulti.cloud/api/v1/packages/"
        f"{_quoted(owner)}/pypi/{_quoted(package)}/{_quoted(version)}"
    )
    metadata = json.loads(_request(base, token=token, maximum=MAX_RESPONSE_BYTES))
    files = json.loads(
        _request(f"{base}/files", token=token, maximum=MAX_RESPONSE_BYTES)
    )
    repo = metadata.get("repository") if isinstance(metadata, dict) else None
    identity = (
        metadata.get("type") if isinstance(metadata, dict) else None,
        canonical_name(str(metadata.get("name", "")))
        if isinstance(metadata, dict)
        else "",
        metadata.get("version") if isinstance(metadata, dict) else None,
        repo.get("full_name") if isinstance(repo, dict) else None,
    )
    if identity != ("pypi", package, version, f"{owner}/{repository}"):
        raise ReleaseArtifactError(
            "Gitea package identity or repository link is invalid"
        )
    if not isinstance(files, list) or len(files) != 2:
        raise ReleaseArtifactError("Gitea must expose exactly two release files")
    dist.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    for row in files:
        if not isinstance(row, dict):
            raise ReleaseArtifactError("Gitea file inventory is malformed")
        name, size, digest = row.get("name"), row.get("size"), row.get("sha256")
        if (
            not isinstance(name, str)
            or SAFE_NAME_RE.fullmatch(name) is None
            or name in seen
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not 0 <= size <= MAX_ARTIFACT_BYTES
            or not isinstance(digest, str)
            or DIGEST_RE.fullmatch(digest.lower()) is None
        ):
            raise ReleaseArtifactError("Gitea file inventory entry is invalid")
        seen.add(name)
        download = (
            "https://git.nmulti.cloud/api/packages/"
            f"{_quoted(owner)}/pypi/files/{_quoted(package)}/{_quoted(version)}/{_quoted(name)}"
        )
        content = _request(download, token=token, maximum=size)
        if (
            len(content) != size
            or hashlib.sha256(content).hexdigest() != digest.lower()
        ):
            raise ReleaseArtifactError(
                "Downloaded artifact differs from Gitea inventory"
            )
        (dist / name).write_bytes(content)
    downloaded_manifest = create_manifest(
        dist=dist, package=package, version=version, source_sha=source_sha
    )
    if downloaded_manifest != published_manifest:
        raise ReleaseArtifactError(
            "Gitea artifacts differ from the original build manifest"
        )
    return published_manifest


def validate_release_attestation(
    *, evidence: object, manifest: dict[str, Any], repository: str
) -> dict[str, Any]:
    """Validate protected NMS production-deployment evidence."""
    if not isinstance(evidence, dict) or set(evidence) != {
        "artifacts",
        "deploy_source",
        "deployment_run_id",
        "deployment_status",
        "environment",
        "manifest_sha256",
        "observed_runtime_identity",
        "package",
        "repository",
        "schema",
        "source_sha",
        "target",
        "version",
    }:
        raise ReleaseArtifactError("NMS promotion evidence schema is not exact")
    typed_evidence = cast(dict[str, Any], evidence)
    package = str(manifest["package"])
    target = package
    expected = {
        "artifacts": manifest["artifacts"],
        "deploy_source": "latest_package",
        "deployment_status": "success",
        "environment": "production",
        "manifest_sha256": manifest_sha256(manifest),
        "package": manifest["package"],
        "repository": repository,
        "schema": 2,
        "source_sha": manifest["source_sha"],
        "target": target,
        "version": manifest["version"],
    }
    if any(typed_evidence.get(key) != value for key, value in expected.items()):
        raise ReleaseArtifactError("NMS promotion evidence does not match the artifact")
    if (
        isinstance(typed_evidence["deployment_run_id"], bool)
        or not isinstance(typed_evidence["deployment_run_id"], int)
        or typed_evidence["deployment_run_id"] <= 0
    ):
        raise ReleaseArtifactError("NMS deployment run ID must be a positive integer")
    expected_runtime = (
        f"netbox_proxbox=={manifest['version']}@/opt/netbox/plugin-releases/"
        f"netbox-proxbox/{manifest_sha256(manifest)}/site-packages"
    )
    if typed_evidence.get("observed_runtime_identity") != expected_runtime:
        raise ReleaseArtifactError("NMS runtime identity does not match netbox-proxbox")
    return typed_evidence


def fetch_gitea_attestation(
    *, owner: str, repository: str, manifest: dict[str, Any], token: str = ""
) -> dict[str, Any]:
    """Fetch immutable, repository-linked deployment completion evidence."""
    package = f"{manifest['package']}-nms-attestation"
    version = str(manifest["version"])
    base = (
        "https://git.nmulti.cloud/api/v1/packages/"
        f"{_quoted(owner)}/generic/{_quoted(package)}/{_quoted(version)}"
    )
    metadata = json.loads(_request(base, token=token, maximum=MAX_RESPONSE_BYTES))
    repo = metadata.get("repository") if isinstance(metadata, dict) else None
    if (
        not isinstance(metadata, dict)
        or metadata.get("type") != "generic"
        or metadata.get("name") != package
        or metadata.get("version") != version
        or not isinstance(repo, dict)
        or repo.get("full_name") != f"{owner}/{repository}"
    ):
        raise ReleaseArtifactError("Gitea deployment attestation identity is invalid")
    url = (
        "https://git.nmulti.cloud/api/packages/"
        f"{_quoted(owner)}/generic/{_quoted(package)}/{_quoted(version)}/completion.json"
    )
    try:
        evidence = json.loads(_request(url, token=token, maximum=MAX_RESPONSE_BYTES))
    except json.JSONDecodeError as exc:
        raise ReleaseArtifactError("Deployment attestation is not valid JSON") from exc
    return validate_release_attestation(
        evidence=evidence, manifest=manifest, repository=f"{owner}/{repository}"
    )


def publish_gitea_attestation(
    *,
    owner: str,
    repository: str,
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    """Publish and independently re-read one immutable completion artifact."""
    if not token:
        raise ReleaseArtifactError("Gitea package token is unavailable")
    validate_release_attestation(
        evidence=evidence, manifest=manifest, repository=f"{owner}/{repository}"
    )
    package = f"{manifest['package']}-nms-attestation"
    version = str(manifest["version"])
    upload_url = (
        "https://git.nmulti.cloud/api/packages/"
        f"{_quoted(owner)}/generic/{_quoted(package)}/{_quoted(version)}/completion.json"
    )
    _request(
        upload_url,
        token=token,
        maximum=MAX_RESPONSE_BYTES,
        method="PUT",
        payload=_manifest_bytes(evidence),
    )
    link_url = (
        "https://git.nmulti.cloud/api/v1/packages/"
        f"{_quoted(owner)}/generic/{_quoted(package)}/-/link/{_quoted(repository)}"
    )
    _request(
        link_url,
        token=token,
        maximum=MAX_RESPONSE_BYTES,
        method="POST",
        payload=b"",
    )
    verified = fetch_gitea_attestation(
        owner=owner, repository=repository, manifest=manifest, token=token
    )
    if verified != evidence:
        raise ReleaseArtifactError("Published deployment attestation changed")
    return verified


def _run_local_command(args: argparse.Namespace) -> dict[str, Any] | None:
    """Run commands that neither read nor write a registry."""
    if args.command == "manifest":
        return write_manifest(
            dist=args.dist,
            package=args.package,
            version=args.version,
            source_sha=args.source_sha,
            output=args.manifest,
        )
    if args.command == "verify":
        return verify_manifest(
            manifest_path=args.manifest,
            dist=args.dist,
            package=args.package,
            version=args.version,
            source_sha=args.source_sha,
        )
    if args.command == "validate-build-source":
        validate_build_source(
            source=args.source,
            package=args.package,
            version=args.version,
        )
    elif args.command == "sanitize-build-source":
        sanitize_build_source(
            source=args.source,
            destination=args.destination,
            package=args.package,
            version=args.version,
        )
    else:
        validate_github_tag_rulesets(
            rulesets=args.rulesets,
            repository=args.repository,
        )
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("manifest", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("--dist", type=Path, required=True)
        command.add_argument("--package", required=True)
        command.add_argument("--version", required=True)
        command.add_argument("--source-sha", required=True)
        command.add_argument("--manifest", type=Path, required=True)
    fetch = subparsers.add_parser("fetch-gitea")
    fetch.add_argument("--owner", required=True)
    fetch.add_argument("--repository", required=True)
    fetch.add_argument("--package", required=True)
    fetch.add_argument("--version", required=True)
    fetch.add_argument("--source-sha", required=True)
    fetch.add_argument("--dist", type=Path, required=True)
    fetch.add_argument("--manifest", type=Path, required=True)
    attest = subparsers.add_parser("validate-attestation")
    attest.add_argument("--attestation", type=Path, required=True)
    attest.add_argument("--manifest", type=Path, required=True)
    attest.add_argument("--repository", required=True)
    fetch_attest = subparsers.add_parser("fetch-attestation")
    fetch_attest.add_argument("--owner", required=True)
    fetch_attest.add_argument("--repository", required=True)
    fetch_attest.add_argument("--manifest", type=Path, required=True)
    publish_attest = subparsers.add_parser("publish-attestation")
    publish_attest.add_argument("--owner", required=True)
    publish_attest.add_argument("--repository", required=True)
    publish_attest.add_argument("--manifest", type=Path, required=True)
    publish_attest.add_argument("--attestation", type=Path, required=True)
    verify_registry = subparsers.add_parser("verify-registry")
    verify_registry.add_argument("--registry", required=True)
    verify_registry.add_argument("--owner", required=True)
    verify_registry.add_argument("--repository", required=True)
    verify_registry.add_argument("--package", required=True)
    verify_registry.add_argument("--version", required=True)
    verify_registry.add_argument("--manifest", type=Path, required=True)
    verify_registry.add_argument("--attempts", type=int, default=1)
    verify_registry.add_argument("--delay-seconds", type=float, default=0)

    prepare_upload = subparsers.add_parser("prepare-upload")
    prepare_upload.add_argument("--registry", required=True)
    prepare_upload.add_argument("--owner", required=True)
    prepare_upload.add_argument("--repository", required=True)
    prepare_upload.add_argument("--package", required=True)
    prepare_upload.add_argument("--version", required=True)
    prepare_upload.add_argument("--manifest", type=Path, required=True)
    prepare_upload.add_argument("--resume-existing", action="store_true")
    prepare_upload.add_argument("--attempts", type=int, default=1)
    prepare_upload.add_argument("--delay-seconds", type=float, default=0)

    validate_source = subparsers.add_parser("validate-build-source")
    validate_source.add_argument("--source", type=Path, required=True)
    validate_source.add_argument("--package", required=True)
    validate_source.add_argument("--version", required=True)

    sanitize_source = subparsers.add_parser("sanitize-build-source")
    sanitize_source.add_argument("--source", type=Path, required=True)
    sanitize_source.add_argument("--destination", type=Path, required=True)
    sanitize_source.add_argument("--package", required=True)
    sanitize_source.add_argument("--version", required=True)

    validate_rulesets = subparsers.add_parser("validate-github-tag-rulesets")
    validate_rulesets.add_argument("--rulesets", type=Path, required=True)
    validate_rulesets.add_argument("--repository", required=True)

    publish_manifest = subparsers.add_parser("publish-manifest")
    publish_manifest.add_argument("--registry", required=True)
    publish_manifest.add_argument("--owner", required=True)
    publish_manifest.add_argument("--repository", required=True)
    publish_manifest.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.command in {
        "manifest",
        "verify",
        "validate-build-source",
        "sanitize-build-source",
        "validate-github-tag-rulesets",
    }:
        local_result = _run_local_command(args)
        if local_result is None:
            return
        manifest = local_result
    elif args.command == "fetch-gitea":
        manifest = fetch_gitea_artifacts(
            owner=args.owner,
            repository=args.repository,
            package=args.package,
            version=args.version,
            source_sha=args.source_sha,
            dist=args.dist,
            token=os.getenv("GITEA_PACKAGE_TOKEN", ""),
        )
        args.manifest.write_bytes(_manifest_bytes(manifest))
    elif args.command == "validate-attestation":
        manifest = load_manifest(args.manifest)
        evidence = json.loads(args.attestation.read_text(encoding="utf-8"))
        validate_release_attestation(
            evidence=evidence,
            manifest=manifest,
            repository=args.repository,
        )
    elif args.command == "fetch-attestation":
        manifest = load_manifest(args.manifest)
        fetch_gitea_attestation(
            owner=args.owner,
            repository=args.repository,
            manifest=manifest,
        )
    elif args.command == "prepare-upload":
        manifest = load_manifest(args.manifest)
        action = prepare_gitea_package_upload(
            registry=args.registry,
            owner=args.owner,
            repository=args.repository,
            package=args.package,
            version=args.version,
            manifest=manifest,
            token=os.getenv("GITEA_PACKAGE_TOKEN", ""),
            resume_existing=args.resume_existing,
            attempts=args.attempts,
            delay_seconds=args.delay_seconds,
        )
        print(action)
        return
    elif args.command == "verify-registry":
        manifest = load_manifest(args.manifest)
        token = os.getenv("GITEA_PACKAGE_TOKEN", "")
        verify_gitea_package_artifacts_with_retry(
            registry=args.registry,
            owner=args.owner,
            repository=args.repository,
            package=args.package,
            version=args.version,
            manifest=manifest,
            token=token,
            attempts=args.attempts,
            delay_seconds=args.delay_seconds,
        )
    elif args.command == "publish-attestation":
        manifest = load_manifest(args.manifest)
        evidence = json.loads(args.attestation.read_text(encoding="utf-8"))
        publish_gitea_attestation(
            owner=args.owner,
            repository=args.repository,
            manifest=manifest,
            evidence=evidence,
            token=os.getenv("GITEA_PACKAGE_TOKEN", ""),
        )
    else:
        manifest = load_manifest(args.manifest)
        publish_gitea_manifest(
            registry=args.registry,
            owner=args.owner,
            repository=args.repository,
            manifest=manifest,
            token=os.getenv("GITEA_PACKAGE_TOKEN", ""),
        )
    print(manifest_sha256(manifest))


if __name__ == "__main__":
    main()
