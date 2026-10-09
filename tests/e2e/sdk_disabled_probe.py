"""Fresh-process regression probe for SDK-disabled native telemetry."""

from __future__ import annotations

import importlib
import json
import os
import sys
import threading
from collections import defaultdict
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

ROOT = Path(__file__).resolve().parents[2]
PAYLOADS: dict[str, list[bytes]] = defaultdict(list)
SECRET = "sdk-disabled-private-value"


class Collector(BaseHTTPRequestHandler):
    """Capture real OTLP HTTP/protobuf requests on loopback."""

    def do_POST(self) -> None:  # noqa: N802
        PAYLOADS[self.path].append(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: Any) -> None:  # noqa: ARG002
        """Suppress the loopback server access log."""


def assert_source_origins(module_name: str) -> None:
    """Prove broker imports resolve from the current worktree."""
    module = importlib.import_module(module_name)
    assert Path(module.__file__).resolve().is_relative_to(ROOT.resolve())
    telemetry = importlib.import_module("tests.e2e.mock_telemetry")
    assert Path(telemetry.__file__).resolve().is_relative_to(ROOT.resolve())


def make_providers(
    base_url: str,
) -> tuple[TracerProvider, MeterProvider, LoggerProvider]:
    """Create caller-owned providers with real loopback protobuf exporters."""
    tracer = TracerProvider()
    tracer.add_span_processor(
        SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{base_url}/v1/traces"))
    )
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{base_url}/v1/metrics"),
        export_interval_millis=60_000,
    )
    logger = LoggerProvider()
    logger.add_log_record_processor(
        SimpleLogRecordProcessor(OTLPLogExporter(endpoint=f"{base_url}/early/logs"))
    )
    return tracer, MeterProvider(metric_readers=[reader]), logger


def select_factory(name: str) -> Callable[..., FastAPI]:
    """Select the actual public mock factory from the current source."""
    assert name == "mock"
    assert_source_origins("tests.e2e.mock_proxmox_api")
    from tests.e2e.mock_proxmox_api import create_app

    return create_app


def exercise_lifespans(app: FastAPI, factory_name: str) -> None:
    """Exercise native success, validation, and error paths twice."""
    assert factory_name == "mock"

    @app.get("/__disabled/{number}")
    def number_route(number: int) -> dict[str, int]:
        return {"number": number}

    @app.get("/__disabled_error")
    def error_route() -> None:
        raise RuntimeError(SECRET)

    for _ in range(2):
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/__disabled/1").status_code == 200
            assert client.get(f"/__disabled/{SECRET}").status_code == 422
            assert client.get("/__disabled_error").status_code == 500


def emit_caller_signals(
    tracer: TracerProvider, meter: MeterProvider, logger: LoggerProvider, base_url: str
) -> None:
    """Emit caller signals after disabled application lifespans."""
    logger.add_log_record_processor(
        SimpleLogRecordProcessor(OTLPLogExporter(endpoint=f"{base_url}/v1/logs"))
    )
    with tracer.get_tracer("fastapi").start_as_current_span(
        "GET /private/{item}",
        attributes={"url.path": f"/private/{SECRET}", "url.query": f"token={SECRET}"},
    ):
        pass
    with tracer.get_tracer("caller.scope").start_as_current_span(
        "caller-span", attributes={"caller.attribute": SECRET}
    ):
        pass
    logger.get_logger("fastapi").emit(
        body="static-fastapi-body",
        attributes={
            "exception.type": "RuntimeError",
            "exception.message": SECRET,
            "exception.stacktrace": f"trace {SECRET}",
        },
    )
    logger.get_logger("caller.scope").emit(
        body=SECRET, attributes={"caller.attribute": SECRET}
    )
    meter.get_meter("caller.scope").create_counter("caller.counter").add(1)
    assert tracer.force_flush()
    assert logger.force_flush()
    assert meter.force_flush()


def decoded_spans() -> list[tuple[str, Any]]:
    """Flatten captured trace protobuf messages with their scope names."""
    requests = map(ExportTraceServiceRequest.FromString, PAYLOADS["/v1/traces"])
    return [
        (scope.scope.name, span)
        for request in requests
        for resource in request.resource_spans
        for scope in resource.scope_spans
        for span in scope.spans
    ]


def assert_trace_payloads() -> None:
    """Prove FastAPI trace redaction and unrelated-scope preservation."""
    spans = decoded_spans()
    fastapi_span = next(span for scope, span in spans if scope == "fastapi")
    fastapi_attrs = {
        item.key: item.value.string_value for item in fastapi_span.attributes
    }
    assert fastapi_attrs["url.path"] == "REDACTED"
    assert fastapi_attrs["url.query"] == "REDACTED"
    caller_span = next(span for scope, span in spans if scope == "caller.scope")
    assert any(
        item.key == "caller.attribute" and item.value.string_value == SECRET
        for item in caller_span.attributes
    )


