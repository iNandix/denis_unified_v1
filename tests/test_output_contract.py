"""Tests for OutputContract and Artifactizer."""

import os
import tempfile
import pytest
import shutil


class TestArtifactizer:
    """Tests for Artifactizer."""

    def test_create_text_artifact(self):
        """Test creating a text artifact."""
        from denis_unified_v1.inference.artifactizer import Artifactizer

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = Artifactizer(artifacts_dir=tmpdir)

            content = "Hello, this is a test artifact!"
            artifact = artifactizer.create_artifact(content, artifact_type="text")

            assert artifact.path.endswith(".txt")
            assert artifact.artifact_type == "text"
            assert artifact.size_bytes > 0
            assert artifact.hash is not None

            # Verify content was saved
            with open(artifact.path, "r") as f:
                saved = f.read()
            assert saved == content

    def test_create_json_artifact(self):
        """Test creating a JSON artifact."""
        from denis_unified_v1.inference.artifactizer import Artifactizer

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = Artifactizer(artifacts_dir=tmpdir)

            content = '{"key": "value", "number": 42}'
            artifact = artifactizer.create_artifact(content, artifact_type="json")

            assert artifact.path.endswith(".json")
            assert artifact.artifact_type == "json"

            # Verify JSON was pretty-printed
            with open(artifact.path, "r") as f:
                saved = f.read()
            assert '"key"' in saved

    def test_create_large_artifact(self):
        """Test creating a large artifact."""
        from denis_unified_v1.inference.artifactizer import Artifactizer

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = Artifactizer(artifacts_dir=tmpdir)

            # Create content larger than 1KB
            content = "x" * 2000
            artifact = artifactizer.create_artifact(content, artifact_type="text")

            assert artifact.size_bytes == 2000
            assert artifact.hash is not None

    def test_get_artifact(self):
        """Test retrieving artifact content."""
        from denis_unified_v1.inference.artifactizer import Artifactizer

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = Artifactizer(artifacts_dir=tmpdir)

            content = "Test content"
            artifact = artifactizer.create_artifact(content, artifact_type="text")

            retrieved = artifactizer.get_artifact(artifact.path)
            assert retrieved == content

    def test_get_artifact_not_found(self):
        """Test retrieving non-existent artifact."""
        from denis_unified_v1.inference.artifactizer import Artifactizer

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = Artifactizer(artifacts_dir=tmpdir)

            result = artifactizer.get_artifact("/nonexistent/path.txt")
            assert result is None


class TestOutputContract:
    """Tests for OutputContract."""

    def test_small_output_text_mode(self):
        """Test small output stays inline in text mode."""
        from denis_unified_v1.inference.output_contract import OutputContract

        with tempfile.TemporaryDirectory() as tmpdir:
            contract = OutputContract(
                artifact_threshold=1000,
                artifactizer=__import__(
                    "denis_unified_v1.inference.artifactizer",
                    fromlist=["Artifactizer"],
                ).Artifactizer(artifacts_dir=tmpdir),
            )

            output = "Short output"
            result = contract.enforce(output, "intent_detection_fast")

            assert result.mode == "text"
            assert result.content == output
            assert len(result.artifacts) == 0
            assert result.was_artifactized is False

    def test_large_output_creates_artifact(self):
        """Test large output is artifactized."""
        from denis_unified_v1.inference.output_contract import OutputContract
        from denis_unified_v1.inference.artifactizer import Artifactizer

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = Artifactizer(artifacts_dir=tmpdir)
            contract = OutputContract(artifact_threshold=100, artifactizer=artifactizer)

            # Create output larger than threshold
            output = "x" * 200
            result = contract.enforce(output, "intent_detection_fast")

            assert result.mode == "artifact_ref"
            assert len(result.artifacts) == 1
            assert result.was_artifactized is True

    def test_json_output_mode(self):
        """Test JSON output mode."""
        from denis_unified_v1.inference.output_contract import OutputContract

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = __import__(
                "denis_unified_v1.inference.artifactizer",
                fromlist=["Artifactizer"],
            ).Artifactizer(artifacts_dir=tmpdir)
            contract = OutputContract(
                artifact_threshold=1000, artifactizer=artifactizer
            )

            output = '{"key": "value"}'
            result = contract.enforce(output, "deep_audit")

            assert result.mode == "json"

    def test_codecraft_artifact_mode(self):
        """Test codecraft_generate defaults to artifact mode."""
        from denis_unified_v1.inference.output_contract import OutputContract

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = __import__(
                "denis_unified_v1.inference.artifactizer",
                fromlist=["Artifactizer"],
            ).Artifactizer(artifacts_dir=tmpdir)
            contract = OutputContract(
                artifact_threshold=1000, artifactizer=artifactizer
            )

            mode = contract.get_output_mode("codecraft_generate")
            assert mode == "artifact_ref"

    def test_unknown_task_profile_defaults_to_text(self):
        """Test unknown task_profile defaults to text mode."""
        from denis_unified_v1.inference.output_contract import OutputContract

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = __import__(
                "denis_unified_v1.inference.artifactizer",
                fromlist=["Artifactizer"],
            ).Artifactizer(artifacts_dir=tmpdir)
            contract = OutputContract(
                artifact_threshold=1000, artifactizer=artifactizer
            )

            mode = contract.get_output_mode("unknown_profile")
            assert mode == "text"

    def test_dict_input_converted_to_string(self):
        """Test dict input is converted to string."""
        from denis_unified_v1.inference.output_contract import OutputContract

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = __import__(
                "denis_unified_v1.inference.artifactizer",
                fromlist=["Artifactizer"],
            ).Artifactizer(artifacts_dir=tmpdir)
            contract = OutputContract(
                artifact_threshold=1000, artifactizer=artifactizer
            )

            output = {"key": "value", "nested": {"a": 1}}
            result = contract.enforce(output, "intent_detection_fast")

            assert "key" in result.content
            assert "value" in result.content


