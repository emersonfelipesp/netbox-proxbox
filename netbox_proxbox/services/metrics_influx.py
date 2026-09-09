"""Server-side proxy for retrieving Proxmox metrics through proxbox-api."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import requests

from netbox_proxbox.models import ProxmoxMetricsInfluxDB, ProxboxPluginSettings
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.utils import encryption as enc_helpers
from netbox_proxbox.utils.metrics import validate_metrics_time


class MetricsProxyError(Exception):
    """Safe error raised when a metrics query cannot be completed."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


MAX_PROXY_RESPONSE_BYTES = 1024 * 1024
_RESPONSE_FORMATS = {"annotated_csv", "json"}
_SAFE_ERROR_CODES = {
    "invalid_query",
    "invalid_configuration",
    "backend_unavailable",
    "influx_upstream_error",
    "influx_invalid_response",
    "influx_timeout",
    "influx_tls_error",
    "influx_connection_error",
    "influx_empty_response",
    "influx_response_too_large",
}


def _invalid_response() -> MetricsProxyError:
    return MetricsProxyError(
        "The proxbox-api metrics backend returned an invalid payload."
    )


def _response_columns(body: dict[str, Any]) -> list[str]:
    columns = body.get("columns")
    if not isinstance(columns, list) or not all(
        isinstance(column, str) for column in columns
    ):
        raise _invalid_response()
    return columns


def _response_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    rows = body.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise _invalid_response()
    return rows


def _response_window(body: dict[str, Any]) -> dict[str, Any]:
    window = body.get("query_window")
    if not isinstance(window, dict) or not {"start", "stop"}.issubset(window):
        raise _invalid_response()
    start = window.get("start")
    stop = window.get("stop")
    if not isinstance(start, str) or len(start) > 64:
        raise _invalid_response()
    try:
        validate_metrics_time(start, allow_now=True)
        if stop is not None:
            if not isinstance(stop, str) or len(stop) > 64:
                raise ValueError("invalid stop")
            validate_metrics_time(stop, allow_now=True)
    except ValueError as exc:
        raise _invalid_response() from exc
    return {"start": start, "stop": stop}


def _response_timestamp(body: dict[str, Any]) -> str:
    captured_at = body.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at:
        raise _invalid_response()
    try:
        parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid_response() from exc
    if parsed.tzinfo is None:
        raise _invalid_response()
    return captured_at


def _response_metadata(body: dict[str, Any]) -> dict[str, Any]:
    truncated = body.get("truncated")
    row_count = body.get("row_count")
    response_format = body.get("response_format")
    if (
        not isinstance(truncated, bool)
        or not isinstance(row_count, int)
        or isinstance(row_count, bool)
        or row_count < 0
        or response_format not in _RESPONSE_FORMATS
    ):
        raise _invalid_response()
    return {
        "truncated": truncated,
        "row_count": row_count,
        "response_format": response_format,
        "captured_at": _response_timestamp(body),
        "query_window": _response_window(body),
    }


def _load_query_token(mapping: ProxmoxMetricsInfluxDB) -> str:
    settings = ProxboxPluginSettings.get_solo()
    key = settings.encryption_key or ""
    if not key or not mapping.query_token_enc:
        raise MetricsProxyError("This metrics mapping has no usable query credential.")
    try:
        return mapping.get_query_token(key=key)
    except enc_helpers.EncryptionError as exc:
        raise MetricsProxyError(
            "The stored metrics credential requires recovery."
        ) from exc


def _build_query_filters(filters: dict[str, Any]) -> list[dict[str, str]]:
    query_filters = []
    for key, value in (
        ("node", filters.get("node")),
        ("vmid", filters.get("vmid")),
        (filters.get("tag_key"), filters.get("tag_value")),
    ):
        if key and value not in (None, ""):
            query_filters.append(
                {"scope": "tag", "key": str(key), "value": str(value), "operator": "=="}
            )
    return query_filters


def _build_aggregation(filters: dict[str, Any]) -> dict[str, str] | None:
    interval = filters.get("aggregation_every")
    function = filters.get("aggregation_function")
    if interval or function:
        if not interval or not function:
            raise MetricsProxyError(
                "Aggregation interval and function must be supplied together."
            )
        return {"every": interval, "function": function}
    return None


