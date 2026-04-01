"""Shared Pydantic V2 base model configuration for all ProxBox schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProxboxBaseModel(BaseModel):
    """Base model: drops unknown keys, strips whitespace from strings."""

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    def __getitem__(self, key: str) -> object:
        return getattr(self, key)

    def get(self, key: str, default: object | None = None) -> object | None:
        return getattr(self, key, default)


class ProxboxLenientModel(BaseModel):
    """Lenient model: passes through unknown keys (for open-ended Proxmox API responses)."""

    model_config = ConfigDict(
        extra="allow",
        str_strip_whitespace=True,
        populate_by_name=True,
    )
