"""
Report Generation - Multi-level research reports.

Creates reports at different depth levels:
- Executive: 1-2 sentences, high-level summary
- Summary: ~200 words, key points
- Detailed: ~1000 words, full analysis
- Full: All data, sources, methodology
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ReportSection:
    """A section of the report."""

    title: str
    content: str
    level: int = 1
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchReport:
    """Complete research report."""

    query: str
    depth: str
    mode: str

    title: str = ""
    executive_summary: str = ""
    sections: List[ReportSection] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    chunks: List[Any] = field(default_factory=list)

    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    duration_ms: int = 0

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "depth": self.depth,
            "mode": self.mode,
            "title": self.title,
            "executive_summary": self.executive_summary,
            "sections": [
                {
                    "title": s.title,
                    "content": s.content,
                    "level": s.level,
                    "sources": s.sources,
                }
                for s in self.sections
            ],
            "sources": self.sources,
            "created_at": self.created_at,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Convert report to markdown format."""
        lines = []

        # Title
        lines.append(f"# {self.title or self.query}")
        lines.append("")
        lines.append(f"*Depth: {self.depth} | Mode: {self.mode} | {self.created_at}*")
        lines.append("")

        # Executive Summary
        if self.executive_summary:
            lines.append("## Executive Summary")
            lines.append("")
            lines.append(self.executive_summary)
            lines.append("")

        # Sections
        for section in self.sections:
            lines.append(f"{'#' * (section.level + 1)} {section.title}")
            lines.append("")
            lines.append(section.content)
            lines.append("")
            if section.sources:
                lines.append("*Sources: " + ", ".join(section.sources) + "*")
                lines.append("")

        # Sources
        if self.sources:
            lines.append("## Sources")
            lines.append("")
            for i, src in enumerate(self.sources, 1):
                url = src.get("url", "N/A")
                title = src.get("title", "Untitled")
                lines.append(f"{i}. [{title}]({url})")
            lines.append("")

        return "\n".join(lines)


