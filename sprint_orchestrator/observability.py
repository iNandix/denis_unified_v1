"""Observability setup for Sprint Orchestrator with Prometheus metrics and OTel spans."""

from __future__ import annotations

from prometheus_client import Counter, start_http_server
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
import os

# Setup OTel
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)
span_processor = BatchSpanProcessor(ConsoleSpanExporter())
trace.get_tracer_provider().add_span_processor(span_processor)

# Setup Prometheus
if os.getenv("DENIS_SPRINT_METRICS_PORT"):
    port = int(os.getenv("DENIS_SPRINT_METRICS_PORT", "8001"))
    start_http_server(port)

# Metrics
sprint_sessions_total = Counter('sprint_sessions_total', 'Total sprint sessions created')
sprint_tasks_total = Counter('sprint_tasks_total', 'Total tasks by state', ['state'])
sprint_approvals_total = Counter('sprint_approvals_total', 'Total approvals by decision', ['decision'])
sprint_validations_total = Counter('sprint_validations_total', 'Total validations by status', ['status'])
sprint_worker_dispatch_total = Counter('sprint_worker_dispatch_total', 'Total dispatches by provider and status', ['provider', 'status'])
