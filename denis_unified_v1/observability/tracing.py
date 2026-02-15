"""Stub tracing module — provides no-op tracer for import compatibility."""

from contextlib import contextmanager


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


def get_tracer() -> _NoOpTracer:
    """Return a no-op tracer. Replace with OpenTelemetry when ready."""
    return _NoOpTracer()
