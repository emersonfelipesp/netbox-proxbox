"""Admit the selected E2E input union before the compatibility matrix starts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

from packaging.specifiers import SpecifierSet

from scripts.e2e_backend_selection import resolve_dependency_mode, validate_version

NETBOX_IMAGES = (
    *(f"netboxcommunity/netbox:v4.5.{patch}" for patch in range(8, 11)),
    *(f"netboxcommunity/netbox:v4.6.{patch}" for patch in range(7)),
    "netboxcommunity/netbox:v4.7.0-5.1.0@sha256:73a54ff279461170032b59a57a1930929965e3ba15c195af59f4b5f6d39a84a9",
)
INDEXES = {"pypi": "https://pypi.org", "testpypi": "https://test.pypi.org"}
BACKEND_REPOSITORY = "https://github.com/emersonfelipesp/proxbox-api.git"
PACKAGE_DEPENDENCY_MODES = ("pypi-package", "testpypi-package")


def select_axis(value: str, choices: tuple[str, ...], full: str) -> list[str]:
    """Select a documented axis without silently replacing an invalid input."""
    if value in ("", full):
        return list(choices)
    if value not in choices:
        raise ValueError(f"Unsupported E2E selection: {value!r}")
    return [value]


def validate_image(reference: str) -> str:
    """Reject option-like, multiline, or shell-active image references."""
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]{0,254}", reference):
        raise ValueError(f"Invalid image reference: {reference!r}")
    return reference


def select_runtimes(value: str, dependency_mode: str) -> list[str]:
    """Keep package installs on the only runtime their artifacts provide."""
    if dependency_mode not in PACKAGE_DEPENDENCY_MODES:
        return select_axis(value, ("python", "pyo3-rust"), "both")
    if value in ("", "python"):
        return ["python"]
    if value in ("both", "pyo3-rust"):
        raise ValueError(
            f"Package dependency mode {dependency_mode!r} cannot request "
            f"proxbox_api_runtime={value!r}: proxbox-api packages ship only the "
            "Python runtime; use dependency_mode='published' or 'dev' for "
            "pyo3-rust"
        )
    return select_axis(value, ("python", "pyo3-rust"), "both")


def build_plan(event: str, inputs: dict[str, str], defaults: dict[str, str]) -> dict:
    """Retain the full certification axes and existing narrow PR selection."""
    dependency_mode = resolve_dependency_mode(inputs.get("dependency_mode", ""))
    sources = select_axis(
        inputs.get("install_source", ""),
        ("local", "pypi", "container", "testpypi"),
        "both",
    )
    if inputs.get("install_source", "") in ("", "both"):
        sources.remove("testpypi")
    runtimes = select_runtimes(inputs.get("proxbox_api_runtime", ""), dependency_mode)
    services = select_axis(
        inputs.get("proxmox_service", ""), ("pve", "pbs", "pdm"), "all"
    )
    if event == "pull_request":
        runtimes, services = ["python"], ["pve"]
    images = (
        [validate_image(inputs["netbox_image"])]
        if inputs.get("netbox_image")
        else list(NETBOX_IMAGES)
    )
    return {
        "matrix": {
            "install_source": sources,
            "netbox_image": images,
            "network_stack": ["ipv4"],
            "proxbox_api_runtime": runtimes,
            "proxmox_service": services,
        },
        "dependency_mode": dependency_mode,
        "backend_version": validate_version(
            inputs.get("proxbox_api_version", "") or defaults["backend_version"]
        ),
        "backend_image": validate_image(defaults["backend_image"]),
        "mock_image": validate_image(defaults["mock_image"]),
        "mock_tag_prefix": defaults["mock_tag_prefix"],
    }


def run_checked(argv: list[str]) -> str:
    """Run a bounded, structured prerequisite command without a shell."""
    try:
        return subprocess.run(
            argv, check=True, capture_output=True, text=True, timeout=90
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"Prerequisite command failed: {argv!r}: {exc.stderr}"
        ) from exc


def resolve_image(reference: str) -> str:
    """Admit a Linux amd64 manifest and preserve its immutable index identity."""
    validate_image(reference)
    manifest = json.loads(
        run_checked(
            [
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                reference,
                "--format",
                "{{json .Manifest}}",
            ]
        )
    )
    digest = manifest.get("digest", "")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError(f"No immutable manifest digest for {reference}")
    if "@" in reference and reference.split("@", 1)[1] != digest:
        raise ValueError(f"Image digest does not match requested identity: {reference}")
    immutable_reference = f"{reference.split('@', 1)[0]}@{digest}"
    if "manifests" in manifest:
        platforms = [entry.get("platform", {}) for entry in manifest["manifests"]]
        supported = any(
            p.get("os") == "linux" and p.get("architecture") == "amd64"
            for p in platforms
        )
    else:
        config = json.loads(
            run_checked(
                [
                    "docker",
                    "buildx",
                    "imagetools",
                    "inspect",
                    immutable_reference,
                    "--format",
                    "{{json .Image}}",
                ]
            )
        )
        supported = (
            config.get("os") == "linux" and config.get("architecture") == "amd64"
        )
    if not supported:
        raise ValueError(f"Image does not provide linux/amd64: {reference}")
    return immutable_reference


def fetch_package_metadata(name: str, version: str, index: str) -> dict[str, Any]:
    """Read one selected public index with a bounded response and request."""
    suffix = f"/{validate_version(version)}" if version else ""
    url = f"{INDEXES[index]}/pypi/{name}{suffix}/json"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            content = response.read(2 * 1024 * 1024 + 1)
    except OSError as exc:
        selection = version or "latest"
        reason = str(exc)[:240]
        raise ValueError(
            f"Package metadata request failed for {name}=={selection} "
            f"on {index}: {reason!r}"
        ) from exc
    if len(content) > 2 * 1024 * 1024:
        raise ValueError(f"Package metadata exceeds the response limit: {name}")
    return json.loads(content)


def admit_package(
    name: str, version: str, index: str, python: str, *, rust: bool = False
) -> dict[str, str]:
    """Require the selected release and bind an artifact to its published hash."""
    metadata = fetch_package_metadata(name, version, index)
    info = metadata["info"]
    resolved = validate_version(info["version"])
    if version and resolved != version:
        raise ValueError(f"Wrong package version admitted for {name}: {resolved}")
    if info["name"].replace("_", "-").lower() != name:
        raise ValueError(f"Wrong package identity admitted for {name}")
    if rust and "pyo3-rust" not in (info.get("provides_extra") or []):
        raise ValueError(f"Selected {name}=={resolved} has no pyo3-rust extra")
    artifact = select_artifact(metadata["urls"], python, index)
    return {"version": resolved, "spec": artifact}


def universal_wheel(item: dict) -> bool:
    """Recognize the portable wheel supplied by these two Python projects."""
    return str(item.get("filename", "")).endswith("-py3-none-any.whl")


def usable_artifact(item: dict, python: str) -> bool:
    """Reject yanked, incompatible, and platform-specific direct artifacts."""
    if item.get("yanked"):
        return False
    if not SpecifierSet(item.get("requires_python") or "").contains(python):
        return False
    return universal_wheel(item) or item.get("packagetype") == "sdist"


def artifact_spec(item: dict, index: str) -> str:
    """Bind a selected-index file URL to its published SHA-256 digest."""
    url = item["url"]
    parsed = urllib.parse.urlsplit(url)
    host = (
        "test-files.pythonhosted.org"
        if index == "testpypi"
        else "files.pythonhosted.org"
    )
    if parsed.scheme != "https" or parsed.netloc != host:
        raise ValueError(
            "Package artifact must use the selected public index's file host"
        )
    if (
        parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/[a-zA-Z0-9._/%+-]+", parsed.path)
    ):
        raise ValueError("Package artifact URL is not safe for workflow transport")
    digest = item.get("digests", {}).get("sha256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Package artifact has no SHA-256 identity")
    return f"{url}#sha256={digest}"


def select_artifact(files: list[dict], python: str, index: str) -> str:
    """Prefer a universal wheel without changing release or index identity."""
    available = [item for item in files if usable_artifact(item, python)]
    if not available:
        raise ValueError(f"No usable direct artifact for Python {python}")
    item = sorted(available, key=lambda entry: not universal_wheel(entry))[0]
    return artifact_spec(item, index)


def image_requests(plan: dict) -> dict[str, str]:
    """Request only images consumed by the selected backend and service paths."""
    images = {"postgres": "postgres:16-alpine", "redis": "redis:7-alpine"}
    for service in plan["matrix"]["proxmox_service"]:
        tag = "nginx" if service == "pve" else service
        images[f"mock_{service}"] = (
            f"{plan['mock_image']}:{plan['mock_tag_prefix']}-{tag}"
        )
    if plan["dependency_mode"] == "published":
        for runtime in plan["matrix"]["proxbox_api_runtime"]:
            suffix = "-pyo3-rust" if runtime == "pyo3-rust" else ""
            images[f"api_{runtime}"] = (
                f"{plan['backend_image']}:{plan['backend_version']}{suffix}"
            )
    elif plan["dependency_mode"] in ("pypi-package", "testpypi-package"):
        images["package_python"] = "python:3.13-slim"
    return images


def admit_plugins(sources: list[str], plugin_version: str) -> tuple[dict, dict]:
    """Admit only the plugin installation paths selected by this event."""
    versions, specs = {}, {}
    for source in sources:
        if source == "local":
            continue
        index = "testpypi" if source == "testpypi" else "pypi"
        requested = "" if source == "container" else plugin_version
        admitted = admit_package("netbox-proxbox", requested, index, "3.12")
        versions[source], specs[source] = admitted["version"], admitted["spec"]
    return versions, specs


def admit_backend_package(plan: dict) -> dict[str, str]:
    """Require the selected backend package instead of falling back to an image."""
    mode = plan["dependency_mode"]
    if mode not in PACKAGE_DEPENDENCY_MODES:
        return {}
    runtimes = plan["matrix"]["proxbox_api_runtime"]
    if runtimes != ["python"]:
        requested = runtimes[0] if len(runtimes) == 1 else "both"
        select_runtimes(requested, mode)
    index = "testpypi" if mode == "testpypi-package" else "pypi"
    admitted = admit_package(
        "proxbox-api",
        plan["backend_version"],
        index,
        "3.13",
    )
    return {"python": f"proxbox-api @ {admitted['spec']}"}


def development_source(mode: str) -> str:
    """Bind explicit development mode to one source identity for the whole run."""
    if mode != "dev":
        return ""
    fields = run_checked(["git", "ls-remote", BACKEND_REPOSITORY, "HEAD"]).split()
    if (
        len(fields) != 2
        or fields[1] != "HEAD"
        or not re.fullmatch(r"[a-f0-9]{40}", fields[0])
    ):
        raise ValueError(
            "The selected development backend has no exact source identity"
        )
    return fields[0]


def admit_plan(plan: dict, plugin_version: str) -> dict:
    """Resolve the selected prerequisite union once, before publishing outputs."""
    plugin_versions, plugin_specs = admit_plugins(
        plan["matrix"]["install_source"], plugin_version
    )
    backend_specs = admit_backend_package(plan)
    backend_sha = development_source(plan["dependency_mode"])
    images = {name: resolve_image(ref) for name, ref in image_requests(plan).items()}
    matrix = {
        **plan["matrix"],
        "netbox_image": [resolve_image(ref) for ref in plan["matrix"]["netbox_image"]],
    }
    return {
        "matrix": matrix,
        "images": images,
        "plugin_versions": plugin_versions,
        "plugin_specs": plugin_specs,
        "backend_specs": backend_specs,
        "backend_sha": backend_sha,
    }


def main() -> int:
    """Publish admitted JSON only after every selected prerequisite succeeds."""
    inputs = json.loads(os.environ.get("E2E_INPUTS", "{}")) or {}
    defaults = {
        "backend_version": os.environ["PROXBOX_API_RELEASE_VERSION"],
        "backend_image": os.environ["PROXBOX_API_IMAGE"],
        "mock_image": os.environ["PROXMOX_SDK_IMAGE"],
        "mock_tag_prefix": os.environ["PROXMOX_SDK_TAG_PREFIX"],
    }
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    plan = build_plan(os.environ["GITHUB_EVENT_NAME"], inputs, defaults)
    admitted = admit_plan(plan, validate_version(metadata["project"]["version"]))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for name, value in admitted.items():
            output.write(f"{name}={json.dumps(value, separators=(',', ':'))}\n")
    print(json.dumps(admitted, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        print(f"E2E prerequisite admission failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
