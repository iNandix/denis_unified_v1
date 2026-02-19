"""
Chunk Classifier - Enterprise-level metadata for chunks.

Data Types:
- DOC: Documentation
- TUTORIAL: How-to guides
- API_REF: API references
- CODE: Programming code
- CONFIG: Configuration
- BENCHMARK: Performance data
- CLAIM: Factual claims
- NEWS: Current events
- DISCUSSION: Forum/social
- CHANGELOG: Release notes
- SECURITY_ADIVSORY: Security alerts
"""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class DataType(Enum):
    """Type of data in the chunk."""

    DOC = "doc"
    TUTORIAL = "tutorial"
    API_REF = "api_ref"
    CODE = "code"
    CONFIG = "config"
    BENCHMARK = "benchmark"
    CLAIM = "claim"
    NEWS = "news"
    DISCUSSION = "discussion"
    CHANGELOG = "changelog"
    SECURITY_ADVISORY = "security_advisory"
    UNKNOWN = "unknown"


class VerificationStatus(Enum):
    """Verification status of the chunk."""

    UNVERIFIED = "unverified"
    PARTIALLY_VERIFIED = "partially_verified"
    CROSS_VERIFIED = "cross_verified"
    CONTRADICTED = "contradicted"


class SourceReliability(Enum):
    """Reliability score of the source."""

    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


RELIABLE_DOMAINS = {
    "arxiv.org",
    "scholar.google",
    "pubmed.ncbi.nlm.nih.gov",
    "ieee.org",
    "acm.org",
    "nature.com",
    "science.org",
    "wikipedia.org",
    "docs.python.org",
    "developer.mozilla.org",
    "docs.microsoft.com",
    "cloud.google.com",
    "docs.aws.amazon.com",
    "developer.apple.com",
    "github.com",
    "stackoverflow.com",
    "medium.com",
    "dev.to",
    "reuters.com",
    "bbc.com",
    "nytimes.com",
    "theguardian.com",
}

LESS_RELIABLE_DOMAINS = {
    "twitter.com",
    "x.com",
    "facebook.com",
    "reddit.com",
    "youtube.com",
    "instagram.com",
    "tiktok.com",
}


@dataclass
class Source:
    """Source entity for chunk provenance."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    domain: str = ""
    url: str = ""
    reliability_score: float = 0.5
    bias_flags: List[str] = field(default_factory=list)
    topic_tags: List[str] = field(default_factory=list)
    created_ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ChunkMetadata:
    """Enterprise-level metadata for chunks."""

    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_ts: str = ""
    request_id: str = ""
    session_id: str = ""
    turn_id: str = ""
    source_id: str = ""
    url: str = ""
    content_hash: str = ""

    data_type: DataType = DataType.UNKNOWN
    domain: str = ""
    topic_tags: List[str] = field(default_factory=list)
    language: str = ""
    entity_refs: List[str] = field(default_factory=list)

    source_reliability_score: float = 0.5

    chunk_quality_score: float = 0.5
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    cross_verify_count: int = 0
    unique_domains_count: int = 1

    relevance_score: float = 0.0
    utility_probability: float = 0.5
    freshness_score: float = 0.5

    risk_flags: List[str] = field(default_factory=list)

    word_count: int = 0
    has_citations: bool = False
    has_examples: bool = False
    is_outdated: bool = False


@dataclass
class ClassifiedChunk:
    """A chunk with classification metadata."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    metadata: ChunkMetadata = field(default_factory=ChunkMetadata)


