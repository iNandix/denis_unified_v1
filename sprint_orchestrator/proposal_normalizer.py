"""Normalize user proposal markdown into stable structured payload."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


@dataclass(frozen=True)
class NormalizedPhase:
    phase_id: str
    title: str
    bullets: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedProposal:
    title: str
    objective: str
    phases: list[NormalizedPhase]
    raw_sections: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "objective": self.objective,
            "phases": [item.as_dict() for item in self.phases],
            "raw_sections": list(self.raw_sections),
        }


def normalize_proposal_markdown(text: str) -> NormalizedProposal:
    clean = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in clean.splitlines()]
    title = _extract_title(lines)
    objective = _extract_objective(lines)
    phases = _extract_phases(lines)
    sections = _extract_sections(lines)
    return NormalizedProposal(
        title=title,
        objective=objective,
        phases=phases,
        raw_sections=sections[:40],
    )


def _extract_title(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    for line in lines:
        stripped = line.strip()
        if len(stripped) >= 8:
            return stripped[:140]
    return "Untitled Proposal"


def _extract_objective(lines: list[str]) -> str:
    joined = "\n".join(lines)
    patterns = [
        r"(?is)\bobjetivo\b\s*[:\-]\s*(.+?)(?:\n\n|\Z)",
        r"(?is)\bgoal\b\s*[:\-]\s*(.+?)(?:\n\n|\Z)",
    ]
    for pattern in patterns:
        match = re.search(pattern, joined)
        if match:
            return " ".join(match.group(1).strip().split())[:400]
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) > 24:
            return stripped[:400]
    return ""


def _extract_sections(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            out.append(stripped.lstrip("#").strip())
    return out


def _extract_phases(lines: list[str]) -> list[NormalizedPhase]:
    phase_headers: list[tuple[int, str, str]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        match = re.match(r"(?i)^(?:#{1,4}\s*)?(fase\s*\d+)\s*[:\-]?\s*(.*)$", stripped)
        if not match:
            continue
        phase_name = re.sub(r"\s+", "", match.group(1).upper()).replace("FASE", "F")
        title = match.group(2).strip() or match.group(1).strip().title()
        phase_headers.append((idx, phase_name, title))

    if not phase_headers:
        bullets = _extract_bullets(lines[:120])
        return [NormalizedPhase(phase_id="F1", title="Plan Inicial", bullets=bullets[:25])]

    out: list[NormalizedPhase] = []
    for pos, (line_idx, phase_id, title) in enumerate(phase_headers):
        end_idx = phase_headers[pos + 1][0] if pos + 1 < len(phase_headers) else len(lines)
        chunk = lines[line_idx + 1 : end_idx]
        bullets = _extract_bullets(chunk)[:40]
        out.append(NormalizedPhase(phase_id=phase_id, title=title, bullets=bullets))
    return out


def _extract_bullets(lines: list[str]) -> list[str]:
    bullets: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^[-*]\s+", stripped):
            bullets.append(re.sub(r"^[-*]\s+", "", stripped).strip())
            continue
        if re.match(r"^\d+\.\s+", stripped):
            bullets.append(re.sub(r"^\d+\.\s+", "", stripped).strip())
    return [item for item in bullets if item]
