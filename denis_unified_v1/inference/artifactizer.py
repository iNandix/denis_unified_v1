"""
Artifactizer - Creates and manages artifacts for large outputs.

When output exceeds threshold:
- Saves content to /artifacts directory (atomic: tmp -> rename)
- Returns reference with path and hash
- Supports text and JSON content
- Retention policy: max files or TTL
"""

import hashlib
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = os.getenv(
    "DENIS_ARTIFACTS_DIR",
    "/media/jotah/SSD_denis/home_jotah/denis_unified_v1/artifacts",
)

DENIS_ARTIFACT_MAX_FILES = int(os.getenv("DENIS_ARTIFACT_MAX_FILES", "100"))
DENIS_ARTIFACT_TTL_HOURS = int(os.getenv("DENIS_ARTIFACT_TTL_HOURS", "168"))  # 1 week

ARTIFACT_LOCK = threading.Lock()


@dataclass
class ArtifactRef:
    """Reference to an artifact."""

    path: str
    hash: str
    artifact_type: str
    size_bytes: int
    created_at: str
    metadata: Dict[str, Any]


class ArtifactizerError(Exception):
    """Base exception for Artifactizer."""

    pass


class ArtifactWriteError(ArtifactizerError):
    """Failed to write artifact."""

    pass


class Artifactizer:
    """Creates and manages artifacts with atomic writes and retention policy."""

    def __init__(
        self,
        artifacts_dir: Optional[str] = None,
        max_files: int = DENIS_ARTIFACT_MAX_FILES,
        ttl_hours: int = DENIS_ARTIFACT_TTL_HOURS,
    ):
        self.artifacts_dir = Path(artifacts_dir or ARTIFACTS_DIR)
        self.max_files = max_files
        self.ttl_hours = ttl_hours
        self._ensure_artifacts_dir()

    def _ensure_artifacts_dir(self):
        """Ensure artifacts directory exists."""
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content - deterministic."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def _generate_filename(self, artifact_type: str, hash: str) -> str:
        """Generate deterministic artifact filename (no timestamp)."""
        ext = "json" if artifact_type == "json" else "txt"
        return f"artifact_{hash}.{ext}"

    def _atomic_write(self, filepath: Path, content: str) -> None:
        """Atomic write: tmp file then rename."""
        dir_path = filepath.parent
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".tmp_artifact_")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.rename(tmp_path, filepath)
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise ArtifactWriteError(f"Failed to write artifact: {e}") from e

    def _enforce_retention(self) -> None:
        """Enforce retention policy: max files and TTL."""
        try:
            artifacts = sorted(
                self.artifacts_dir.glob("artifact_*.txt"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            json_artifacts = sorted(
                self.artifacts_dir.glob("artifact_*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            all_artifacts = artifacts + json_artifacts

            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.ttl_hours)

            to_delete = []

            for f in all_artifacts:
                if len(to_delete) >= len(all_artifacts) - self.max_files:
                    break
                to_delete.append(f)

            for f in to_delete:
                try:
                    f.unlink()
                    meta = f.with_suffix(f.suffix + ".meta.json")
                    if meta.exists():
                        meta.unlink()
                    logger.info(f"Deleted old artifact: {f}")
                except OSError as e:
                    logger.warning(f"Failed to delete artifact {f}: {e}")

            for f in all_artifacts:
                if f.stat().st_mtime < cutoff_time.timestamp():
                    try:
                        f.unlink()
                        meta = f.with_suffix(f.suffix + ".meta.json")
                        if meta.exists():
                            meta.unlink()
                        logger.info(f"Deleted expired artifact: {f}")
                    except OSError as e:
                        logger.warning(f"Failed to delete expired artifact {f}: {e}")

        except Exception as e:
            logger.warning(f"Retention policy enforcement failed: {e}")

    def create_artifact(
        self,
        content: str,
        artifact_type: str = "text",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactRef:
        """
        Create an artifact from content (atomic write).

        Args:
            content: The content to save
            artifact_type: "text" or "json"
            metadata: Optional metadata

        Returns:
            ArtifactRef with path and hash
        """
        with ARTIFACT_LOCK:
            self._enforce_retention()

            content_hash = self._compute_hash(content)
            filename = self._generate_filename(artifact_type, content_hash)
            filepath = self.artifacts_dir / filename

            if filepath.exists():
                logger.info(f"Artifact already exists: {filepath}")
                size_bytes = len(content.encode("utf-8"))
                return ArtifactRef(
                    path=str(filepath),
                    hash=content_hash,
                    artifact_type=artifact_type,
                    size_bytes=size_bytes,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    metadata=metadata or {},
                )

            tmp_content = content
            if artifact_type == "json":
                try:
                    parsed = json.loads(content)
                    tmp_content = json.dumps(parsed, indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    pass

            self._atomic_write(filepath, tmp_content)

            size_bytes = len(content.encode("utf-8"))

            meta = {
                "artifact_type": artifact_type,
                "original_hash": content_hash,
                "size_bytes": size_bytes,
                "created_at": datetime.now(timezone.utc).isoformat(),
                **(metadata or {}),
            }
            meta_path = self.artifacts_dir / f"{filename}.meta.json"
            self._atomic_write(meta_path, json.dumps(meta, indent=2))

            logger.info(f"Created artifact: {filepath} ({size_bytes} bytes)")

            return ArtifactRef(
                path=str(filepath),
                hash=content_hash,
                artifact_type=artifact_type,
                size_bytes=size_bytes,
                created_at=meta["created_at"],
                metadata=meta,
            )

    def get_artifact(self, path: str) -> Optional[str]:
        """Retrieve artifact content by path."""
        try:
            with open(path, "r") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"Artifact not found: {path}")
            return None

    def list_artifacts(self, limit: int = 50) -> list[ArtifactRef]:
        """List recent artifacts."""
        artifacts = []
        try:
            all_files = sorted(
                self.artifacts_dir.glob("artifact_*.txt"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )[:limit]

            for f in all_files:
                if f.suffix == ".meta.json":
                    continue
                try:
                    with open(f, "r") as fp:
                        content = fp.read()
                    hash_val = self._compute_hash(content)
                    artifacts.append(
                        ArtifactRef(
                            path=str(f),
                            hash=hash_val,
                            artifact_type="text",
                            size_bytes=len(content.encode("utf-8")),
                            created_at=datetime.now(timezone.utc).isoformat(),
                            metadata={},
                        )
                    )
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Error listing artifacts: {e}")
        return artifacts


_default_artifactizer: Optional[Artifactizer] = None


def get_artifactizer() -> Artifactizer:
    """Get default Artifactizer instance."""
    global _default_artifactizer
    if _default_artifactizer is None:
        _default_artifactizer = Artifactizer()
    return _default_artifactizer