def decoded_logs() -> list[tuple[str, Any]]:
    """Flatten captured log protobuf messages with their scope names."""
    requests = map(ExportLogsServiceRequest.FromString, PAYLOADS["/v1/logs"])
    return [
        (scope.scope.name, record)
        for request in requests
        for resource in request.resource_logs
        for scope in resource.scope_logs
        for record in scope.log_records
    ]


def assert_log_payloads() -> None:
    """Prove FastAPI exception redaction and unrelated-scope preservation."""
    records = decoded_logs()
    fastapi_log = next(record for scope, record in records if scope == "fastapi")
    assert fastapi_log.body.string_value == "static-fastapi-body"
    assert {item.key for item in fastapi_log.attributes} == {"exception.type"}
    caller_log = next(record for scope, record in records if scope == "caller.scope")
    assert caller_log.body.string_value == SECRET


def decoded_metrics(payloads: list[bytes]) -> list[tuple[str, Any]]:
    """Flatten captured metric protobuf messages with their scope names."""
    requests = map(ExportMetricsServiceRequest.FromString, payloads)
    return [
        (scope.scope.name, metric)
        for request in requests
        for resource in request.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    ]


def flush_disabled_metrics(meter: MeterProvider) -> list[bytes]:
    """Flush while disabled and prove no application metric was buffered."""
    assert os.environ["OTEL_SDK_DISABLED"] == "true"
    assert meter.force_flush()
    payloads = list(PAYLOADS["/v1/metrics"])
    assert not decoded_metrics(payloads)
    assert all(SECRET.encode() not in payload for payload in payloads)
    PAYLOADS["/v1/metrics"].clear()
    return payloads


def assert_metric_payloads(disabled_payloads: list[bytes]) -> None:
    """Reject application metrics and prove caller export after re-enablement."""
    assert not decoded_metrics(disabled_payloads)
    assert all(SECRET.encode() not in payload for payload in disabled_payloads)
    caller_payloads = PAYLOADS["/v1/metrics"]
    metrics_by_scope = {
        (scope, metric.name) for scope, metric in decoded_metrics(caller_payloads)
    }
    assert metrics_by_scope == {("caller.scope", "caller.counter")}
    assert all(SECRET.encode() not in payload for payload in caller_payloads)


def main() -> None:
    """Execute one factory/provider-mode combination."""
    factory_name, provider_mode = sys.argv[1:]
    server = ThreadingHTTPServer(("127.0.0.1", 0), Collector)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    os.environ["OTEL_SDK_DISABLED"] = "false"
    tracer, meter, logger = make_providers(base_url)
    before = (
        trace.get_tracer_provider(),
        metrics.get_meter_provider(),
        _logs.get_logger_provider(),
    )
    if provider_mode == "global":
        trace.set_tracer_provider(tracer)
        metrics.set_meter_provider(meter)
        _logs.set_logger_provider(logger)
        selected: dict[str, Any] = {}
    else:
        selected = {
            "tracer_provider": tracer,
            "meter_provider": meter,
            "logger_provider": logger,
        }
    caller_config = {
        "auto_configure": True,
        "tracing": True,
        "metrics": True,
        "logs": True,
        **selected,
    }
    original = dict(caller_config)
    os.environ["OTEL_SDK_DISABLED"] = "true"
    factory = select_factory(factory_name)
    app = factory(telemetry=caller_config)
    assert caller_config == original
    effective = app._telemetry
    assert all(
        effective[key] is False
        for key in ("auto_configure", "tracing", "metrics", "logs")
    )
    assert all(effective[key] is value for key, value in selected.items())
    if provider_mode == "explicit":
        assert before == (
            trace.get_tracer_provider(),
            metrics.get_meter_provider(),
            _logs.get_logger_provider(),
        )
    privacy_counts = (
        len(tracer._active_span_processor._span_processors),
        len(logger._multi_log_record_processor._log_record_processors),
    )
    second = factory(telemetry=caller_config)
    assert privacy_counts == (
        len(tracer._active_span_processor._span_processors),
        len(logger._multi_log_record_processor._log_record_processors),
    )
    exercise_lifespans(app, factory_name)
    disabled_metric_payloads = flush_disabled_metrics(meter)
    exercise_lifespans(second, factory_name)
    disabled_metric_payloads.extend(flush_disabled_metrics(meter))
    assert not {path: values for path, values in PAYLOADS.items() if values}, dict(
        PAYLOADS
    )
    emit_caller_signals(tracer, meter, logger, base_url)
    assert_trace_payloads()
    assert_log_payloads()
    assert_metric_payloads(disabled_metric_payloads)
    tracer.shutdown()
    meter.shutdown()
    logger.shutdown()
    server.shutdown()
    server.server_close()
    print(
        json.dumps(
            {
                "factory": factory_name,
                "provider_mode": provider_mode,
                "status": "passed",
            }
        )
    )


if __name__ == "__main__":
    main()
