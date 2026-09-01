"""Shared ``django.db.models`` field stand-ins for mocked module loaders."""

from __future__ import annotations


def attach_standard_model_fields(models_module: object, *, field_class: type) -> object:
    """Ensure a stub ``django.db.models`` module exposes common field types."""
    for name in (
        "BooleanField",
        "CharField",
        "DateTimeField",
        "DecimalField",
        "ForeignKey",
        "JSONField",
        "ManyToManyField",
        "PositiveIntegerField",
        "PositiveSmallIntegerField",
        "TextField",
        "UUIDField",
    ):
        if not hasattr(models_module, name):
            setattr(models_module, name, field_class)
    return models_module
