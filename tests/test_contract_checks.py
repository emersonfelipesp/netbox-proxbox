import pytest

from tests.contract_checks import assert_import_roots_allowed


def test_relative_import_alias_is_checked_against_allowlist() -> None:
    assert_import_roots_allowed(
        "from . import public_provider\n",
        frozenset({"public_provider"}),
    )


def test_non_allowlisted_relative_import_alias_is_rejected() -> None:
    with pytest.raises(AssertionError, match="private_provider"):
        assert_import_roots_allowed(
            "from . import private_provider\n",
            frozenset({"public_provider"}),
        )
