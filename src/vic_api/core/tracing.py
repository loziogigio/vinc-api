from __future__ import annotations

import logging
from typing import Any, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ALWAYS_ON

from .config import Settings

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcExporter
except Exception:  # pragma: no cover
    OTLPGrpcExporter = None  # type: ignore

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHttpExporter
except Exception:  # pragma: no cover
    OTLPHttpExporter = None  # type: ignore

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
except Exception:  # pragma: no cover
    FastAPIInstrumentor = None  # type: ignore

try:
    from opentelemetry.instrumentation.redis import RedisInstrumentor
except Exception:  # pragma: no cover
    RedisInstrumentor = None  # type: ignore

try:
    from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
except Exception:  # pragma: no cover
    PymongoInstrumentor = None  # type: ignore

try:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
except Exception:  # pragma: no cover
    SQLAlchemyInstrumentor = None  # type: ignore


logger = logging.getLogger(__name__)

_tracing_configured = False
_instrumented_fastapi_ids: set[int] = set()
_instrumented_sqlalchemy = False
_instrumented_redis = False
_instrumented_pymongo = False


def init_tracing(settings: Settings) -> None:
    global _tracing_configured

    if _tracing_configured:
        return

    if not getattr(settings, "OTEL_ENABLED", True):
        logger.info("Tracing is disabled via configuration flag")
        return

    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if not endpoint:
        logger.info("Tracing is disabled; no OTLP endpoint configured")
        return

    protocol = (settings.OTEL_EXPORTER_OTLP_PROTOCOL or "grpc").lower()
    headers = settings.otel_headers_dict

    exporter = _create_exporter(protocol=protocol, endpoint=endpoint, headers=headers)
    if exporter is None:
        logger.warning("Tracing exporter not created (protocol=%s) -- disabling tracing", protocol)
        return

    sampler = _create_sampler(settings)

    resource_attributes: dict[str, Any] = {
        "service.name": settings.OTEL_SERVICE_NAME or settings.PROJECT_NAME,
        "service.version": "1.0.0",
        "deployment.environment": settings.ENV,
    }
    provider = TracerProvider(resource=Resource.create(resource_attributes), sampler=sampler)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    # Instrument client libraries eagerly when possible
    instrument_redis()
    instrument_pymongo()

    _tracing_configured = True
    logger.info("Tracing initialized with OTLP exporter", extra={"otel_endpoint": endpoint, "otel_protocol": protocol})


def instrument_fastapi(app, settings: Settings) -> None:
    if FastAPIInstrumentor is None:
        return

    if not _tracing_configured:
        return

    app_id = id(app)
    if app_id in _instrumented_fastapi_ids:
        return

    provider = trace.get_tracer_provider()

    try:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
        _instrumented_fastapi_ids.add(app_id)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to instrument FastAPI for tracing: %s", exc)


def instrument_sqlalchemy(engine) -> None:
    global _instrumented_sqlalchemy
    if SQLAlchemyInstrumentor is None or engine is None or _instrumented_sqlalchemy:
        return
    try:
        SQLAlchemyInstrumentor().instrument(engine=engine)
        _instrumented_sqlalchemy = True
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to instrument SQLAlchemy: %s", exc)


def instrument_redis() -> None:
    global _instrumented_redis
    if RedisInstrumentor is None or _instrumented_redis:
        return
    try:
        RedisInstrumentor().instrument()
        _instrumented_redis = True
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to instrument Redis: %s", exc)


def instrument_pymongo() -> None:
    global _instrumented_pymongo
    if PymongoInstrumentor is None or _instrumented_pymongo:
        return
    try:
        PymongoInstrumentor().instrument()
        _instrumented_pymongo = True
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to instrument MongoDB: %s", exc)


def _create_exporter(protocol: str, endpoint: str, headers: dict[str, str]):
    protocol = protocol.lower()
    if protocol == "grpc":
        if OTLPGrpcExporter is None:
            return None
        return OTLPGrpcExporter(endpoint=endpoint, headers=headers)
    if protocol in {"http", "http/protobuf", "http_protobuf"}:
        if OTLPHttpExporter is None:
            return None
        return OTLPHttpExporter(endpoint=endpoint, headers=headers)
    logger.warning("Unsupported OTLP protocol '%s'", protocol)
    return None


def _create_sampler(settings: Settings):
    ratio = settings.OTEL_SAMPLE_RATIO
    if ratio is None:
        return ALWAYS_ON
    ratio = max(0.0, min(1.0, ratio))
    if ratio >= 1.0:
        return ALWAYS_ON
    return TraceIdRatioBased(ratio)
