"""
OutputContract - Enforces output mode based on task_profile.

Defines how output should be delivered:
- text: inline text response
- json: inline JSON response
- artifact_ref: reference to artifact file

Validates output size and enforces artifact creation when threshold exceeded.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from denis_unified_v1.inference.artifactizer import Artifactizer, ArtifactRef

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT_THRESHOLD_BYTES = int(
    os.getenv("DENIS_ARTIFACT_THRESHOLD_BYTES", "32768")
)  # 32KB

MAX_ARTIFACT_ABSOLUTE_BYTES = int(
    os.getenv("DENIS_MAX_ARTIFACT_ABSOLUTE_BYTES", "1048576")
)  # 1MB max


class OutputMode:
    TEXT = "text"
    JSON = "json"
    ARTIFACT_REF = "artifact_ref"


class OutputContractError(Exception):
    """Base exception for OutputContract."""

    pass


class UnknownTaskProfileError(OutputContractError):
    """Unknown task_profile."""

    pass


class InvalidOutputModeError(OutputContractError):
    """Invalid output mode."""

    pass


class ArtifactWriteFailedError(OutputContractError):
    """Failed to write artifact."""

    pass


_TASK_PROFILE_OUTPUT_MODES: Dict[str, str] = {
    "intent_detection_fast": OutputMode.TEXT,
    "pro_search_prepare_fast": OutputMode.TEXT,
    "tool_runner_read_only": OutputMode.TEXT,
    "summarize_artifact": OutputMode.TEXT,
    "codecraft_generate": OutputMode.ARTIFACT_REF,
    "deep_audit": OutputMode.JSON,
    "premium_search": OutputMode.TEXT,
    "incident_response": OutputMode.TEXT,
    "incident_triage": OutputMode.TEXT,
}

_VALID_OUTPUT_MODES = {OutputMode.TEXT, OutputMode.JSON, OutputMode.ARTIFACT_REF}


@dataclass
class EnforcedOutput:
    """Output after enforcement."""

    mode: str
    content: str
    artifacts: List[ArtifactRef]
    was_artifactized: bool = False
    error: Optional[str] = None


class OutputContract:
    """Enforces output contract based on task_profile with strict validation."""

    def __init__(
        self,
        artifact_threshold: int = DEFAULT_ARTIFACT_THRESHOLD_BYTES,
        max_absolute_bytes: int = MAX_ARTIFACT_ABSOLUTE_BYTES,
        artifactizer: Optional[Artifactizer] = None,
    ):
        if artifact_threshold <= 0:
            raise ValueError("artifact_threshold must be positive")
        if max_absolute_bytes <= 0:
            raise ValueError("max_absolute_bytes must be positive")
        if artifact_threshold > max_absolute_bytes:
            raise ValueError("artifact_threshold cannot exceed max_absolute_bytes")

        self.artifact_threshold = artifact_threshold
        self.max_absolute_bytes = max_absolute_bytes
        self.artifactizer = artifactizer or Artifactizer()

    def get_output_mode(self, task_profile_id: str) -> str:
        """Get the expected output mode for a task_profile."""
        mode = _TASK_PROFILE_OUTPUT_MODES.get(task_profile_id, OutputMode.TEXT)
        if mode not in _VALID_OUTPUT_MODES:
            raise InvalidOutputModeError(f"Invalid output mode: {mode}")
        return mode

    def _validate_task_profile(self, task_profile_id: str) -> None:
        """Validate task_profile_id."""
        if not task_profile_id or not isinstance(task_profile_id, str):
            raise UnknownTaskProfileError("task_profile_id must be a non-empty string")

    def _normalize_error(self, error: Exception) -> str:
        """Normalize error to known types."""
        error_type = type(error).__name__
        error_msg = str(error)[:200]

        if "UnknownTaskProfileError" in error_type or "unknown" in error_msg.lower():
            return "unknown_task_profile"
        if "InvalidOutputModeError" in error_type or "invalid" in error_msg.lower():
            return "invalid_output_mode"
        if "ArtifactWriteError" in error_type or "write" in error_msg.lower():
            return "artifact_write_failed"

        return f"unknown_error: {error_type}"

    def enforce(
        self,
        output: Union[str, Dict[str, Any]],
        task_profile_id: str,
    ) -> EnforcedOutput:
        """
        Enforce output contract with strict validation.

        Args:
            output: The raw output (str or dict)
            task_profile_id: The task profile ID

        Returns:
            EnforcedOutput with mode, content, artifacts, and optional error
        """
        try:
            self._validate_task_profile(task_profile_id)
        except Exception as e:
            return EnforcedOutput(
                mode=OutputMode.TEXT,
                content="",
                artifacts=[],
                was_artifactized=False,
                error=self._normalize_error(e),
            )

        try:
            content = str(output) if not isinstance(output, dict) else str(output)
        except Exception as e:
            return EnforcedOutput(
                mode=OutputMode.TEXT,
                content="",
                artifacts=[],
                was_artifactized=False,
                error=f"invalid_output_type: {type(output).__name__}",
            )

        try:
            output_mode = self.get_output_mode(task_profile_id)
        except Exception as e:
            return EnforcedOutput(
                mode=OutputMode.TEXT,
                content=content[:1000],
                artifacts=[],
                was_artifactized=False,
                error=self._normalize_error(e),
            )

        content_bytes = len(content.encode("utf-8"))
        artifacts = []

        if content_bytes > self.max_absolute_bytes:
            logger.warning(
                f"Output size {content_bytes} exceeds max_absolute_bytes {self.max_absolute_bytes}, truncating"
            )
            content = content[: self.max_absolute_bytes]
            content_bytes = len(content.encode("utf-8"))

        if content_bytes > self.artifact_threshold:
            logger.info(
                f"Output size {content_bytes} bytes exceeds threshold {self.artifact_threshold}, artifactizing"
            )
            try:
                artifact = self.artifactizer.create_artifact(
                    content=content,
                    artifact_type="json" if output_mode == OutputMode.JSON else "text",
                    metadata={
                        "task_profile": task_profile_id,
                        "original_size": content_bytes,
                    },
                )
                artifacts.append(artifact)

                return EnforcedOutput(
                    mode=OutputMode.ARTIFACT_REF,
                    content=f"Output artifactized. See: {artifact.path}",
                    artifacts=artifacts,
                    was_artifactized=True,
                )
            except Exception as e:
                logger.error(f"Failed to create artifact: {e}")
                return EnforcedOutput(
                    mode=output_mode,
                    content=content[: self.artifact_threshold],
                    artifacts=[],
                    was_artifactized=False,
                    error=self._normalize_error(e),
                )

        return EnforcedOutput(
            mode=output_mode,
            content=content,
            artifacts=artifacts,
            was_artifactized=False,
        )


_default_contract: Optional[OutputContract] = None


def get_output_contract() -> OutputContract:
    """Get default OutputContract instance."""
    global _default_contract
    if _default_contract is None:
        _default_contract = OutputContract()
    return _default_contract
