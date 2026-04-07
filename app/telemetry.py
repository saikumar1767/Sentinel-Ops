from __future__ import annotations

import logging
from collections.abc import Mapping
from contextlib import contextmanager

from fastapi import FastAPI

from app.settings import Settings

logger = logging.getLogger("sentinelops.telemetry")


def configure_telemetry(app: FastAPI, settings: Settings) -> None:
    if getattr(app.state, "telemetry_configured", False):
        return

    app.state.telemetry_configured = True
    app.state.telemetry_enabled = False
    app.state.telemetry_exporter = settings.telemetry_exporter

    if not settings.telemetry_enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except ImportError as exc:
        logger.warning("telemetry packages are not installed: %s", exc)
        app.state.telemetry_error = str(exc)
        return

    resource = Resource.create({"service.name": settings.telemetry_service_name})
    tracer_provider = TracerProvider(resource=resource)

    if settings.telemetry_exporter == "console":
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif settings.telemetry_exporter == "otlp":
        exporter = OTLPSpanExporter(endpoint=settings.telemetry_otlp_endpoint)
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(tracer_provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
    app.state.telemetry_enabled = True


@contextmanager
def start_span(name: str, attributes: Mapping[str, object] | None = None):
    try:
        from opentelemetry import trace
    except ImportError:
        yield None
        return

    tracer = trace.get_tracer("sentinelops")
    with tracer.start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            if value is None:
                continue
            span.set_attribute(key, _attribute_value(value))
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            raise


def set_span_attributes(span, attributes: Mapping[str, object] | None = None) -> None:
    if span is None or not attributes:
        return
    for key, value in attributes.items():
        if value is None:
            continue
        span.set_attribute(key, _attribute_value(value))


def _attribute_value(value: object) -> object:
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return str(value)
