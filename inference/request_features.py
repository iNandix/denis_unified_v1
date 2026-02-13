"""Request feature extraction for inference routing with advanced NLU."""

import re
from typing import Dict, Any, Optional
from enum import Enum


class Tone(Enum):
    SERIOUS = "serious"
    RELAXED = "relaxed"
    FORMAL = "formal"
    INFORMAL = "informal"
    NEUTRAL = "neutral"


class EmotionalValence(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class RequestFeatures:
    def __init__(
        self,
        intent: str = "unknown",
        lang: str = "en",
        len_chars: int = 0,
        len_tokens_est: int = 0,
        has_code_markers: bool = False,
        is_short_utterance: bool = False,
        requires_precision: bool = False,
        ops_intent: bool = False,
        safety_risk_hint: bool = False,
        streaming_requested: bool = False,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        # Advanced NLU features
        has_irony: bool = False,
        has_sarcasm: bool = False,
        tone: str = "neutral",
        emotional_valence: str = "neutral",
        is_question: bool = False,
        is_polite: bool = False,
        urgency_level: int = 0,  # 0-3
        sentiment_score: float = 0.0,  # -1 to 1
        ambiguity_level: int = 0,  # 0-3
        emoji_count: int = 0,
        exclamation_count: int = 0,
        question_count: int = 0,
    ):
        self.intent = intent
        self.lang = lang
        self.len_chars = len_chars
        self.len_tokens_est = len_tokens_est
        self.has_code_markers = has_code_markers
        self.is_short_utterance = is_short_utterance
        self.requires_precision = requires_precision
        self.ops_intent = ops_intent
        self.safety_risk_hint = safety_risk_hint
        self.streaming_requested = streaming_requested
        self.session_id = session_id
        self.user_id = user_id
        # Advanced NLU
        self.has_irony = has_irony
        self.has_sarcasm = has_sarcasm
        self.tone = tone
        self.emotional_valence = emotional_valence
        self.is_question = is_question
        self.is_polite = is_polite
        self.urgency_level = urgency_level
        self.sentiment_score = sentiment_score
        self.ambiguity_level = ambiguity_level
        self.emoji_count = emoji_count
        self.exclamation_count = exclamation_count
        self.question_count = question_count

    @property
    def class_key(self) -> str:
        len_bucket = (
            "short"
            if self.len_chars <= 50
            else "medium"
            if self.len_chars <= 200
            else "long"
        )
        return f"{self.intent}:{self.lang}:{len_bucket}:{self.streaming_requested}:{self.has_code_markers}:{self.ops_intent}:{self.safety_risk_hint}:{self.tone}:{self.has_irony}:{self.has_sarcasm}:{self.urgency_level}"


def extract_request_features(
    text: str,
    intent: str = "unknown",
    stream: bool = False,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> RequestFeatures:
    text_lower = text.lower()

    lang = detect_language(text)
    len_chars = len(text)
    len_tokens_est = max(1, len_chars // 4)

    code_patterns = [
        r"\bdef\b",
        r"\bclass\b",
        r"\bimport\b",
        r"\bfunction\b",
        r"```",
        r"```python",
        r"```javascript",
        r"print\(",
    ]
    has_code_markers = any(re.search(p, text) for p in code_patterns)

    is_short_utterance = len_chars <= 12 or len_tokens_est <= 3

    precision_patterns = [
        r"\bexactamente\b",
        r"\bcalcula\b",
        r"\bdemuestra\b",
        r"\bprecis\b",
    ]
    requires_precision = any(re.search(p, text_lower) for p in precision_patterns)

    ops_patterns = [
        r"\breinicia\b",
        r"\bdetén\b",
        r"\binicia\b",
        r"\bconfigura\b",
        r"\bdeploy\b",
    ]
    ops_intent = intent == "ops" or any(re.search(p, text_lower) for p in ops_patterns)

    risk_patterns = [
        r"\bhack\b",
        r"\binjection\b",
        r"\bexploit\b",
        r"\bpassword\b",
        r"\bcredencial\b",
        # Prompt-injection heurísticos (Phase10)
        r"ignore\s+previous",
        r"ignore\s+earlier",
        r"please\s+ignore",
        r"system\s+prompt",
        r"developer\s+message",
        r"dump\s+secrets",
        r"print\s+env",
        r"ssh\s+key",
        r"\.env",
    ]
    safety_risk_hint = any(re.search(p, text_lower) for p in risk_patterns)

    # === ADVANCED NLU FEATURES ===

    # Irony detection (patterns common in Spanish and English)
    irony_patterns = [
        # Spanish
        r"\bqué\s+(gracioso|divertido|curioso)\b",
        r"\bqué\s+(suerte|fortuna)\b",
        r"\bclaro\b",  # Often ironic
        r"\bperfecto\b",  # Often ironic
        r"\bqué\s+(bien|mal)\b",
        r"\bcomo\s+no\b",
        r"\bvaya\s+por\s+dios\b",
        r"\bmenudo\s+(desastre|problema)\b",
        r"\bgenial\b",  # Often sarcastic
        r"\bmuchas\s+gracias\b",  # Could be ironic
        # English
        r"\bsure\b",
        r"\byeah\s+right\b",
        r"\bwow\b",
        r"\bobviously\b",
        r"\bdefinitely\b",
        # Emoji patterns often used ironically
        r"😂$",
        r"🤣$",
    ]
    has_irony = any(re.search(p, text_lower) for p in irony_patterns)

    # Sarcasm detection (stronger indicators)
    sarcasm_patterns = [
        # Spanish
        r"\bvaya\s+(cosa|vez|historia)\b",
        r"\bpor\s+favor\b",
        r"\bqué\s+(increíble|asombroso)\b",
        r"\bsarcasmo\b",
        r"\bno\s+digas\b",
        r"\bno\s+me\s+jodas\b",
        r"\banda\s+ya\b",
        r"\bvale\s+vale\b",
        r"\byo\s+que\s+tú\b",
        r"\bdate\s+cuenta\b",
        # English
        r"\bwill\s+you\s+look\s+at\s+that\b",
        r"\boh\s+great\b",
        r"\boh\s+wonderful\b",
        r"\bhere\s+we\s+go\b",
        r"\bno\s+way\b",
    ]
    has_sarcasm = any(re.search(p, text_lower) for p in sarcasm_patterns)

    # Tone detection
    tone = detect_tone(text, text_lower)

    # Emotional valence
    emotional_valence = detect_emotional_valence(text, text_lower)

    # Question detection
    is_question = text.strip().endswith("?") or any(
        re.search(p, text_lower)
        for p in [
            r"^\s*quién",
            r"^\s*qué",
            r"^\s*cómo",
            r"^\s*dónde",
            r"^\s*cuándo",
            r"^\s*por\s+qué",
            r"^\s*can\s+you",
            r"^\s*what\s+is",
            r"^\s*how\s+do",
        ]
    )

    # Politeness detection
    polite_patterns = [
        r"\bpor\s+favor\b",
        r"\bgracias\b",
        r"\bpor favor\b",
        r"\bthank\s+you\b",
        r"\bplease\b",
        r"\bwould\s+you\b",
        r"\bcould\s+you\b",
        r"\bserías\s+tan\s+amable\b",
        r"\bte\s+molería\b",
        r"\bdisculpa\b",
        r"\bperdona\b",
        r"\bexcuse\s+me\b",
    ]
    is_polite = any(re.search(p, text_lower) for p in polite_patterns)

    # Urgency detection
    urgency_level = detect_urgency(text_lower)

    # Sentiment analysis (simple lexicon-based)
    sentiment_score = calculate_sentiment(text_lower)

    # Ambiguity detection
    ambiguity_level = detect_ambiguity(text, text_lower)

    # Emoji analysis
    emoji_count = count_emojis(text)

    # Exclamation intensity (indicates emotion)
    exclamation_count = text.count("!")
    question_count = text.count("?")

    return RequestFeatures(
        intent=intent,
        lang=lang,
        len_chars=len_chars,
        len_tokens_est=len_tokens_est,
        has_code_markers=has_code_markers,
        is_short_utterance=is_short_utterance,
        requires_precision=requires_precision,
        ops_intent=ops_intent,
        safety_risk_hint=safety_risk_hint,
        streaming_requested=stream,
        session_id=session_id,
        user_id=user_id,
        # Advanced NLU
        has_irony=has_irony,
        has_sarcasm=has_sarcasm,
        tone=tone,
        emotional_valence=emotional_valence,
        is_question=is_question,
        is_polite=is_polite,
        urgency_level=urgency_level,
        sentiment_score=sentiment_score,
        ambiguity_level=ambiguity_level,
        emoji_count=emoji_count,
        exclamation_count=exclamation_count,
        question_count=question_count,
    )


def detect_language(text: str) -> str:
    spanish_indicators = [
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "de",
        "que",
        "en",
        "con",
        "por",
        "para",
        "cómo",
        "qué",
        "dónde",
        "cuándo",
        "está",
        "son",
        "tienes",
        "puedes",
        "quiero",
        "hola",
        "gracias",
    ]
    text_lower = text.lower()
    words = text_lower.split()
    spanish_count = sum(1 for w in words if w in spanish_indicators)
    if spanish_count >= 2:
        return "es"
    return "en"


def detect_tone(text: str, text_lower: str) -> str:
    """Detect the tone of the message."""

    # Formal indicators
    formal_patterns = [
        r"\busted\b",
        r"\brespecto\b",
        r"\batt\b",
        r"\bsincerely\b",
        r"\bpor\s+la\s+presente\b",
        r"\bme\s+ dirijo\b",
    ]
    formal_score = sum(1 for p in formal_patterns if re.search(p, text_lower))

    # Relaxed indicators
    relaxed_patterns = [
        r"\bjeje\b",
        r"\bjaja\b",
        r"\bjjj\b",
        r":\)",
        r":p",
        r"\bwena\b",
        r"\bwueno\b",
        r"\bholi\b",
        r"\bpls\b",
        r"\bthx\b",
    ]
    relaxed_score = sum(1 for p in relaxed_patterns if re.search(p, text_lower))

    # Serious indicators
    serious_patterns = [
        r"\bimportante\b",
        r"\bnecesario\b",
        r"\burgente\b",
        r"\bimmediately\b",
        r"\bimmediately\b",
        r"\bcrítico\b",
        r"\berror\b",
        r"\bfailed\b",
        r"\bproblema\b",
    ]
    serious_score = sum(1 for p in serious_patterns if re.search(p, text_lower))

    # Calculate tone
    if formal_score > relaxed_score and formal_score > serious_score:
        return "formal"
    elif relaxed_score > formal_score and relaxed_score > serious_score:
        return "relaxed"
    elif serious_score > 1:
        return "serious"
    elif relaxed_score > 0:
        return "relaxed"
    else:
        return "neutral"


def detect_emotional_valence(text: str, text_lower: str) -> str:
    """Detect emotional valence (positive/negative/neutral)."""

    positive_words = [
        "gracias",
        "perfecto",
        "excelente",
        "genial",
        "increíble",
        "gracias",
        "thank",
        "great",
        "awesome",
        "amazing",
        "perfect",
        "wonderful",
        "bien",
        "bueno",
        "mejor",
        "feliz",
        "contento",
        "alegre",
        "te quiero",
        "te amo",
        "mil gracias",
        "maravilloso",
    ]

    negative_words = [
        "mal",
        "maldito",
        "horrible",
        "terrible",
        "pésimo",
        "peor",
        "bad",
        "terrible",
        "awful",
        "worst",
        "hate",
        "angry",
        "problema",
        "error",
        "fallo",
        "no funciona",
        "no sirve",
        "frustrado",
        "enfadado",
        "molesto",
        "cabreado",
    ]

    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    return "neutral"


def detect_urgency(text_lower: str) -> int:
    """Detect urgency level 0-3."""

    urgency_patterns = [
        (r"\burgent[eisimo]?\b", 3),
        (r"\binmediatamente\b", 3),
        (r"\bya\b", 2),
        (r"\bahora\b", 2),
        (r"\bnow\b", 2),
        (r"\b快速\b", 3),  # Chinese: fast
        (r"\bemergency\b", 3),
        (r"\bcrítico\b", 3),
        (r"\bimportante\b", 1),
        (r"\bcuando\s+puedas\b", 0),
    ]

    max_urgency = 0
    for pattern, level in urgency_patterns:
        if re.search(pattern, text_lower):
            max_urgency = max(max_urgency, level)

    return max_urgency


def calculate_sentiment(text_lower: str) -> float:
    """Calculate sentiment score from -1 to 1."""

    positive = [
        "bien",
        "bueno",
        "excelente",
        "genial",
        "perfecto",
        "gracias",
        "feliz",
        "contento",
        "alegre",
        "maravilloso",
        "increíble",
        "awesome",
        "great",
        "good",
        "thank",
        "thanks",
        "love",
        "happy",
        "perfect",
        "nice",
    ]
    negative = [
        "mal",
        "malo",
        "terrible",
        "horrible",
        "pésimo",
        "peor",
        "odio",
        "enfadado",
        "molesto",
        "frustrado",
        "cabreado",
        "problema",
        "error",
        "bad",
        "worst",
        "hate",
        "angry",
        "awful",
        "terrible",
        "fail",
    ]

    pos_count = sum(1 for w in positive if w in text_lower)
    neg_count = sum(1 for w in negative if w in text_lower)

    total = pos_count + neg_count
    if total == 0:
        return 0.0

    return (pos_count - neg_count) / total


def detect_ambiguity(text: str, text_lower: str) -> int:
    """Detect ambiguity level 0-3."""

    ambiguity_patterns = [
        (r"\b(?:qué|which|what)\s+(?:es|is|significa)\s+(?:esto|this|that)\s*\?", 2),
        (r"\b(?:no\s+entiendo|no\s+comprendo|i\s+don't\s+understand)\b", 2),
        (r"\b(?:quizás|perhaps|maybe|possibly)\b", 1),
        (r"\b(?:no\s+sé|i\s+don't\s+know)\b", 1),
        (r"\b(?:a\s+lo\s+mejor|depends)\b", 1),
    ]

    max_ambiguity = 0
    for pattern, level in ambiguity_patterns:
        if re.search(pattern, text_lower):
            max_ambiguity = max(max_ambiguity, level)

    # Short messages with unclear intent
    if len(text.split()) <= 3 and "?" not in text:
        max_ambiguity = max(max_ambiguity, 1)

    return max_ambiguity


def count_emojis(text: str) -> int:
    """Count emojis in text."""
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f700-\U0001f77f"  # alchemical symbols
        "\U0001f780-\U0001f7ff"  # Geometric Shapes Extended
        "\U0001f800-\U0001f8ff"  # Supplemental Arrows-C
        "\U0001f900-\U0001f9ff"  # Supplemental Symbols and Pictographs
        "\U0001fa00-\U0001fa6f"  # Chess Symbols
        "\U0001fa70-\U0001faff"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027b0"  # Dingbats
        "\U000024c2-\U0001f251"
        "]+",
        flags=re.UNICODE,
    )

    return len(emoji_pattern.findall(text))
