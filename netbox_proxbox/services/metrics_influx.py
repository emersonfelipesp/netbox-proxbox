"""Server-side proxy for retrieving Proxmox metrics through proxbox-api."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
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
_RESPONSE_FORMATS = {"annotated_csv", "json", "proxmox_export"}
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
    "pull_invalid_response",
    "pull_response_too_large",
    "pull_unavailable",
}

_CANONICAL_COLUMNS = [
    "object_id",
    "metric",
    "timestamp",
    "value",
    "metric_type",
    "source",
    "also_seen_in",
    "conflict",
]
_INFLUX_METRIC_ALIASES = {
    "cpu": "cpu_current",
    "cpus": "cpu_max",
    "mem": "mem_used",
    "maxmem": "mem_total",
    "memused": "mem_used",
    "memtotal": "mem_total",
    "diskread": "disk_read",
    "diskwrite": "disk_write",
    "disk": "disk_used",
    "maxdisk": "disk_total",
    "netin": "net_in",
    "netout": "net_out",
    "swaptotal": "swap_total",
    "swapused": "swap_used",
}
_DURATION_PART = re.compile(r"(\d+)(ns|us|µs|ms|mo|s|m|h|d|w|y)")
_DURATION_SECONDS = {
    "ns": 1e-9,
    "us": 1e-6,
    "µs": 1e-6,
    "ms": 1e-3,
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "mo": 2592000,
    "y": 31536000,
}


def _enabled_backend_endpoint_scope(**kwargs: Any) -> tuple:
    """Resolve backend endpoint IDs without widening this module's import surface."""
    from netbox_proxbox.services.endpoint_scope import enabled_backend_endpoint_scope

    return enabled_backend_endpoint_scope(**kwargs)


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
    node = filters.get("node")
    if node:
        node_key = "nodename" if filters.get("vmid") is not None else "host"
        query_filters.append(
            {"scope": "tag", "key": node_key, "value": str(node), "operator": "=="}
        )
    for key, value in (
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
        "field": None,
        "fields": _influx_field_aliases(filters.get("field")),
        "filters": _build_query_filters(filters),
        "aggregation": _build_aggregation(filters),
        "max_rows": filters.get("limit") or 500,
        "timeout_seconds": 10.0,
        "max_response_bytes": 1024 * 1024,
    }


def _influx_field_aliases(value: Any) -> list[str]:
    if not value:
        return []
    requested = str(value)
    canonical = _INFLUX_METRIC_ALIASES.get(requested, requested)
    aliases = [
        influx
        for influx, normalized in _INFLUX_METRIC_ALIASES.items()
        if normalized == canonical
    ]
    return list(dict.fromkeys([*aliases, canonical]))


def _time_to_epoch(value: str, *, now: datetime) -> int:
    """Convert a validated relative duration or RFC3339 time to Unix seconds."""
    if value.startswith("-"):
        parts = _DURATION_PART.findall(value[1:])
        if not parts or "".join(f"{count}{unit}" for count, unit in parts) != value[1:]:
            raise MetricsProxyError(
                "The pull metrics start time is invalid.", status_code=400
            )
        seconds = sum(int(count) * _DURATION_SECONDS[unit] for count, unit in parts)
        return max(0, int((now - timedelta(seconds=seconds)).timestamp()))
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetricsProxyError(
            "The pull metrics start time is invalid.", status_code=400
        ) from exc
    return int(parsed.timestamp())


