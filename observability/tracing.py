"""OpenTelemetry tracing setup."""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
import os

def setup_tracing():
    """Configura OpenTelemetry con Jaeger exporter."""
    
    # Resource identification
    resource = Resource.create({
        "service.name": "denis-unified-v1",
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("ENVIRONMENT", "production"),
    })
    
    # Tracer provider
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)
    
    # Jaeger exporter
    jaeger_host = os.getenv("JAEGER_HOST", "localhost")
    jaeger_port = int(os.getenv("JAEGER_PORT", "6831"))
    
    jaeger_exporter = JaegerExporter(
        agent_host_name=jaeger_host,
        agent_port=jaeger_port,
    )
    
    provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
    
    # Auto-instrument FastAPI and httpx
    FastAPIInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    
    return trace.get_tracer(__name__)

def get_tracer():
    """Obtiene tracer global."""
    return trace.get_tracer("denis.unified.v1")
