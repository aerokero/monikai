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
# A period after a short word that is followed by a lowercase letter or digit
# is an abbreviation dot, not a sentence end ("ok. 5", "np. kawa"): sentences
# start with a capital.  Dropping it keeps the engine from stopping there.
_ABBREVIATION_DOT_RE = re.compile(r"\b(\w{1,5})\.(?=[ \t]+[^\W_A-Z]|[ \t]+\d)")


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
    value = _ABBREVIATION_DOT_RE.sub(r"\1", value)
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


# A sentence ends at terminal punctuation followed by whitespace, unless the
# next word starts lowercase or with a digit (abbreviation dot, see above).
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?…]+[\"'”»)\]]*\s+(?=\S)|\n+")
_CLAUSE_BOUNDARY_RE = re.compile(r"[,;:]\s+(?=\S)")


class SpeechChunker:
    """Cut a streamed reply into speakable pieces as soon as each is complete.

    The first piece may end at a clause boundary so speech starts early; later
    pieces are whole sentences, which keeps the synthesizer's prosody natural.
    Speech stops at ``max_chars``; the full reply still lands in the chat.
    """

    def __init__(
        self,
        max_chars: int = 0,
        first_clause_min: int = 20,
        first_clause_wait: int = 60,
        long_piece: int = 200,
    ):
        self.max_chars = max_chars
        self.first_clause_min = first_clause_min
        # A clause cut costs prosody (it is read like a finished sentence),
        # so only do it when the first sentence is long enough to delay speech.
        self.first_clause_wait = first_clause_wait
        # A sentence this long would render for seconds while nothing plays;
        # cut it at its last clause boundary instead.
        self.long_piece = long_piece
        self.text = ""  # everything fed so far
        self._buffer = ""
        self._spoken_chars = 0

    def _take(self, end: int) -> list[str]:
        piece, self._buffer = self._buffer[:end].strip(), self._buffer[end:]
        if not piece or (self.max_chars and self._spoken_chars >= self.max_chars):
            return []
        self._spoken_chars += len(piece)
        return [piece]

    def feed(self, delta: str) -> list[str]:
        self.text += delta
        self._buffer += delta
        pieces: list[str] = []
        while True:
            end = None
            for match in _SENTENCE_BOUNDARY_RE.finditer(self._buffer):
                following = self._buffer[match.end()]
                if match.group().startswith("\n") or not (following.islower() or following.isdigit()):
                    end = match.end()
                    break
            if end is None and not self._spoken_chars and len(self._buffer) >= self.first_clause_wait:
                for match in _CLAUSE_BOUNDARY_RE.finditer(self._buffer):
                    if match.start() >= self.first_clause_min:
                        end = match.end()
                        break
            if (end or len(self._buffer)) > self.long_piece:
                clauses = [m.end() for m in _CLAUSE_BOUNDARY_RE.finditer(self._buffer, 0, self.long_piece)]
                end = clauses[-1] if clauses else end
            if end is None:
                return pieces
            pieces += self._take(end)

    def flush(self) -> list[str]:
        return self._take(len(self._buffer))
