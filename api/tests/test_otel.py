"""Tests for OpenTelemetry SDK initialization module (api/app/otel.py).

All tests exercise the no-op path (OTEL_EXPORTER_OTLP_ENDPOINT unset) so they
run without the opentelemetry-sdk packages installed.
"""
import importlib
import os


def _reload_otel():
    """Return a freshly-imported otel module with _configured reset."""
    import app.otel as mod

    mod._configured = False
    return mod


class TestConfigureTelemetryNoop:
    def test_noop_when_endpoint_unset(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        otel = _reload_otel()
        # Should complete without error and set _configured = True
        otel.configure_telemetry("test-service", "test")
        assert otel._configured is True

    def test_idempotent(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        otel = _reload_otel()
        otel.configure_telemetry("svc", "dev")
        otel.configure_telemetry("svc", "dev")  # second call must not raise
        assert otel._configured is True

    def test_instrument_fastapi_noop_when_endpoint_unset(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        import app.otel as otel

        # Passing a fake app object must not raise
        otel.instrument_fastapi(object())

    def test_instrument_sqlalchemy_noop_when_endpoint_unset(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        import app.otel as otel

        otel.instrument_sqlalchemy_engine(object())


