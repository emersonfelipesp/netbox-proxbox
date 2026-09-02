#!/usr/bin/env python3
"""Create, verify, and retrieve one immutable Python release artifact set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
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


def fetch_gitea_manifest(
    *, owner: str, repository: str, package: str, version: str, token: str = ""
) -> dict[str, Any]:
    """Fetch the original repository-linked manifest created by the builder."""
    manifest_package = f"{canonical_name(package)}-release-manifest"
    base = (
        "https://git.nmulti.cloud/api/v1/packages/"
        f"{_quoted(owner)}/generic/{_quoted(manifest_package)}/{_quoted(version)}"
    )
    metadata = json.loads(_request(base, token=token, maximum=MAX_RESPONSE_BYTES))
    files = json.loads(
        _request(f"{base}/files", token=token, maximum=MAX_RESPONSE_BYTES)
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
    """Require the registry to hold exactly the artifacts the manifest names.

    The previous check searched the owner's package list and counted entries
    whose ``version`` matched. That is satisfied by any package of any name at
    that version, so it could pass while this package's own upload was absent,
    incomplete, or carrying different bytes -- and the manifest would then be
    published against a release that does not exist as it describes. The
    manifest is the provenance record every later deploy and promotion verifies
    against, so it must not be published until the artifacts it names are
    provably present with the exact sizes and digests it recorded.

    The repository link is required here, matching ``fetch_gitea_artifacts``,
    which refuses to download an artifact whose PyPI metadata does not name
    ``<owner>/<repository>``. A twine upload does not create that link, so
    ``link_gitea_package`` creates it first; verifying it here is what makes a
    published version actually consumable by the deploy and promotion paths
    rather than merely present in the registry.
    """
    base = (
        registry
        + f"{_quoted(owner)}/pypi/{_quoted(canonical_name(package))}/{_quoted(version)}"
    )
    metadata = json.loads(_request(base, token=token, maximum=MAX_RESPONSE_BYTES))
    files = json.loads(
        _request(f"{base}/files", token=token, maximum=MAX_RESPONSE_BYTES)
    )
    repo = metadata.get("repository") if isinstance(metadata, dict) else None
    if (
        not isinstance(metadata, dict)
        or metadata.get("type") != "pypi"
        or canonical_name(str(metadata.get("name", ""))) != canonical_name(package)
        or metadata.get("version") != version
        or not isinstance(repo, dict)
        or repo.get("full_name") != f"{owner}/{repository}"
    ):
        raise ReleaseArtifactError("Published package identity or link is invalid")
    if not isinstance(files, list):
        raise ReleaseArtifactError("Published package inventory is invalid")

    expected = {
        str(record["name"]): (int(record["size"]), str(record["sha256"]).lower())
        for record in manifest["artifacts"]
    }
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

    if published != expected:
        raise ReleaseArtifactError(
            "Published artifacts do not match the release manifest"
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

    publish_manifest = subparsers.add_parser("publish-manifest")
    publish_manifest.add_argument("--registry", required=True)
    publish_manifest.add_argument("--owner", required=True)
    publish_manifest.add_argument("--repository", required=True)
    publish_manifest.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "manifest":
        manifest = write_manifest(
            dist=args.dist,
            package=args.package,
            version=args.version,
            source_sha=args.source_sha,
            output=args.manifest,
        )
    elif args.command == "verify":
        manifest = verify_manifest(
            manifest_path=args.manifest,
            dist=args.dist,
            package=args.package,
            version=args.version,
            source_sha=args.source_sha,
        )
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
    elif args.command == "verify-registry":
        manifest = load_manifest(args.manifest)
        token = os.getenv("GITEA_PACKAGE_TOKEN", "")
        # A twine upload leaves the package unlinked, and the deploy and
        # promotion consumers both refuse an unlinked package, so the link is
        # created here and then required by the verification below.
        link_gitea_package(
            registry=args.registry,
            owner=args.owner,
            repository=args.repository,
            package_type="pypi",
            package=args.package,
            token=token,
        )
        verify_gitea_package_artifacts(
            registry=args.registry,
            owner=args.owner,
            repository=args.repository,
            package=args.package,
            version=args.version,
            manifest=manifest,
            token=token,
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
