"""Validation for storage download hostname allowlists."""

from __future__ import annotations

import ipaddress
import re

from django.core.exceptions import ValidationError

MAX_STORAGE_DOWNLOAD_ALLOWED_HOSTS = 64
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _invalid(entry: object, reason: str) -> ValidationError:
    return ValidationError(f"Invalid storage download host {entry!r}: {reason}")


def _is_ip_literal(hostname: str) -> bool:
    candidate = (
        hostname[1:-1]
        if hostname.startswith("[") and hostname.endswith("]")
        else hostname
    )
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return True


def _reject_forbidden_syntax(entry: object, hostname: str) -> None:
    if "://" in hostname:
        raise _invalid(entry, "schemes are not allowed.")
    if "@" in hostname:
        raise _invalid(entry, "userinfo is not allowed.")
    if any(character in hostname for character in ":/?#"):
        raise _invalid(entry, "ports, paths, queries, and fragments are not allowed.")
    if "*" in hostname:
        raise _invalid(entry, "wildcards are not allowed.")


def _normalize_host(entry: object) -> str:
    if not isinstance(entry, str):
        raise _invalid(entry, "each entry must be a string.")
    hostname = entry.strip().lower()
    if hostname.endswith("."):
        hostname = hostname[:-1]
    if not hostname:
        raise _invalid(entry, "the hostname cannot be empty.")
    if _is_ip_literal(hostname):
        raise _invalid(entry, "IP address literals are not allowed.")
    _reject_forbidden_syntax(entry, hostname)
    if len(hostname) > 253:
        raise _invalid(entry, "the hostname exceeds 253 characters.")
    labels = hostname.split(".")
    if len(labels) < 2:
        raise _invalid(entry, "the hostname must contain at least one dot.")
    if any(not _HOST_LABEL_RE.fullmatch(label) for label in labels):
        raise _invalid(entry, "each label must conform to RFC 1123.")
    return hostname


def normalize_storage_download_allowed_hosts(value: object) -> list[str]:
    """Return normalized exact hostnames or raise ``ValidationError``."""

    if not isinstance(value, list):
        raise ValidationError(
            "Storage download allowed hosts must be a list of strings."
        )
    if len(value) > MAX_STORAGE_DOWNLOAD_ALLOWED_HOSTS:
        raise ValidationError(
            f"Storage download allowed hosts cannot contain more than {MAX_STORAGE_DOWNLOAD_ALLOWED_HOSTS} entries."
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for entry in value:
        hostname = _normalize_host(entry)
        if hostname in seen:
            raise _invalid(entry, f"duplicate normalized hostname {hostname!r}.")
        seen.add(hostname)
        normalized.append(hostname)
    return normalized
