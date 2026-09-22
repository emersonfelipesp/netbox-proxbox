from __future__ import annotations

import pytest

from scripts.e2e_backend_selection import (
    DEPENDENCY_MODES,
    resolve_dependency_mode,
    resolve_release_version,
    validate_version,
)


@pytest.mark.parametrize("value", ["", " ", "\t"])
def test_empty_event_dependency_mode_defaults_to_published(value: str) -> None:
    assert resolve_dependency_mode(value) == "published"


@pytest.mark.parametrize("value", sorted(DEPENDENCY_MODES))
def test_explicit_dependency_modes_are_preserved(value: str) -> None:
    assert resolve_dependency_mode(value) == value


def test_unknown_dependency_mode_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unsupported proxbox-api dependency mode"):
        resolve_dependency_mode("source-head-ish")


def test_current_implicit_release_version_is_accepted() -> None:
    assert (
        resolve_release_version(
            explicit="", configured="0.0.23", required_default="0.0.23"
        )
        == "0.0.23"
    )


def test_stale_implicit_release_version_fails_closed() -> None:
    with pytest.raises(ValueError, match="Stale proxbox-api repository variable"):
        resolve_release_version(
            explicit="", configured="0.0.19.post5", required_default="0.0.23"
        )


def test_explicit_release_candidate_is_preserved() -> None:
    assert (
        resolve_release_version(
            explicit="0.0.24rc1",
            configured="0.0.19.post5",
            required_default="0.0.23",
        )
        == "0.0.24rc1"
    )


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-version",
        "0.0.23; touch /tmp/injected",
        "0.0.23\nINJECTED=1",
        "v0.0.23",
    ],
)
def test_invalid_or_noncanonical_version_fails_closed(value: str) -> None:
    with pytest.raises(ValueError, match="proxbox-api version"):
        validate_version(value)