class TestNoLargeInlinePayloads:
    """B5: Tests for no large inline payloads."""

    def test_large_json_always_becomes_artifact(self):
        """Test that JSON output exceeding threshold becomes artifact_ref."""
        from denis_unified_v1.inference.output_contract import OutputContract

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = __import__(
                "denis_unified_v1.inference.artifactizer",
                fromlist=["Artifactizer"],
            ).Artifactizer(artifacts_dir=tmpdir)
            contract = OutputContract(artifact_threshold=100, artifactizer=artifactizer)

            large_json = '{"key": "' + "x" * 200 + '"}'
            result = contract.enforce(large_json, "deep_audit")

            assert result.mode == "artifact_ref"
            assert result.was_artifactized is True
            assert len(result.artifacts) == 1
            assert result.artifacts[0].artifact_type == "json"

    def test_large_text_always_becomes_artifact(self):
        """Test that text output exceeding threshold becomes artifact_ref."""
        from denis_unified_v1.inference.output_contract import OutputContract

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = __import__(
                "denis_unified_v1.inference.artifactizer",
                fromlist=["Artifactizer"],
            ).Artifactizer(artifacts_dir=tmpdir)
            contract = OutputContract(artifact_threshold=100, artifactizer=artifactizer)

            large_text = "x" * 200
            result = contract.enforce(large_text, "intent_detection_fast")

            assert result.mode == "artifact_ref"
            assert result.was_artifactized is True

    def test_exactly_threshold_is_inline(self):
        """Test that output exactly at threshold stays inline."""
        from denis_unified_v1.inference.output_contract import OutputContract

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = __import__(
                "denis_unified_v1.inference.artifactizer",
                fromlist=["Artifactizer"],
            ).Artifactizer(artifacts_dir=tmpdir)
            contract = OutputContract(artifact_threshold=100, artifactizer=artifactizer)

            exactly_100 = "x" * 100
            result = contract.enforce(exactly_100, "intent_detection_fast")

            assert result.was_artifactized is False
            assert result.mode == "text"

    def test_just_over_threshold_becomes_artifact(self):
        """Test that output just over threshold becomes artifact_ref."""
        from denis_unified_v1.inference.output_contract import OutputContract

        with tempfile.TemporaryDirectory() as tmpdir:
            artifactizer = __import__(
                "denis_unified_v1.inference.artifactizer",
                fromlist=["Artifactizer"],
            ).Artifactizer(artifacts_dir=tmpdir)
            contract = OutputContract(artifact_threshold=100, artifactizer=artifactizer)

            just_over = "x" * 101
            result = contract.enforce(just_over, "intent_detection_fast")

            assert result.was_artifactized is True
            assert result.mode == "artifact_ref"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
