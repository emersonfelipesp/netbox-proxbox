"""Async aiohttp HTTP client for the proxbox-api."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TypeAlias

import aiohttp
from pydantic import BaseModel, Field

from proxbox_cli.config import Config

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
QueryValue: TypeAlias = str | int | float | bool


class ApiResponse(BaseModel):
    status: int
    text: str
    headers: dict[str, str] = Field(default_factory=dict)

    def json_data(self) -> JSONValue:
        return json.loads(self.text)

    def is_ok(self) -> bool:
        return 200 <= self.status < 300


class ProxboxApiClient:
    """Simple async HTTP client targeting a proxbox-api instance."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def _url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")
        path = path if path.startswith("/") else f"/{path}"
        return f"{base}{path}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, QueryValue] | None = None,
        payload: JSONValue | None = None,
    ) -> ApiResponse:
        url = self._url(path)
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                url,
                params=query,
                json=payload,
                headers={"Accept": "application/json"},
            ) as resp:
                text = await resp.text()
                headers = dict(resp.headers)
                return ApiResponse(status=resp.status, text=text, headers=headers)

    async def get(
        self, path: str, *, query: Mapping[str, QueryValue] | None = None
    ) -> ApiResponse:
        return await self.request("GET", path, query=query)

    async def post(self, path: str, *, payload: JSONValue | None = None) -> ApiResponse:
        return await self.request("POST", path, payload=payload)

    async def put(self, path: str, *, payload: JSONValue | None = None) -> ApiResponse:
        return await self.request("PUT", path, payload=payload)

    async def delete(self, path: str) -> ApiResponse:
        return await self.request("DELETE", path)
