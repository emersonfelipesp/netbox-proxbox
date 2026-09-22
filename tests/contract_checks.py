"""Reusable source-contract checks that do not publish forbidden identities."""

from __future__ import annotations

import ast
import hashlib
import re


_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def assert_digest_token_absent(source: str, forbidden_digest: str) -> None:
    """Reject the production contract token without embedding it in fixtures."""
    assert all(
        hashlib.sha256(token.casefold().encode()).hexdigest() != forbidden_digest
        for token in _TOKEN.findall(source)
    )


def assert_import_roots_allowed(source: str, allowed: frozenset[str]) -> None:
    """Reject imports outside the reviewed standard/public provider surface."""
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.partition(".")[0])
            else:
                roots.update(alias.name.partition(".")[0] for alias in node.names)
    assert roots <= allowed, roots - allowed
