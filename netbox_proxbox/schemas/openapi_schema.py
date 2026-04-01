"""Pydantic V2 schemas and factory for OpenAPI schema normalization."""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator

from netbox_proxbox.schemas._base import ProxboxBaseModel

_METHOD_ORDER: dict[str, int] = {
    "get": 10,
    "post": 20,
    "put": 30,
    "patch": 40,
    "delete": 50,
    "options": 60,
    "head": 70,
    "trace": 80,
}


class OpenAPIServer(ProxboxBaseModel):
    """One server entry from an OpenAPI ``servers`` list."""

    url: str
    description: str = ""


class OpenAPISecurityScheme(ProxboxBaseModel):
    """One security scheme from ``components.securitySchemes``."""

    name: str
    type: str = ""
    scheme: str = ""
    location: str = Field("", alias="in")

    model_config = ConfigDict(
        populate_by_name=True, extra="ignore", str_strip_whitespace=True
    )


class OpenAPIOperation(ProxboxBaseModel):
    """One HTTP operation from an OpenAPI ``paths`` item."""

    path: str
    method: str
    method_order: int = 99
    summary: str = ""
    operation_id: str = ""
    tags: str = ""
    parameters_count: int = 0
    responses_count: int = 0

    @field_validator("method", mode="before")
    @classmethod
    def _uppercase_method(cls, v: object) -> str:
        return str(v).upper()


class OpenAPIStats(ProxboxBaseModel):
    """Counts of paths, operations, schemas, and security schemes."""

    paths: int = 0
    operations: int = 0
    schemas: int = 0
    security_schemes: int = 0


class OpenAPISummary(ProxboxBaseModel):
    """Parsed and normalised summary of a proxbox-api OpenAPI schema.

    Replaces the five ``_normalize_*`` functions and ``_build_openapi_summary``
    in ``services/openapi_schema.py``.
    """

    title: str = "OpenAPI"
    version: str = "unknown"
    description: str = ""
    servers: list[OpenAPIServer] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    security_schemes: list[OpenAPISecurityScheme] = Field(default_factory=list)
    operations: list[OpenAPIOperation] = Field(default_factory=list)
    stats: OpenAPIStats = Field(default_factory=OpenAPIStats)

    @classmethod
    def from_raw_payload(cls, payload: object) -> OpenAPISummary:
        """Parse a raw OpenAPI JSON object into a typed ``OpenAPISummary``.

        Raises ``ValueError`` when *payload* is not a dict.
        """
        if not isinstance(payload, dict):
            raise ValueError("OpenAPI response is not a JSON object.")

        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
        components = (
            payload.get("components")
            if isinstance(payload.get("components"), dict)
            else {}
        )
        servers_raw = payload.get("servers") or []
        tags_raw = payload.get("tags") or []
        paths_raw = payload.get("paths") or {}
        schemes_raw = components.get("securitySchemes") or {}
        schemas_raw = components.get("schemas") or {}

        # Normalise servers
        servers: list[OpenAPIServer] = []
        if isinstance(servers_raw, list):
            for item in servers_raw:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if url:
                    servers.append(
                        OpenAPIServer(
                            url=url,
                            description=str(item.get("description") or "").strip(),
                        )
                    )

        # Normalise tags
        tags: list[str] = []
        if isinstance(tags_raw, list):
            for item in tags_raw:
                if isinstance(item, dict):
                    n = str(item.get("name") or "").strip()
                    if n:
                        tags.append(n)

        # Normalise security schemes
        schemes: list[OpenAPISecurityScheme] = []
        if isinstance(schemes_raw, dict):
            for name, defn in schemes_raw.items():
                if not isinstance(defn, dict):
                    continue
                schemes.append(
                    OpenAPISecurityScheme(
                        name=str(name),
                        type=str(defn.get("type") or ""),
                        scheme=str(defn.get("scheme") or ""),
                        **{"in": str(defn.get("in") or "")},
                    )
                )
        schemes.sort(key=lambda s: s.name.lower())

        # Normalise operations
        operations: list[OpenAPIOperation] = []
        if isinstance(paths_raw, dict):
            for path, path_item in paths_raw.items():
                if not isinstance(path_item, dict):
                    continue
                for method, op in path_item.items():
                    method_lower = str(method).lower().strip()
                    if method_lower not in _METHOD_ORDER or not isinstance(op, dict):
                        continue
                    tags_val = op.get("tags")
                    tags_str = (
                        ", ".join(str(t) for t in tags_val)
                        if isinstance(tags_val, list)
                        else ""
                    )
                    responses = op.get("responses")
                    parameters = op.get("parameters")
                    operations.append(
                        OpenAPIOperation(
                            path=str(path),
                            method=method_lower.upper(),
                            method_order=_METHOD_ORDER[method_lower],
                            summary=str(
                                op.get("summary") or op.get("description") or ""
                            ).strip(),
                            operation_id=str(op.get("operationId") or "").strip(),
                            tags=tags_str,
                            parameters_count=len(parameters)
                            if isinstance(parameters, list)
                            else 0,
                            responses_count=len(responses)
                            if isinstance(responses, dict)
                            else 0,
                        )
                    )
        operations.sort(key=lambda o: (o.path, o.method_order))

        stats = OpenAPIStats(
            paths=len(paths_raw) if isinstance(paths_raw, dict) else 0,
            operations=len(operations),
            schemas=len(schemas_raw) if isinstance(schemas_raw, dict) else 0,
            security_schemes=len(schemes_raw) if isinstance(schemes_raw, dict) else 0,
        )

        return cls(
            title=str(info.get("title") or "OpenAPI"),
            version=str(info.get("version") or "unknown"),
            description=str(info.get("description") or "").strip(),
            servers=servers,
            tags=tags,
            security_schemes=schemes,
            operations=operations,
            stats=stats,
        )