class ChunkClassifier:
    """Enterprise chunk classifier."""

    DATA_TYPE_PATTERNS = {
        DataType.CODE: [
            r"^```\w+",
            r"^def\s+\w+",
            r"^class\s+\w+",
            r"^function\s+\w+",
            r"^const\s+\w+",
            r"^let\s+\w+",
            r"^import\s+\w+",
            r"^from\s+\w+\s+import",
            r"async\s+def",
            r"=>\s*{",
            r"fn\s+\w+\(",
            r"func\s+\w+\(",
        ],
        DataType.TUTORIAL: [
            r"how to",
            r"step by step",
            r"walkthrough",
            r"getting started",
            r"follow these steps",
            r"in this guide",
        ],
        DataType.API_REF: [
            r"api reference",
            r"parameters:",
            r"returns:",
            r"attributes:",
            r"endpoint",
            r"http method",
            r"request body",
        ],
        DataType.CONFIG: [
            r"\.json$",
            r"\.yaml$",
            r"\.yml$",
            r"\.toml$",
            r"\.ini$",
            r"config",
            r"settings",
            r"options",
            r"environment",
        ],
        DataType.BENCHMARK: [
            r"benchmark",
            r"performance",
            r"ops/sec",
            r"latency",
            r"throughput",
        ],
        DataType.CLAIM: [
            r"research shows",
            r"studies show",
            r"according to",
            r"it is known that",
        ],
        DataType.NEWS: [
            r"announced",
            r"released",
            r"breaking",
            r"update:",
            r"recently",
        ],
        DataType.DISCUSSION: [
            r"reddit",
            r"forum",
            r"discuss",
            r"opinion",
            r"i think",
        ],
        DataType.CHANGELOG: [
            r"changelog",
            r"release notes",
            r"version \d+",
            r"breaking changes",
        ],
        DataType.SECURITY_ADVISORY: [
            r"security",
            r"vulnerability",
            r"cve-",
            r"exploit",
            r"patch",
            r"advisory",
            r"alert",
            r"breach",
        ],
    }

    TOPIC_KEYWORDS = {
        "programming": [
            "function",
            "variable",
            "class",
            "method",
            "api",
            "library",
            "framework",
            "code",
        ],
        "science": [
            "research",
            "study",
            "experiment",
            "hypothesis",
            "data",
            "analysis",
        ],
        "business": ["revenue", "market", "customer", "profit", "growth", "strategy"],
        "technology": [
            "software",
            "hardware",
            "network",
            "system",
            "platform",
            "cloud",
        ],
        "health": [
            "patient",
            "treatment",
            "symptom",
            "diagnosis",
            "disease",
            "medicine",
        ],
        "security": ["vulnerability", "exploit", "attack", "patch", "cve", "malware"],
        "ai_ml": [
            "machine learning",
            "deep learning",
            "neural",
            "model",
            "training",
            "inference",
        ],
    }

    FRESHNESS_TTL = {
        DataType.NEWS: 7,
        DataType.DISCUSSION: 30,
        DataType.SECURITY_ADVISORY: 14,
        DataType.CHANGELOG: 90,
        DataType.DOC: 365,
        DataType.TUTORIAL: 180,
        DataType.CODE: 365,
    }

    def __init__(self):
        self.stop_words = frozenset(
            {
                "the",
                "a",
                "an",
                "and",
                "or",
                "but",
                "in",
                "on",
                "at",
                "to",
                "for",
                "of",
                "with",
                "by",
                "from",
                "as",
                "is",
                "was",
                "are",
                "were",
                "be",
            }
        )

    def classify(self, chunk) -> ChunkMetadata:
        """Classify chunk with enterprise metadata."""
        text = chunk.text if hasattr(chunk, "text") else str(chunk)
        metadata = ChunkMetadata()

        if hasattr(chunk, "id") and chunk.id:
            metadata.chunk_id = chunk.id

        metadata.word_count = len(text.split())
        metadata.content_hash = hashlib.md5(text.encode()).hexdigest()

        if hasattr(chunk, "source_url") and chunk.source_url:
            metadata.url = chunk.source_url
            metadata.source_id = self._detect_source_type(chunk.source_url)
            metadata.domain = self._extract_domain(chunk.source_url)
            metadata.source_reliability_score = self._calculate_source_reliability(
                metadata.domain
            )

        metadata.data_type = self._detect_data_type(text)
        metadata.topic_tags = self._detect_topics(text)
        metadata.language = self._detect_language(text)
        metadata.entity_refs = self._extract_entities(text)

        metadata.has_citations = self._has_citations(text)
        metadata.has_examples = self._has_examples(text)
        metadata.chunk_quality_score = self._calculate_chunk_quality(metadata)
        metadata.freshness_score = self._calculate_freshness(metadata)
        metadata.risk_flags = self._detect_risk_flags(text, metadata)

        return metadata

    def _extract_domain(self, url: str) -> str:
        match = re.search(r"https?://(?:www\.)?([^/]+)", url)
        return match.group(1) if match else ""

    def _detect_source_type(self, url: str) -> str:
        if "github.com" in url:
            return "gh"
        if "huggingface.co" in url:
            return "hf"
        if "arxiv.org" in url:
            return "arxiv"
        if "stackoverflow.com" in url:
            return "stackoverflow"
        return "web"

    def _calculate_source_reliability(self, domain: str) -> float:
        if not domain:
            return 0.5
        domain_lower = domain.lower()
        for reliable in RELIABLE_DOMAINS:
            if reliable in domain_lower:
                return 0.95
        for less_reliable in LESS_RELIABLE_DOMAINS:
            if less_reliable in domain_lower:
                return 0.2
        if domain_lower.endswith((".org", ".gov", ".edu")):
            return 0.8
        if domain_lower.endswith(".com"):
            return 0.6
        return 0.5

    def _detect_data_type(self, text: str) -> DataType:
        scores = {}
        for dtype, patterns in self.DATA_TYPE_PATTERNS.items():
            score = sum(
                1 for p in patterns if re.search(p, text, re.IGNORECASE | re.MULTILINE)
            )
            if score > 0:
                scores[dtype] = score
        return max(scores, key=scores.get) if scores else DataType.DOC

    def _detect_topics(self, text: str) -> List[str]:
        text_lower = text.lower()
        topics = []
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            if matches >= 2:
                topics.append(topic)
        return topics

    def _detect_language(self, text: str) -> str:
        patterns = {
            "python": [r"def ", r"import ", r"class .*:"],
            "javascript": [r"const ", r"let ", r"function ", r"=>"],
            "typescript": [r": string", r": number", r"interface "],
            "go": [r"func ", r"package ", r"import \("],
            "rust": [r"fn ", r"let mut", r"impl "],
            "java": [r"public class", r"private ", r"void "],
            "sql": [r"SELECT ", r"FROM ", r"WHERE "],
        }
        for lang, patterns_list in patterns.items():
            if any(re.search(p, text) for p in patterns_list):
                return lang
        return ""

    def _extract_entities(self, text: str) -> List[str]:
        entities = []
        urls = re.findall(r"https?://[^\s]+", text)
        entities.extend([u[:50] for u in urls][:3])
        funcs = re.findall(r"\b([a-z_]+)\s*\(", text)
        entities.extend([f for f in funcs if len(f) > 2][:5])
        return list(set(entities))[:10]

    def _has_citations(self, text: str) -> bool:
        return bool(
            re.search(r"\[\d+\]|\(\w+,\s*\d{4}\)|according to", text, re.IGNORECASE)
        )

    def _has_examples(self, text: str) -> bool:
        return bool(
            re.search(
                r"for example|for instance|e\.g\.|example:|```", text, re.IGNORECASE
            )
        )

    def _calculate_chunk_quality(self, metadata: ChunkMetadata) -> float:
        score = 0.5
        if 100 < metadata.word_count < 1000:
            score += 0.15
        elif metadata.word_count < 50:
            score -= 0.1
        if metadata.has_citations:
            score += 0.15
        if metadata.has_examples:
            score += 0.1
        if metadata.data_type in [DataType.API_REF, DataType.CODE]:
            score += 0.1
        return max(0.0, min(1.0, score))

    def _calculate_freshness(self, metadata: ChunkMetadata) -> float:
        if not metadata.source_ts:
            return 0.5
        try:
            source_date = datetime.fromisoformat(
                metadata.source_ts.replace("Z", "+00:00")
            )
            age_days = (datetime.now(timezone.utc) - source_date).days
            ttl = self.FRESHNESS_TTL.get(metadata.data_type, 180)
            if age_days <= ttl:
                return 1.0 - (age_days / ttl) * 0.5
            return max(0.0, 0.5 - (age_days - ttl) / 365)
        except:
            return 0.5

    def _detect_risk_flags(self, text: str, metadata: ChunkMetadata) -> List[str]:
        flags = []
        if metadata.source_reliability_score < 0.4:
            flags.append("low_trust")
        if metadata.freshness_score < 0.3:
            flags.append("outdated")
        if metadata.data_type == DataType.DISCUSSION:
            flags.append("opinionated")
        if "paywall" in text.lower() or "subscription" in text.lower():
            flags.append("paywalled")
        if metadata.data_type == DataType.CODE:
            unsafe_patterns = [r"exec\(", r"eval\(", r"system\(", r"shell_exec"]
            if any(re.search(p, text) for p in unsafe_patterns):
                flags.append("unsafe_code")
        return flags

    def calculate_utility_probability(
        self,
        relevance_score: float,
        metadata: ChunkMetadata,
    ) -> float:
        """Calculate utility using sigmoid formula."""
        w_relevance = 1.2
        w_source_reliability = 0.9
        w_chunk_quality = 0.6
        w_freshness = 0.5
        w_verification = 0.4
        w_risk = 0.8

        verification_bonus = 0.0
        if metadata.verification_status == VerificationStatus.CROSS_VERIFIED:
            verification_bonus = 0.3
        elif metadata.verification_status == VerificationStatus.PARTIALLY_VERIFIED:
            verification_bonus = 0.15

        risk_penalty = len(metadata.risk_flags) * 0.15

        z = (
            w_relevance * relevance_score
            + w_source_reliability * metadata.source_reliability_score
            + w_chunk_quality * metadata.chunk_quality_score
            + w_freshness * metadata.freshness_score
            + w_verification * verification_bonus
            - w_risk * risk_penalty
        )

        return 1 / (1 + math.exp(-z))

    def classify_batch(self, chunks: List) -> List[ClassifiedChunk]:
        results = []
        for chunk in chunks:
            metadata = self.classify(chunk)
            classified = ClassifiedChunk(
                id=metadata.chunk_id,
                text=chunk.text if hasattr(chunk, "text") else str(chunk),
                metadata=metadata,
            )
            results.append(classified)
        return results


