"""Exercise FastAPI's excluded nested-request context on the actual mock."""

import asyncio
from typing import Any

import httpx
import pytest
from fastapi.telemetry._api import _REQUEST_TELEMETRY_KEY
from opentelemetry import context as otel_context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind


async def _exercise_nested_context(application: Any, fail: bool) -> list[Any]:
    """Check exclusion isolation and restoration on normal and error paths."""
    observed = []

    @application.get("/excluded-context-probe")
    async def excluded() -> dict[str, bool]:
        observed.append(otel_context.get_value(_REQUEST_TELEMETRY_KEY))
        if fail:
            raise RuntimeError("The excluded-request failure is intentional.")
        return {"excluded": True}

    @application.get("/parent-context-probe")
    async def parent() -> dict[str, int]:
        inherited = otel_context.get_value(_REQUEST_TELEMETRY_KEY)
        assert inherited is not None
        transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://local.test"
        ) as client:
            response = await client.get("/excluded-context-probe")
        assert otel_context.get_value(_REQUEST_TELEMETRY_KEY) is inherited
        return {"nested_status": response.status_code}

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://local.test"
    ) as client:
        response = await client.get("/parent-context-probe")
    assert response.status_code == 200
    assert response.json() == {"nested_status": 500 if fail else 200}
    return observed


@pytest.mark.parametrize("fail", [False, True])
def test_excluded_nested_request_restores_context(
    fail: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove the current native context fix through the mock factory."""
    from tests.e2e.mock_proxmox_api import create_app

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    original = otel_context.get_value(_REQUEST_TELEMETRY_KEY)
    provider = TracerProvider(sampler=ALWAYS_ON)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        application = create_app(
            telemetry={
                "auto_configure": False,
                "tracing": True,
                "metrics": False,
                "logs": False,
                "tracer_provider": provider,
                "exclude": lambda scope: scope["path"] == "/excluded-context-probe",
            }
        )
        assert asyncio.run(_exercise_nested_context(application, fail)) == [None]
        assert otel_context.get_value(_REQUEST_TELEMETRY_KEY) is original
        exported = exporter.get_finished_spans()
        assert not any("excluded-context-probe" in span.name for span in exported)
        spans = [span for span in exported if span.kind is SpanKind.SERVER]
        assert len(spans) == 1
        assert spans[0].name == "GET /parent-context-probe"
        assert spans[0].kind is SpanKind.SERVER
    finally:
        provider.shutdown()
