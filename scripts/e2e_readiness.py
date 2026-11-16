"""Bounded E2E readiness that refuses terminal container states immediately."""

from __future__ import annotations

import argparse
import json
from functools import partial
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable


class ReadinessFailure(RuntimeError):
    """The selected disposable stack cannot become ready in its current state."""


def inspect_state(name: str, timeout: float) -> dict:
    """Read one required container; a missing or unreadable state fails closed."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{json .State}}", name],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    state = json.loads(result.stdout)
    if not isinstance(state, dict) or not state.get("Status"):
        raise ReadinessFailure(f"Invalid container state for {name}: {state!r}")
    return state


def assert_starting_or_running(states: dict[str, dict]) -> None:
    """Refuse terminal, paused, unknown, and explicitly unhealthy states."""
    for name, state in states.items():
        status = state.get("Status")
        health = state.get("Health", {}).get("Status")
        if status not in ("created", "running", "restarting") or health == "unhealthy":
            raise ReadinessFailure(
                f"Required container {name} cannot become ready: {json.dumps(state)}"
            )


class KeepProbeResponse(urllib.request.HTTPRedirectHandler):
    """Inspect the disposable service's response instead of following redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Let HTTPError expose the original redirect status to the probe."""
        return None


def http_ready(url: str, timeout: float, insecure: bool) -> bool:
    """Accept a responding application below HTTP 500, including login denial."""
    context = (
        ssl._create_unverified_context() if insecure else ssl.create_default_context()
    )
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            KeepProbeResponse(),
            urllib.request.HTTPSHandler(context=context),
        )
        with opener.open(url, timeout=timeout) as response:
            return 100 <= response.status < 500
    except urllib.error.HTTPError as exc:
        return 100 <= exc.code < 500
    except (OSError, urllib.error.URLError):
        return False


def wait_until_ready(
    names: list[str],
    probe: Callable[[dict[str, dict], float], bool],
    timeout: float,
    interval: float = 2,
) -> None:
    """Keep slow valid startup while bounding all polling with one deadline."""
    if timeout <= 0 or interval <= 0:
        raise ValueError("Readiness timeout and interval must be positive")
    deadline = time.monotonic() + timeout
    while True:
        states = {}
        for name in names:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReadinessFailure(
                    f"Stack did not become ready within {timeout:g}s"
                )
            states[name] = inspect_state(name, min(10, remaining))
            assert_starting_or_running({name: states[name]})
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ReadinessFailure(f"Stack did not become ready within {timeout:g}s")
        ready = probe(states, min(5, remaining))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ReadinessFailure(f"Stack did not become ready within {timeout:g}s")
        if ready:
            return
        time.sleep(min(interval, remaining))


def selected_probe(
    states: dict[str, dict],
    remaining: float,
    *,
    healthy: str | None,
    url: str | None,
    insecure: bool,
) -> bool:
    """Probe the selected readiness condition after all container states pass."""
    if healthy:
        return states[healthy].get("Health", {}).get("Status") == "healthy"
    return http_ready(str(url), remaining, insecure)


def dump_diagnostics(names: list[str]) -> None:
    """Print complete logs without allowing a diagnostic failure to mask refusal."""
    for name in names:
        print(f"=== Required container: {name} ===", flush=True)
        for command in (["inspect", name], ["logs", name]):
            try:
                subprocess.run(["docker", *command], check=False, timeout=15)
            except (OSError, subprocess.SubprocessError) as exc:
                print(f"Diagnostic failed for {name}: {exc}", file=sys.stderr)


def main() -> int:
    """Wait for container health or HTTP readiness without starting any service."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--required", nargs="+", required=True)
    parser.add_argument("--timeout", type=float, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--healthy")
    selection.add_argument("--url")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Allow only the disposable mock's self-signed TLS",
    )
    args = parser.parse_args()
    if args.healthy and args.healthy not in args.required:
        parser.error("The health target must be a required container")
    probe = partial(
        selected_probe, healthy=args.healthy, url=args.url, insecure=args.insecure
    )
    try:
        wait_until_ready(args.required, probe, args.timeout)
    except (ReadinessFailure, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"E2E readiness failed: {exc}", file=sys.stderr, flush=True)
        dump_diagnostics(args.required)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