def _build_pull_payload(
    mapping: ProxmoxMetricsInfluxDB,
    filters: dict[str, Any],
    *,
    now: datetime,
    backend_endpoint_id: int,
) -> dict[str, Any]:
    object_ids: list[str] = []
    if filters.get("node"):
        object_ids.append(f"node/{filters['node']}")
    if filters.get("vmid") is not None:
        object_ids.extend((f"qemu/{filters['vmid']}", f"lxc/{filters['vmid']}"))
    raw_field = str(filters.get("field") or "")
    metric_names = (
        [_INFLUX_METRIC_ALIASES.get(raw_field, raw_field)] if raw_field else []
    )
    return {
        "source": "database",
        "endpoint_id": backend_endpoint_id,
        "start_time": _time_to_epoch(filters.get("time_start") or "-1h", now=now),
        "history": True,
        "local_only": False,
        "object_ids": object_ids,
        "metric_names": metric_names,
        "max_rows": filters.get("limit") or 500,
        "max_response_bytes": MAX_PROXY_RESPONSE_BYTES,
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


def _query_backend(
    *,
    context: Any,
    path: str,
    payload: dict[str, Any],
    timeout: tuple[int, int],
) -> dict[str, Any]:
    url = f"{context.http_url.rstrip('/')}{path}"
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


def _canonical_object_id(row: dict[str, Any]) -> str:
    object_type = str(row.get("object") or "").lower()
    tagged_id = _tagged_object_id(row, object_type)
    if tagged_id:
        return tagged_id
    candidate = row.get("object_id") or row.get("id")
    if isinstance(candidate, str) and candidate:
        return candidate
    raise _invalid_response()


def _tagged_object_id(row: dict[str, Any], object_type: str) -> str | None:
    vmid = row.get("vmid")
    if object_type in {"qemu", "lxc"} and vmid not in (None, ""):
        return f"{object_type}/{vmid}"
    host = row.get("host")
    if object_type in {"node", "nodes"} and host:
        return f"node/{host}"
    nodename = row.get("nodename")
    if object_type in {"storage", "storages"} and nodename and host:
        return f"storage/{nodename}/{host}"
    return None


def _timestamp_nanoseconds(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value * 1_000_000_000
    if isinstance(value, float) and math.isfinite(value):
        value = str(value)
    if isinstance(value, str):
        numeric = value.strip()
        try:
            nanoseconds = Decimal(numeric) * 1_000_000_000
        except InvalidOperation:
            nanoseconds = None
        if nanoseconds is not None:
            if nanoseconds != nanoseconds.to_integral_value():
                raise _invalid_response()
            return int(nanoseconds)

        match = re.fullmatch(
            r"(?P<base>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
            r"(?:\.(?P<fraction>\d{1,9}))?(?P<zone>Z|[+-]\d{2}:\d{2})",
            numeric,
        )
        if match is None:
            raise _invalid_response()
        zone = "+00:00" if match.group("zone") == "Z" else match.group("zone")
        try:
            parsed = datetime.fromisoformat(f"{match.group('base')}{zone}")
        except ValueError as exc:
            raise _invalid_response() from exc
        if parsed.tzinfo is None:
            raise _invalid_response()
        delta = parsed.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
        seconds = delta.days * 86_400 + delta.seconds
        fraction = int((match.group("fraction") or "0").ljust(9, "0"))
        return seconds * 1_000_000_000 + fraction
    raise _invalid_response()


def _canonical_timestamp(value: Any) -> tuple[int | float, int]:
    nanoseconds = _timestamp_nanoseconds(value)
    seconds, fraction = divmod(nanoseconds, 1_000_000_000)
    if fraction == 0:
        return seconds, nanoseconds
    return float(Decimal(nanoseconds) / 1_000_000_000), nanoseconds


def _canonical_row(row: dict[str, Any], source: str) -> dict[str, Any]:
    raw_metric = row.get("metric") if source == "pull" else row.get("_field")
    raw_timestamp = row.get("timestamp") if source == "pull" else row.get("_time")
    value = row.get("value") if source == "pull" else row.get("_value")
    if not isinstance(raw_metric, str) or not raw_metric or value is None:
        raise _invalid_response()
    metric = _INFLUX_METRIC_ALIASES.get(raw_metric, raw_metric)
    timestamp, timestamp_nanoseconds = _canonical_timestamp(raw_timestamp)
    return {
        "object_id": _canonical_object_id(row),
        "metric": metric,
        "timestamp": timestamp,
        "_timestamp_ns": timestamp_nanoseconds,
        "value": value,
        "metric_type": row.get("metric_type") if source == "pull" else None,
        "source": source,
        "also_seen_in": [],
        "conflict": False,
    }


def _normalized_source_rows(
    result: dict[str, Any], source: str
) -> list[dict[str, Any]]:
    return [_canonical_row(row, source) for row in result["rows"]]


def _canonicalize_result(
    result: dict[str, Any], source: str, filters: dict[str, Any]
) -> dict[str, Any]:
    rows = _normalized_source_rows(result, source)
    rows = _apply_canonical_filters(rows, filters, source=source)
    rows.sort(
        key=lambda row: (
            row["timestamp"],
            row["object_id"],
            row["metric"],
            str(row["value"]),
        )
    )
    normalized = dict(result)
    normalized["rows"] = rows
    normalized["row_count"] = len(rows)
    return normalized


def _apply_canonical_filters(
    rows: list[dict[str, Any]], filters: dict[str, Any], *, source: str
) -> list[dict[str, Any]]:
    field = str(filters.get("field") or "")
    metric = _INFLUX_METRIC_ALIASES.get(field, field)
    vmid = filters.get("vmid")
    node_filter_is_provider_side = source == "influx" and vmid is not None
    node_id = (
        f"node/{filters['node']}"
        if filters.get("node") and not node_filter_is_provider_side
        else ""
    )
    vm_ids = {f"qemu/{vmid}", f"lxc/{vmid}"} if vmid is not None else set()
    return [row for row in rows if _row_matches(row, metric, node_id, vm_ids)]


def _row_matches(
    row: dict[str, Any], metric: str, node_id: str, vm_ids: set[str]
) -> bool:
    if metric and row["metric"] != metric:
        return False
    if node_id and row["object_id"] != node_id:
        return False
    return not vm_ids or row["object_id"] in vm_ids


def _reconcile_rows(
    influx_rows: list[dict[str, Any]], pull_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, int]:
    merged: dict[tuple[str, str, int], dict[str, Any]] = {}
    duplicates = 0
    conflicts = 0
    for row in [*pull_rows, *influx_rows]:
        timestamp_identity = row.get("_timestamp_ns")
        if timestamp_identity is None:
            timestamp_identity = _timestamp_nanoseconds(row["timestamp"])
        identity = (row["object_id"], row["metric"], timestamp_identity)
        previous = merged.get(identity)
        if previous is None:
            merged[identity] = dict(row)
            continue
        observed_sources = {
            previous["source"],
            row["source"],
            *previous.get("also_seen_in", []),
            *row.get("also_seen_in", []),
        }
        if previous["value"] == row["value"]:
            duplicates += 1
            winner = dict(row if row["source"] == "influx" else previous)
            winner["conflict"] = bool(previous["conflict"] or row["conflict"])
            winner["also_seen_in"] = sorted(observed_sources - {winner["source"]})
            merged[identity] = winner
            continue
        conflicts += 1
        winner = dict(row if row["source"] == "influx" else previous)
        winner["conflict"] = True
        winner["also_seen_in"] = sorted(observed_sources - {winner["source"]})
        merged[identity] = winner
    rows = sorted(
        (
            {key: value for key, value in row.items() if key != "_timestamp_ns"}
            for row in merged.values()
        ),
        key=lambda row: (row["timestamp"], row["object_id"], row["metric"]),
    )
    return rows, duplicates, conflicts


def _combined_response(
    results: dict[str, dict[str, Any]],
    failures: dict[str, MetricsProxyError],
    *,
    limit: int,
    stop_epoch: int | None,
) -> dict[str, Any]:
    influx_rows = _source_rows_or_empty(results, "influx")
    pull_rows = _source_rows_or_empty(results, "pull")
    if stop_epoch is not None:
        pull_rows = [row for row in pull_rows if row["timestamp"] <= stop_epoch]
    rows, duplicates, conflicts = _reconcile_rows(influx_rows, pull_rows)
    reconciliation_truncated = len(rows) > limit
    rows = rows[:limit]
    status = _source_status(results, failures)
    captured_at = max(
        (result["captured_at"] for result in results.values()),
        default=datetime.now(UTC).isoformat(),
    )
    truncated = reconciliation_truncated or any(
        result["truncated"] for result in results.values()
    )
    response = {
        "columns": _CANONICAL_COLUMNS,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "query_window": next(iter(results.values()))["query_window"],
        "captured_at": captured_at,
        "response_format": "reconciled",
        "source_mode": "reconciled" if len(status) > 1 else next(iter(status)),
        "source_status": status,
        "partial": bool(failures),
        "deduplicated_count": duplicates,
        "conflict_count": conflicts,
    }
    response["display_rows"] = [
        [row.get(column, "") for column in _CANONICAL_COLUMNS] for row in rows
    ]
    return response


def _source_rows_or_empty(
    results: dict[str, dict[str, Any]], source: str
) -> list[dict[str, Any]]:
    if source not in results:
        return []
    return results[source]["rows"]


def _source_status(
    results: dict[str, dict[str, Any]], failures: dict[str, MetricsProxyError]
) -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}
    for source in ("influx", "pull"):
        if source in results:
            status[source] = {
                "status": "ok",
                "row_count": len(results[source]["rows"]),
            }
        elif source in failures:
            status[source] = {
                "status": "error",
                "row_count": 0,
                "error": str(failures[source]),
            }
    return status


def _requested_sources(source_mode: str) -> tuple[str, ...]:
    return ("influx", "pull") if source_mode == "reconciled" else (source_mode,)


def _validate_source_query(requested: tuple[str, ...], filters: dict[str, Any]) -> None:
    if "influx" in requested and not str(filters.get("measurement") or "").strip():
        raise MetricsProxyError(
            "A measurement is required when the source includes InfluxDB.",
            status_code=400,
        )
    if "pull" in requested:
        _validate_pull_filters(filters)


def _validate_pull_filters(filters: dict[str, Any]) -> None:
    if filters.get("aggregation_every") or filters.get("aggregation_function"):
        raise MetricsProxyError(
            "Aggregation is unavailable when the source includes Proxmox API pull.",
            status_code=400,
        )
    if filters.get("tag_key"):
        raise MetricsProxyError(
            "Tag filters are unavailable when the source includes Proxmox API pull.",
            status_code=400,
        )
    if filters.get("node") and filters.get("vmid") is not None:
        raise MetricsProxyError(
            "A node and VM ID cannot be combined when the source includes Proxmox API pull.",
            status_code=400,
        )


def _query_source(
    source: str,
    mapping: ProxmoxMetricsInfluxDB,
    filters: dict[str, Any],
    *,
    context: Any,
    timeout: tuple[int, int],
    now: datetime,
) -> dict[str, Any]:
    if source == "influx":
        payload = _build_query_payload(mapping, _load_query_token(mapping), filters)
        path = "/proxmox/metrics/influx/query"
    else:
        _, backend_ids, error = _enabled_backend_endpoint_scope(
            base_url=context.http_url,
            auth_headers=context.headers or {},
            backend_verify_ssl=context.verify_ssl,
            endpoint_ids=[mapping.endpoint.pk],
        )
        backend_endpoint_id = backend_ids.get(mapping.endpoint.pk)
        if error or backend_endpoint_id is None:
            raise MetricsProxyError(
                "The Proxmox endpoint is not registered on the metrics backend."
            )
        payload = _build_pull_payload(
            mapping,
            filters,
            now=now,
            backend_endpoint_id=backend_endpoint_id,
        )
        path = "/proxmox/metrics/pull/query"
    return _query_backend(context=context, path=path, payload=payload, timeout=timeout)


def query_metrics(
    mapping: ProxmoxMetricsInfluxDB,
    filters: dict[str, Any],
    *,
    timeout: tuple[int, int] = (10, 60),
) -> dict[str, Any]:
    """Query the persisted source policy and return reconciled canonical rows."""
    _validate_mapping_enabled(mapping)
    context = _backend_context()
    requested = _requested_sources(mapping.source_mode)
    _validate_source_query(requested, filters)
    results: dict[str, dict[str, Any]] = {}
    failures: dict[str, MetricsProxyError] = {}
    now = datetime.now(UTC)
    for source in requested:
        try:
            result = _query_source(
                source,
                mapping,
                filters,
                context=context,
                timeout=timeout,
                now=now,
            )
            results[source] = _canonicalize_result(result, source, filters)
        except MetricsProxyError as exc:
            failures[source] = exc
    if not results:
        raise next(iter(failures.values()))
    stop = filters.get("time_stop")
    stop_epoch = (
        None if stop in (None, "", "now()") else _time_to_epoch(str(stop), now=now)
    )
    return _combined_response(
        results,
        failures,
        limit=int(filters.get("limit") or 500),
        stop_epoch=stop_epoch,
    )