def _build_query_payload(
    mapping: ProxmoxMetricsInfluxDB,
    token: str,
    filters: dict[str, Any],
) -> dict[str, Any]:
    measurement = str(filters.get("measurement", "")).strip()
    if not measurement:
        raise MetricsProxyError("A measurement is required for a metrics query.")
    if mapping.measurement_prefix and not measurement.startswith(
        mapping.measurement_prefix
    ):
        measurement = f"{mapping.measurement_prefix}{measurement}"
    return {
        "url": mapping.influx_url,
        "org": mapping.org,
        "bucket": mapping.bucket,
        "token": token,
        "verify_ssl": mapping.verify_tls,
        "start": filters.get("time_start") or "-1h",
        "stop": None
        if filters.get("time_stop") in (None, "", "now()")
        else filters["time_stop"],
        "measurement": measurement,
        "field": filters.get("field") or None,
        "filters": _build_query_filters(filters),
        "aggregation": _build_aggregation(filters),
        "max_rows": filters.get("limit") or 500,
        "timeout_seconds": 10.0,
        "max_response_bytes": 1024 * 1024,
    }


def _safe_error_code(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get("reason")
    return body.get("error_code")


def _normalize_response(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise _invalid_response()
    columns = _response_columns(body)
    rows = _response_rows(body)
    normalized = {
        "columns": columns,
        "rows": rows,
        **_response_metadata(body),
    }
    if isinstance(body.get("limit"), int) and not isinstance(body["limit"], bool):
        normalized["limit"] = body["limit"]
    normalized["display_rows"] = [
        [row.get(column, "") for column in columns] for row in rows
    ]
    return normalized


def _post_backend_query(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    context: Any,
    timeout: tuple[int, int],
) -> requests.Response:
    session = requests.Session()
    session.trust_env = False
    try:
        return session.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout,
            verify=context.verify_ssl,
            allow_redirects=False,
            stream=True,
        )
    finally:
        session.close()


def _validate_mapping_enabled(mapping: ProxmoxMetricsInfluxDB) -> None:
    if not mapping.enabled:
        raise MetricsProxyError("This metrics mapping is disabled.")
    endpoint = getattr(mapping, "endpoint", None)
    if endpoint is not None and not endpoint.enabled:
        raise MetricsProxyError("The Proxmox endpoint for this mapping is disabled.")


def _backend_context() -> Any:
    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        raise MetricsProxyError(
            "No enabled proxbox-api backend endpoint is configured."
        )
    return context


def _backend_response_json(response: requests.Response) -> Any:
    content_length = response.headers.get("Content-Length")
    try:
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > MAX_PROXY_RESPONSE_BYTES
        ):
            raise MetricsProxyError(
                "The proxbox-api metrics backend response is too large."
            )
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_PROXY_RESPONSE_BYTES:
                raise MetricsProxyError(
                    "The proxbox-api metrics backend response is too large."
                )
            chunks.append(chunk)
        return json.loads(b"".join(chunks))
    except ValueError as exc:
        raise MetricsProxyError(
            "The proxbox-api metrics backend returned invalid JSON."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise MetricsProxyError(
            "The proxbox-api metrics backend could not be read."
        ) from exc
    finally:
        response.close()


def _raise_backend_error(response: requests.Response, body: Any) -> None:
    if response.status_code == 422:
        raise MetricsProxyError(
            "The metrics query was rejected by proxbox-api.", status_code=400
        )
    error_code = _safe_error_code(body)
    if error_code in _SAFE_ERROR_CODES:
        raise MetricsProxyError(
            f"The metrics backend rejected the request ({error_code})."
        )
    raise MetricsProxyError("The metrics backend rejected the request.")


def query_metrics(
    mapping: ProxmoxMetricsInfluxDB,
    filters: dict[str, Any],
    *,
    timeout: tuple[int, int] = (10, 60),
) -> dict[str, Any]:
    """Query proxbox-api without exposing InfluxDB credentials to the caller."""
    _validate_mapping_enabled(mapping)
    context = _backend_context()
    query_token = _load_query_token(mapping)
    payload = _build_query_payload(mapping, query_token, filters)
    url = f"{context.http_url.rstrip('/')}/proxmox/metrics/influx/query"
    headers = dict(context.headers or {})
    headers["Content-Type"] = "application/json"
    try:
        response = _post_backend_query(url, payload, headers, context, timeout)
    except requests.exceptions.RequestException as exc:
        raise MetricsProxyError(
            "The proxbox-api metrics backend could not be reached."
        ) from exc
    body = _backend_response_json(response)
    if not response.ok:
        _raise_backend_error(response, body)
    return _normalize_response(body)
