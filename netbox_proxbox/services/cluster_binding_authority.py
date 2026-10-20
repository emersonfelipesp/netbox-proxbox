"""Exact in-process authority for synchronization-owned inventory relations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_CLUSTER_BINDING_WRITE: ContextVar[tuple[int, int] | None] = ContextVar(
    "proxbox_cluster_binding_write", default=None
)


@contextmanager
def allow_cluster_binding_write(endpoint_pk: int, cluster_pk: int) -> Iterator[None]:
    """Delegate one exact ownership write inside the protected transaction."""
    token = _CLUSTER_BINDING_WRITE.set((endpoint_pk, cluster_pk))
    try:
        yield
    finally:
        _CLUSTER_BINDING_WRITE.reset(token)


def cluster_binding_write_allowed(
    cluster_pk: int, endpoint_pk: int | None = None
) -> bool:
    """Return whether the current protected operation owns this exact pair."""
    permit = _CLUSTER_BINDING_WRITE.get()
    if permit is None or permit[1] != cluster_pk:
        return False
    return endpoint_pk is None or permit[0] == endpoint_pk
