"""Define custom model fields and validators used by plugin models."""

import re

from django.core.exceptions import ValidationError
from django.db import models


def validate_domain(value: object) -> None:
    """Reject values that are not empty, ``localhost``, or a simple DNS-like hostname."""
    if value in (None, ""):
        return

    domain_regex = re.compile(
        r"^(?:[a-zA-Z0-9]"  # First character of the domain
        r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)"  # Sub domain + hostname
        r"+[a-zA-Z]{2,6}$"  # Top level domain
    )
    if value != "localhost":
        if not domain_regex.match(value):
            raise ValidationError(f"{value} is not a valid domain name")


class DomainField(models.CharField):
    """CharField with RFC-ish domain validation (plus ``localhost``)."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs["max_length"] = 253  # Maximum length of a domain name is 253 characters
        super().__init__(*args, **kwargs)
        self.validators.append(validate_domain)
