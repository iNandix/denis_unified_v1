"""OpenTelemetry tracing setup.

Falls back to no-op stubs when opentelemetry is not installed,
so the rest of the codebase can import without hard dependency.
"""

import os
from contextlib import contextmanager

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


# ---------- no-op fallback ----------

class _NoOpSpan:
    def set_attribute(self, key: str, value) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _NoOpTracer:
    @contextmanager
    def start_as_current_span(self, name: str, **kwargs):
        yield _NoOpSpan()


def setup_tracing():
    """Configura OpenTelemetry con Jaeger exporter."""
    if not _HAS_OTEL:
        return _NoOpTracer()

    resource = Resource.create({
        "service.name": "denis-unified-v1",
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("ENVIRONMENT", "production"),
    })

    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    jaeger_host = os.getenv("JAEGER_HOST", "localhost")
    jaeger_port = int(os.getenv("JAEGER_PORT", "6831"))

    jaeger_exporter = JaegerExporter(
        agent_host_name=jaeger_host,
        agent_port=jaeger_port,
    )

    provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

    FastAPIInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()

    return trace.get_tracer(__name__)


def get_tracer():
    """Obtiene tracer global — returns no-op when OTel not installed."""
    if not _HAS_OTEL:
        return _NoOpTracer()
    return trace.get_tracer("denis.unified.v1")
