"""Turn chat-style text into something a TTS engine can read naturally.

Voice replies sometimes arrive as markdown (bold, bullet lists, arrows,
nested parentheses).  Read literally, those produce long silences and odd
pauses, so the structure is flattened into plain sentences before synthesis.

This module is deliberately language-neutral: it never inserts words.  Spelling
out units and symbols is left to the reply author (the voice-channel prompt
asks for it in the user's language) and to the TTS engine itself.
"""

from __future__ import annotations

import re

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F2FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*(?:[-*•–—]|\d{1,2}[.)])\s+", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(\*{1,3}|_{2,3})(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
_SENTENCE_END = ".!?…:;"


def _end_lines_with_punctuation(text: str) -> str:
    """Make every former line/bullet its own sentence."""
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line[-1] not in _SENTENCE_END:
            line += "."
        lines.append(line)
    return " ".join(lines)


def prepare_for_speech(text: str) -> str:
    """Return plain, speakable text without adding any words."""
    value = str(text or "")
    if not value.strip():
        return ""

    value = _FENCED_CODE_RE.sub(" ", value)
    value = _INLINE_CODE_RE.sub(r"\1", value)
    value = _LINK_RE.sub(r"\1", value)
    value = _BARE_URL_RE.sub(" ", value)
    value = _HEADING_RE.sub("", value)
    value = _BULLET_RE.sub("", value)
    # Run twice so nested emphasis such as ***text*** is fully removed.
    for _ in range(2):
        value = _EMPHASIS_RE.sub(r"\2", value)
    value = value.replace("*", "").replace("`", "")
    value = _EMOJI_RE.sub(" ", value)

    # Arrows are language-neutral separators; read as a short pause.
    value = re.sub(r"[ \t]*(?:→|->|=>|⇒)[ \t]*", ", ", value)
    # Dashes used as pauses become commas; they otherwise produce long gaps.
    value = re.sub(r"[ \t]+[–—][ \t]+", ", ", value)
    value = re.sub(r"[|]", ", ", value)
    # Parentheses cause abrupt prosody changes; use commas instead.
    value = re.sub(r"[ \t]*[(\[][ \t]*", ", ", value)
    value = re.sub(r"[ \t]*[)\]][ \t]*", ", ", value)

    value = _end_lines_with_punctuation(value)
    # Tidy up punctuation produced by the replacements above.
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([,;:])\s*(?:[,;:])+", r"\1", value)
    value = re.sub(r",\s*([.!?])", r"\1", value)
    value = re.sub(r"([.!?])\s*[,;:]", r"\1", value)
    value = re.sub(r"(?<!\.)\.\.(?!\.)", ".", value)
    value = re.sub(r"\.{4,}", "...", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip(" ,;:")


def truncate_for_speech(text: str, max_chars: int) -> str:
    """Cut long text at a sentence (or word) boundary for spoken replies."""
    value = str(text or "").strip()
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    window = value[:max_chars]
    cut = max(window.rfind(mark) for mark in (". ", "! ", "? ", "… "))
    if cut >= int(max_chars * 0.4):
        return window[: cut + 1].strip()
    cut = window.rfind(" ")
    return (window[:cut] if cut > 0 else window).strip(" ,;:") + "."
