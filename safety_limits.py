import fnmatch
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass(frozen=True)
class SafetyVerdict:
    ok: bool
    decision: str  # "allow" | "block" | "degraded_allow"
    reason: str
    matched_rule: Optional[str] = None


class SafetyLimits:
    """
    Minimal safety layer for auto-modification.
    Deterministic: pure function of (path, patch_text, mode).
    Fail-open: if internal error, returns degraded_allow with reason.
    """

    def __init__(
        self,
        protected_globs: Optional[List[str]] = None,
        banned_tokens: Optional[List[str]] = None,
        allow_globs: Optional[List[str]] = None,
    ) -> None:
        self.protected_globs = protected_globs or [
            "metacognitive/hooks.py",
            "api/*",
            "orchestration/*",
            "safety_limits.py",
        ]
        self.allow_globs = allow_globs or [
            "artifacts/*",
            "scripts/*",
            "*.md",
        ]
        self.banned_tokens = banned_tokens or [
            "rm -rf",
            "reset --hard",
            "shred",
            "mkfs",
            "dd if=",
            "chmod 777",
        ]

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    def check_change(self, path: str, patch_text: str, mode: str = "enforce") -> Dict[str, Any]:
        """
        Returns dict for easy JSON artifact usage.
        mode:
          - "enforce": block protected paths and banned tokens
          - "audit": never block (ok True) but still reports findings
        """
        start = time.time()
        try:
            findings: List[Dict[str, Any]] = []

            protected_hit = next((g for g in self.protected_globs if fnmatch.fnmatch(path, g)), None)
            allow_hit = next((g for g in self.allow_globs if fnmatch.fnmatch(path, g)), None)

            if protected_hit:
                findings.append({"type": "protected_path", "rule": protected_hit})

            token_hit = None
            lowered = patch_text.lower()
            for tok in self.banned_tokens:
                if tok.lower() in lowered:
                    token_hit = tok
                    findings.append({"type": "banned_token", "rule": tok})
                    break

            # Decide
            if mode == "audit":
                verdict = SafetyVerdict(ok=True, decision="allow", reason="audit_mode")
            else:
                if protected_hit:
                    verdict = SafetyVerdict(ok=False, decision="block", reason="protected_path", matched_rule=protected_hit)
                elif token_hit:
                    verdict = SafetyVerdict(ok=False, decision="block", reason="banned_token", matched_rule=token_hit)
                else:
                    # If not explicitly allowed, still allow (fail-open) but mark reason.
                    if allow_hit:
                        verdict = SafetyVerdict(ok=True, decision="allow", reason="allowlisted_path", matched_rule=allow_hit)
                    else:
                        verdict = SafetyVerdict(ok=True, decision="degraded_allow", reason="not_allowlisted")

            latency_ms = (time.time() - start) * 1000.0
            return {
                "ok": verdict.ok,
                "decision": verdict.decision,
                "reason": verdict.reason,
                "matched_rule": verdict.matched_rule,
                "path": path,
                "patch_sha256": self._hash(patch_text),
                "findings": findings,
                "mode": mode,
                "latency_ms": latency_ms,
                "timestamp_utc": _utc_now(),
            }
        except Exception as e:
            # fail-open
            latency_ms = (time.time() - start) * 1000.0
            return {
                "ok": True,
                "decision": "degraded_allow",
                "reason": "safety_internal_error",
                "matched_rule": None,
                "path": path,
                "patch_sha256": self._hash(patch_text),
                "findings": [{"type": "internal_error", "error": str(e)}],
                "mode": mode,
                "latency_ms": latency_ms,
                "timestamp_utc": _utc_now(),
            }
