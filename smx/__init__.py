"""Optional SMX shim for fail-open imports."""

try:
    import smx  # pragma: no cover
except Exception:
    pass
