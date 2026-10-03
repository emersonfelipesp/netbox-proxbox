"""Fail-closed sensitive-data policy shared by UI, API, and service consumers."""

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import DatabaseError


def is_active_superuser(user: object) -> bool:
    """Require an authenticated, active superuser, not staff or model permissions."""
    return (
        getattr(user, "is_authenticated", False) is True
        and getattr(user, "is_active", False) is True
        and getattr(user, "is_superuser", False) is True
    )


def can_access_sensitive_data(user: object) -> bool:
    """Read the explicit grant afresh so cached relations cannot survive revocation."""
    if (
        getattr(user, "is_authenticated", False) is not True
        or getattr(user, "is_active", False) is not True
    ):
        return False
    if is_active_superuser(user):
        return True
    user_id = getattr(user, "pk", None)
    if user_id is None:
        return False
    from netbox_proxbox.models.sensitive_data_access import ProxboxSensitiveDataAccess

    try:
        return ProxboxSensitiveDataAccess.objects.filter(
            user_id=user_id, can_access_sensitive_data=True
        ).exists()
    except (DatabaseError, ObjectDoesNotExist):
        return False


def require_sensitive_data_access(user: object) -> None:
    """Deny before any secret resolver is called; retain object/provider checks."""
    if not can_access_sensitive_data(user):
        raise PermissionDenied("Sensitive data access is not authorized.")
