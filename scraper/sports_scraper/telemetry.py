"""OpenTelemetry SDK initialization for the scraper/Celery process.

Call init_telemetry() BEFORE the Celery app is created so CeleryInstrumentor
hooks into the signal system before any tasks are registered. All logic is a
no-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
"""
from __future__ import annotations

import logging
import os

_logger = logging.getLogger(__name__)
_configured = False


def init_telemetry(
    service_name: str = "sports-scraper",
    environment: str | None = None,
) -> None:
    """Initialize OTel trace + metrics for the Celery worker process.

    Must be called before Celery app creation so CeleryInstrumentor can attach
    to task_prerun / task_postrun / task_failure signals correctly.
    """
    global _configured
    if _configured:
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        _logger.info("otel_disabled — OTEL_EXPORTER_OTLP_ENDPOINT not set, skipping OTel setup")
        _configured = True
        return

    env = environment or os.getenv("ENVIRONMENT", "development")

    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({
        "service.name": service_name,
        "deployment.environment": env,
    })

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint),
        export_interval_millis=15_000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    # Hooks into task_prerun/postrun/failure signals — must run before app creation.
    CeleryInstrumentor().instrument()

    _configured = True
    _logger.info("otel_configured", extra={"service": service_name, "endpoint": endpoint})
