"""Tests for Makina Filter - OpenCode Intent Router."""

import pytest


class TestMakinaFilter:
    """Tests for the makina filter module."""

    def test_basic_import(self):
        """Test that makina_filter can be imported."""
        from denis_unified_v1.inference.makina_filter import (
            filter_input,
            filter_input_safe,
            VERSION,
        )

        assert VERSION.startswith("1.0.")

    def test_greeting_returns_greeting_intent(self):
        """Test that greetings are detected correctly."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "hola"})

        assert result.intent["pick"] == "greeting"
        assert result.intent["confidence"] == 1.0
        assert len(result.intent_candidates) >= 1

    def test_short_question_returns_explain_concept(self):
        """Test that short questions are detected."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "qué es esto?"})

        assert result.intent["pick"] == "explain_concept"
        assert result.output_format == "text"

    def test_intent_candidates_sorted(self):
        """Test that intent candidates are sorted by score (highest first)."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "crea un nuevo componente y arréglame el bug"})

        assert len(result.intent_candidates) >= 2
        scores = [c["score"] for c in result.intent_candidates]
        assert scores == sorted(scores, reverse=True)

    def test_low_confidence_returns_unknown(self):
        """Test that low confidence (< 0.55) returns unknown intent."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "abc"})

        assert result.intent["pick"] == "unknown"
        assert result.intent["confidence"] == 0.0

    def test_trace_present_in_output(self):
        """Test that intent_trace is present in output."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "crea un test"})

        assert "intent_trace" in result.to_dict()
        assert "version" in result.intent_trace
        assert "matched_rules" in result.intent_trace
        assert "features" in result.intent_trace
        assert "reason" in result.intent_trace

    def test_trace_version_format(self):
        """Test that trace version follows expected format."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "haz algo"})

        assert result.intent_trace["version"].startswith("makina_filter@")

    def test_fail_open_on_exception(self):
        """Test that exceptions are handled gracefully with fail-open."""
        from denis_unified_v1.inference.makina_filter import filter_input_safe, MakinaOutput

        class BrokenInput:
            def __init__(self):
                pass

        result = filter_input_safe(BrokenInput())

        assert result.intent["pick"] == "unknown"
        assert result.intent["confidence"] == 0.0
        assert result.intent_trace["reason"] == "router_error"

    def test_tool_keyword_boost_crea(self):
        """Test that 'crea' boosts implement_feature intent."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "crea task para mí"})

        assert result.intent["pick"] == "implement_feature"
        assert result.intent["confidence"] > 0.5

    def test_tool_keyword_boost_reindexa(self):
        """Test that 'reindexa' boosts toolchain_task intent."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "reindexa la base de datos"})

        assert result.intent["pick"] == "toolchain_task"
        assert result.intent["confidence"] > 0.5

    def test_tool_keyword_boost_scrapea(self):
        """Test that 'scrapea' boosts toolchain_task intent."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "scrapea las noticias del periódico"})

        assert result.intent["pick"] == "toolchain_task"
        assert result.intent["confidence"] > 0.5

    def test_tool_keyword_boost_arregla(self):
        """Test that 'arregla' boosts debug_repo intent."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "arréglame el error"})

        assert result.intent["pick"] == "debug_repo"
        assert result.intent["confidence"] > 0.5

    def test_output_format_json_detection(self):
        """Test that JSON output format is detected."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "dame los datos en json"})

        assert result.output_format == "json"

    def test_output_format_code_detection(self):
        """Test that code output format is detected."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "escribe el código"})

        assert result.output_format == "code"

    def test_output_format_markdown_detection(self):
        """Test that markdown output format is detected."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "escribe en markdown"})

        assert result.output_format == "markdown"

    def test_contract_structure(self):
        """Test that output matches required contract structure."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "haz algo"})

        output = result.to_dict()

        assert "intent" in output
        assert "pick" in output["intent"]
        assert "confidence" in output["intent"]
        assert "intent_candidates" in output
        assert "intent_trace" in output
        assert "constraints" in output
        assert "context_refs" in output
        assert "acceptance_criteria" in output
        assert "output_format" in output
        assert "missing_inputs" in output

    def test_context_refs_passed_through(self):
        """Test that context_refs are passed through."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input(
            {"prompt": "haz algo", "context_refs": ["file:///test.py", "ref:123"]}
        )

        assert result.context_refs == ["file:///test.py", "ref:123"]

    def test_makina_input_object(self):
        """Test that MakinaInput object works."""
        from denis_unified_v1.inference.makina_filter import MakinaInput, filter_input

        input_obj = MakinaInput(prompt="crea un test", context_refs=["ref:1"])
        result = filter_input(input_obj)

        assert result.intent["pick"] == "implement_feature"

    def test_no_intent_returns_unknown(self):
        """Test that prompts with no matching keywords return unknown."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "asdfghjkl qwerty"})

        assert result.intent["pick"] == "unknown"
        assert "no_keywords" in result.intent_trace["matched_rules"]

    def test_debug_flag_env_variable(self, monkeypatch):
        """Test that debug events are controlled by env variable."""
        import os
        from denis_unified_v1.inference.makina_filter import filter_input

        monkeypatch.setenv("MAKINA_FILTER_DEBUG", "0")
        result = filter_input({"prompt": "crea algo"})
        assert "features" in result.intent_trace


class TestMakinaFilterEdgeCases:
    """Edge case tests for makina filter."""

    def test_empty_prompt(self):
        """Test handling of empty prompt."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": ""})

        assert result.intent["pick"] == "unknown"

    def test_very_long_prompt(self):
        """Test handling of very long prompt."""
        from denis_unified_v1.inference.makina_filter import filter_input

        long_prompt = " ".join(["crea"] * 1000)
        result = filter_input({"prompt": long_prompt})

        assert result.intent["pick"] == "implement_feature"

    def test_mixed_case_keywords(self):
        """Test that keywords work regardless of case."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "CREA un archivo"})

        assert result.intent["pick"] == "implement_feature"

    def test_spanish_and_english_keywords(self):
        """Test that both Spanish and English keywords work."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result_es = filter_input({"prompt": "arréglame el bug"})
        result_en = filter_input({"prompt": "fix the bug"})

        assert result_es.intent["pick"] == "debug_repo"
        assert result_en.intent["pick"] == "debug_repo"

    def test_multiple_intents_in_prompt(self):
        """Test that multiple intents produce multiple candidates."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "crea test y arregla el error"})

        assert len(result.intent_candidates) >= 2
        intent_names = [c["name"] for c in result.intent_candidates]
        assert "implement_feature" in intent_names
        assert "debug_repo" in intent_names