class ReportGenerator:
    """Generate multi-level reports from research results."""

    def __init__(self):
        pass

    def generate(
        self,
        query: str,
        chunks: List[Any],
        sources: List[Dict[str, Any]],
        depth: str = "standard",
        mode: str = "user_pure",
    ) -> ResearchReport:
        """Generate complete report."""
        report = ResearchReport(
            query=query,
            depth=depth,
            mode=mode,
        )

        # Title
        report.title = self._generate_title(query, chunks)

        # Sort chunks by relevance
        sorted_chunks = sorted(chunks, key=lambda c: c.relevance_score, reverse=True)

        # Executive summary (always)
        report.executive_summary = self._generate_executive_summary(
            query, sorted_chunks
        )

        # Sections based on depth
        if depth in ("quick", "standard"):
            report.sections = self._generate_summary_sections(query, sorted_chunks)
        elif depth == "deep":
            report.sections = self._generate_detailed_sections(query, sorted_chunks)
        else:  # continuous
            report.sections = self._generate_full_sections(query, sorted_chunks)

        report.sources = sources
        report.chunks = sorted_chunks

        return report

    def _generate_title(self, query: str, chunks: List[Any]) -> str:
        """Generate report title from query."""
        # Capitalize first letter of each word
        words = query.split()
        title_words = []
        for word in words[:6]:  # Max 6 words
            if word.lower() not in (
                "a",
                "an",
                "the",
                "is",
                "are",
                "was",
                "were",
                "in",
                "on",
                "at",
                "to",
                "for",
            ):
                title_words.append(word.capitalize())
            else:
                title_words.append(word.lower())

        return " ".join(title_words)

    def _generate_executive_summary(self, query: str, chunks: List[Any]) -> str:
        """Generate 1-2 sentence executive summary."""
        if not chunks:
            return f"Research on '{query}' found no relevant information."

        # Use top 2-3 most relevant chunks
        top_chunks = chunks[:3]

        # Extract key sentences
        sentences = []
        for chunk in top_chunks:
            text = chunk.text
            # Take first substantial sentence
            for sent in text.split(". "):
                if len(sent) > 30:
                    sentences.append(sent.strip())
                    if len(sentences) >= 2:
                        break
            if len(sentences) >= 2:
                break

        if sentences:
            summary = ". ".join(sentences[:2])
            if not summary.endswith("."):
                summary += "."
            return summary

        return f"Based on research, {query} involves key aspects that include relevant findings from multiple sources."

    def _generate_summary_sections(
        self, query: str, chunks: List[Any]
    ) -> List[ReportSection]:
        """Generate summary-level sections (~200 words total)."""
        sections = []

        # Overview section
        overview_content = "## Key Findings\n\n"
        for chunk in chunks[:5]:
            # Take first 100 chars of relevant chunks
            snippet = chunk.text[:150].strip()
            if snippet:
                overview_content += f"- {snippet}...\n"

        sections.append(
            ReportSection(
                title="Overview",
                content=overview_content,
                level=1,
                sources=[c.source_url for c in chunks[:3] if c.source_url],
            )
        )

        return sections

    def _generate_detailed_sections(
        self, query: str, chunks: List[Any]
    ) -> List[ReportSection]:
        """Generate detailed sections (~1000 words)."""
        sections = []

        # Section 1: Main Findings
        findings_content = ""
        for chunk in chunks[:5]:
            if chunk.relevance_score > 0.5:
                findings_content += f"### {chunk.source_title or 'Finding'}\n\n"
                findings_content += chunk.text[:500] + "\n\n"

        sections.append(
            ReportSection(
                title="Main Findings",
                content=findings_content,
                level=1,
                sources=[c.source_url for c in chunks[:5] if c.source_url],
            )
        )

        # Section 2: Technical Details
        tech_chunks = [
            c
            for c in chunks
            if c.is_code or "code" in c.text.lower() or "function" in c.text.lower()
        ]
        if tech_chunks:
            tech_content = ""
            for chunk in tech_chunks[:3]:
                tech_content += f"**From {chunk.source_title or 'Source'}**\n\n"
                tech_content += chunk.text[:400] + "\n\n"

            sections.append(
                ReportSection(
                    title="Technical Details",
                    content=tech_content,
                    level=1,
                    sources=[c.source_url for c in tech_chunks[:3] if c.source_url],
                )
            )

        # Section 3: Additional Insights
        other_chunks = chunks[5:10]
        if other_chunks:
            insights_content = ""
            for chunk in other_chunks:
                insights_content += f"- {chunk.text[:200]}...\n"

            sections.append(
                ReportSection(
                    title="Additional Insights",
                    content=insights_content,
                    level=1,
                    sources=[c.source_url for c in other_chunks if c.source_url],
                )
            )

        return sections

    def _generate_full_sections(
        self, query: str, chunks: List[Any]
    ) -> List[ReportSection]:
        """Generate full sections with all data."""
        sections = self._generate_detailed_sections(query, chunks)

        # Add methodology section
        sections.insert(
            0,
            ReportSection(
                title="Methodology",
                content="This research was conducted using the following approach:\n\n"
                "1. Query classification and expansion\n"
                "2. Multi-engine search across relevant sources\n"
                "3. Content extraction and relevance scoring\n"
                "4. Chunking and organization by relevance\n"
                "5. Synthesis into structured report\n\n"
                "Sources were evaluated for reliability and cross-verified where possible.",
                level=1,
            ),
        )

        # Add all sources section at the end
        sections.append(
            ReportSection(
                title="All Sources",
                content="Full list of sources ordered by relevance:\n\n"
                + "\n".join(f"- {c.source_url}" for c in chunks if c.source_url),
                level=1,
            )
        )

        return sections

    def generate_executive(self, report: ResearchReport) -> str:
        """Extract just executive summary."""
        return report.executive_summary

    def generate_summary(self, report: ResearchReport) -> str:
        """Generate ~200 word summary."""
        sections = report.sections[:2]  # First 2 sections
        content = "\n\n".join(s.content for s in sections)

        # Truncate to ~200 words
        words = content.split()
        if len(words) > 200:
            content = " ".join(words[:200]) + "..."

        return content


def generate_report(
    query: str,
    chunks: List[Any],
    sources: List[Dict[str, Any]],
    depth: str = "standard",
    mode: str = "user_pure",
) -> ResearchReport:
    """Convenience function to generate report."""
    generator = ReportGenerator()
    return generator.generate(query, chunks, sources, depth, mode)