def classify_chunk(chunk) -> ChunkMetadata:
    """Convenience function."""
    classifier = ChunkClassifier()
    return classifier.classify(chunk)


@dataclass
class CodeChunkCandidate:
    """A code chunk candidate for reuse."""

    chunk_id: str
    text: str
    language: str
    license: Optional[str] = None
    reliability: float = 0.5
    freshness: float = 0.5
    verification: str = "unverified"
    risk_flags: List[str] = field(default_factory=list)
    utility_score: float = 0.0
    source: str = ""
    url: str = ""
    quality: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "language": self.language,
            "license": self.license,
            "reliability": self.reliability,
            "freshness": self.freshness,
            "verification": self.verification,
            "risk_flags": self.risk_flags,
            "utility_score": self.utility_score,
            "source": self.source,
            "url": self.url,
            "quality": self.quality,
        }


async def retrieve_code_chunks(
    query: str,
    language: str = "",
    intent: str = "write_code",
    k: int = 10,
) -> List[CodeChunkCandidate]:
    """
    Retrieve code chunks for reuse in CodeCraft.

    Contract:
        Input:
            query: str - The code request description
            language: str - Programming language (python, javascript, etc.)
            intent: str - Intent (write_code, fix_bug, implement_feature, etc.)
            k: int - Max candidates to return

        Output:
            List[CodeChunkCandidate] with:
                - chunk_id: unique identifier
                - text: code content
                - language: programming language
                - license: license name (MIT, Apache, etc.)
                - reliability: 0-1 source reliability score
                - freshness: 0-1 freshness score
                - verification: unverified/partially_verified/cross_verified
                - risk_flags: [low_trust, outdated, unsafe_code, etc.]
                - utility_score: 0-1 computed utility
                - source: source identifier (gh, hf, web)
                - url: source URL
                - quality: 0-1 quality score
    """
    from denis_unified_v1.actions.vector_store import VectorStoreManager

    # For now, use mock data - in production this would query Neo4j + Vector store
    mock_chunks = [
        {
            "chunk_id": "chunk-gh-001",
            "text": "def process_data(data):\n    return [x*2 for x in data]",
            "language": "python",
            "license": "MIT",
            "reliability": 0.95,
            "freshness": 0.8,
            "verification": "cross_verified",
            "risk_flags": [],
            "source": "github.com",
            "url": "https://github.com/example/utils/blob/main/process.py",
        },
        {
            "chunk_id": "chunk-gh-002",
            "text": "async function fetchData(url) {\n    const response = await fetch(url);\n    return response.json();\n}",
            "language": "javascript",
            "license": "Apache-2.0",
            "reliability": 0.9,
            "freshness": 0.7,
            "verification": "partially_verified",
            "risk_flags": [],
            "source": "github.com",
            "url": "https://github.com/example/fetch/blob/main/api.js",
        },
        {
            "chunk_id": "chunk-so-001",
            "text": "def calculate(x, y):\n    return x + y",
            "language": "python",
            "license": None,
            "reliability": 0.4,
            "freshness": 0.2,
            "verification": "unverified",
            "risk_flags": ["outdated"],
            "source": "stackoverflow.com",
            "url": "https://stackoverflow.com/questions/12345",
        },
        {
            "chunk_id": "chunk-gh-003",
            "text": "class AuthHandler:\n    def __init__(self, secret):\n        self.secret = secret\n    \ndef authenticate(self, token):\n        return token == self.secret",
            "language": "python",
            "license": "MIT",
            "reliability": 0.92,
            "freshness": 0.85,
            "verification": "cross_verified",
            "risk_flags": [],
            "source": "github.com",
            "url": "https://github.com/example/auth/blob/main/handler.py",
        },
        {
            "chunk_id": "chunk-gh-004",
            "text": "import os\nos.system('rm -rf /')  # DANGEROUS",
            "language": "python",
            "license": "GPL-3.0",
            "reliability": 0.1,
            "freshness": 0.9,
            "verification": "unverified",
            "risk_flags": ["unsafe_code"],
            "source": "github.com",
            "url": "https://github.com/bad actor/dangerous/blob/main/script.py",
        },
    ]

    # Filter by language if specified
    candidates = []
    for mock in mock_chunks:
        if language and mock["language"] != language:
            continue
        candidates.append(mock)

    # If no language filter, use all
    if not language:
        candidates = mock_chunks

    # Calculate utility scores
    classifier = ChunkClassifier()
    results = []

    for mock in candidates:
        # Create a mock chunk object for classification
        class MockChunk:
            def __init__(self, text, url):
                self.text = text
                self.source_url = url
                self.id = ""

        chunk = MockChunk(mock["text"], mock["url"])
        metadata = classifier.classify(chunk)

        # Calculate utility
        relevance = 0.8  # Default relevance for now
        utility = classifier.calculate_utility_probability(relevance, metadata)

        results.append(
            CodeChunkCandidate(
                chunk_id=mock["chunk_id"],
                text=mock["text"],
                language=mock["language"],
                license=mock.get("license"),
                reliability=mock["reliability"],
                freshness=mock["freshness"],
                verification=mock["verification"],
                risk_flags=mock["risk_flags"],
                utility_score=utility,
                source=mock["source"],
                url=mock["url"],
                quality=metadata.chunk_quality_score,
            )
        )

    # Sort by utility score descending
    results.sort(key=lambda x: x.utility_score, reverse=True)

    return results[:k]
