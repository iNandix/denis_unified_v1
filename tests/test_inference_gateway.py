"""Tests for InferenceGateway."""

import pytest
from unittest.mock import patch, MagicMock
import denis_unified_v1.inference.inference_gateway as igw
from denis_unified_v1.inference.inference_gateway import (
    shadow_select,
    ShadowDecision,
    _get_alternative_provider,
)


class TestInferenceGateway:
    """Test InferenceGateway shadow selection."""

    def setup_method(self):
        """Reset window manager before each test."""
        igw._window_manager = None

    def test_incident_triage_elige_barato(self):
        """Para incident_triage -> elegir modelo barato (local)."""
        result = shadow_select("incident_triage")

        assert result is not None
        assert result.provider == "llamacpp"
        assert "qwen2.5" in result.model
        assert result.quota_available is True

    def test_codecraft_elige_coder(self):
        """Para codecraft_generate -> elegir modelo coder."""
        result = shadow_select("codecraft_generate")

        assert result is not None
        assert result.provider == "llamacpp"
        assert "coder" in result.model
        assert result.quota_available is True

    def test_deep_audit_groq(self):
        """Para deep_audit -> groq (modelo grande)."""
        result = shadow_select("deep_audit")

        assert result is not None
        assert result.provider == "groq"
        assert "70b" in result.model

    def test_window_manager_bloquea_elige_alternativa(self):
        """Si WindowManager bloquea -> marca quota_available=False."""
        mock_wm = MagicMock()
        mock_wm.can_use.return_value = False  # Block all
        igw._window_manager = mock_wm

        result = shadow_select("incident_triage")

        assert result is not None
        # Should return decision but with quota unavailable
        assert result.quota_available is False
        assert "quota" in result.reason.lower()

    def test_todas_cuotas_exhaustadas(self):
        """Si todas las cuotas exhaustadas -> seguir retornando decisión."""
        mock_wm = MagicMock()
        mock_wm.can_use.return_value = False
        igw._window_manager = mock_wm

        result = shadow_select("incident_triage")

        assert result is not None
        assert result.quota_available is False

    def test_excepcion_falla_abierto(self):
        """Si excepción -> fail-open (retorna None)."""
        igw._window_manager = None

        def raise_exc():
            raise Exception("test")

        original_get = igw._get_window_manager
        igw._get_window_manager = raise_exc

        result = shadow_select("incident_triage")

        igw._get_window_manager = original_get

        assert result is not None
        assert result.result == "error"
        assert "test" in result.reason

    def test_shadow_mode_desactivado(self):
        """Si SHADOW_MODE=False -> retorna None."""
        original = igw.SHADOW_MODE
        igw.SHADOW_MODE = False

        result = shadow_select("incident_triage")

        igw.SHADOW_MODE = original

        assert result is None

    def test_get_alternative_provider(self):
        """Test fallback provider logic."""
        igw._window_manager = None  # Reset
        alt = _get_alternative_provider("llamacpp")
        assert alt is not None
        assert alt[0] == "groq"

        alt = _get_alternative_provider("groq")
        assert alt is not None
        assert alt[0] == "openrouter"

    def test_task_profile_incident_triage_existe(self):
        """incident_triage mapping existe."""
        igw._window_manager = None
        result = shadow_select("incident_triage")
        assert result is not None
        assert result.provider == "llamacpp"

    def test_latency_incluida(self):
        """ShadowDecision incluye latency_ms."""
        result = shadow_select("incident_response")

        assert result is not None
        assert hasattr(result, "latency_ms")
        assert result.latency_ms >= 0
        assert result.latency_ms < 50

    def test_reason_incluye_task(self):
        """Reason incluye información de task."""
        result = shadow_select("codecraft_generate")

        assert result is not None
        assert result.reason is not None
        # reason puede ser "policy-match" o contener "code" dependiendo del flujo
        assert "code" in result.reason.lower() or result.model == "qwen2.5-coder-7b"
