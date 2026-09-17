"""Small, transport-agnostic guards for speech-to-text turns.

Speech recognition providers occasionally return a plausible-looking guess for
noise or an incomplete utterance.  Voice input is the one place where sending
that guess to the conversation model can create an unsolicited answer or a
tool/search call, so the boundary is deliberately conservative.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any


DEFAULT_MIN_VOICE_CONFIDENCE = 0.60

_WORD_RE = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
_UNINTELLIGIBLE_MARKER_RE = re.compile(
    r"^(?:"
    r"\[(?:unintelligible|inaudible|unclear|no speech|no audio|"
    r"niezrozumiałe|niezrozumiale|niesłyszalne|nieslyszalne|brak mowy)\]"
    r"|(?:unintelligible|inaudible|unclear|no speech|no audio|"
    r"niezrozumiałe|niezrozumiale|niesłyszalne|nieslyszalne|brak mowy)"
    r")[\s.!?]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VoiceTranscriptAssessment:
    """Decision and diagnostic reason for one final speech transcript."""

    accepted: bool
    text: str
    confidence: float | None = None
    reason: str = "accepted"


def normalize_voice_transcript(text: Any) -> str:
    """Collapse provider whitespace without rewriting what was spoken."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_voice_confidence(value: Any) -> float | None:
    """Return a finite 0..1 confidence, accepting percentage-shaped values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(confidence):
        return None
    if confidence > 1.0 and confidence <= 100.0:
        confidence /= 100.0
    if confidence < 0.0 or confidence > 1.0:
        return None
    return confidence


def assess_voice_transcript(
    text: Any,
    *,
    confidence: Any = None,
    intelligible: Any = None,
    min_confidence: float = DEFAULT_MIN_VOICE_CONFIDENCE,
) -> VoiceTranscriptAssessment:
    """Assess a final ASR result without guessing its intended meaning.

    Missing confidence is not treated as failure because several providers
    expose only text.  Those providers still get the explicit-marker guard and
    the voice prompt's no-inference rule at the response-author boundary.
    """
    normalized = normalize_voice_transcript(text)
    normalized_confidence = normalize_voice_confidence(confidence)

    if not normalized:
        return VoiceTranscriptAssessment(False, "", normalized_confidence, "empty")

    if intelligible is False:
        return VoiceTranscriptAssessment(
            False, normalized, normalized_confidence, "provider_marked_unintelligible"
        )

    if _UNINTELLIGIBLE_MARKER_RE.match(normalized):
        return VoiceTranscriptAssessment(
            False, normalized, normalized_confidence, "unintelligible_marker"
        )

    if normalized_confidence is not None and normalized_confidence < max(
        0.0, min(1.0, float(min_confidence))
    ):
        return VoiceTranscriptAssessment(
            False, normalized, normalized_confidence, "low_confidence"
        )

    if not _WORD_RE.search(normalized):
        return VoiceTranscriptAssessment(
            False, normalized, normalized_confidence, "no_words"
        )

    return VoiceTranscriptAssessment(True, normalized, normalized_confidence)


def voice_transcript_is_usable(
    text: Any,
    *,
    confidence: Any = None,
    intelligible: Any = None,
    min_confidence: float = DEFAULT_MIN_VOICE_CONFIDENCE,
) -> bool:
    """Convenience predicate used immediately before a voice turn is sent."""
    return assess_voice_transcript(
        text,
        confidence=confidence,
        intelligible=intelligible,
        min_confidence=min_confidence,
    ).accepted

