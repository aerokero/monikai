"""User Mood Tracker — observes and summarises the user's emotional patterns.

Monika has her own feelings, but she also pays attention to the user's.
This module tracks per-turn mood signals (sentiment, self-disclosure, laughter)
and provides pattern analysis over recent days.

Storage: JSONL append-only file at data/soul/user_mood.jsonl
         Entries older than 30 days are discarded on load.

Usage:
    tracker = UserMoodTracker.load()
    tracker.observe(signals)
    tracker.save()
    print(tracker.weekly_summary())
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from backend.soul.personality.signals import ConversationSignals

logger = logging.getLogger(__name__)

_MOOD_PATH = Path(__file__).parent.parent.parent / "data" / "soul" / "user_mood.jsonl"
_RETENTION_DAYS = 30
_TREND_DAYS = 7


class MoodObservation:
    __slots__ = ("ts", "sentiment", "self_disclosure", "word_count", "laughter", "arousal_hint")

    def __init__(
        self,
        ts: datetime,
        sentiment: float,
        self_disclosure: bool,
        word_count: int,
        laughter: bool,
        arousal_hint: float,
    ) -> None:
        self.ts = ts
        self.sentiment = sentiment
        self.self_disclosure = self_disclosure
        self.word_count = word_count
        self.laughter = laughter
        self.arousal_hint = arousal_hint

    def to_dict(self) -> dict:
        return {
            "ts": self.ts.isoformat(timespec="seconds"),
            "sentiment": round(self.sentiment, 3),
            "self_disclosure": self.self_disclosure,
            "word_count": self.word_count,
            "laughter": self.laughter,
            "arousal_hint": round(self.arousal_hint, 3),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MoodObservation":
        raw_ts = d.get("ts", "")
        try:
            ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except ValueError:
            ts = datetime.now(tz=timezone.utc)
        return cls(
            ts=ts,
            sentiment=float(d.get("sentiment", 0.0)),
            self_disclosure=bool(d.get("self_disclosure", False)),
            word_count=int(d.get("word_count", 0)),
            laughter=bool(d.get("laughter", False)),
            arousal_hint=float(d.get("arousal_hint", 0.0)),
        )


class UserMoodTracker:
    """Rolling window of mood observations with trend analysis."""

    def __init__(self, observations: list[MoodObservation], path: Path | None = None) -> None:
        self._obs = observations
        self._path = path or _MOOD_PATH
        self._dirty = False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> "UserMoodTracker":
        p = path or _MOOD_PATH
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_RETENTION_DAYS)
        observations: list[MoodObservation] = []

        if p.exists():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obs = MoodObservation.from_dict(json.loads(line))
                        if obs.ts >= cutoff:
                            observations.append(obs)
                    except (json.JSONDecodeError, KeyError):
                        pass
            except Exception as exc:
                logger.warning("UserMoodTracker: failed to load: %s", exc)

        return cls(observations=observations, path=p)

    def save(self, path: Path | None = None) -> None:
        if not self._dirty:
            return
        p = path or self._path
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with p.open("w", encoding="utf-8") as f:
                for obs in self._obs:
                    f.write(json.dumps(obs.to_dict(), ensure_ascii=False) + "\n")
            self._dirty = False
        except Exception as exc:
            logger.error("UserMoodTracker: failed to save: %s", exc)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def observe(self, signals: ConversationSignals) -> None:
        """Record one turn's worth of mood data."""
        obs = MoodObservation(
            ts=datetime.now(tz=timezone.utc),
            sentiment=signals.sentiment,
            self_disclosure=signals.self_disclosure,
            word_count=signals.word_count,
            laughter=signals.laughter,
            arousal_hint=signals.arousal_hint,
        )
        self._obs.append(obs)
        self._dirty = True

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def recent(self, days: int = _TREND_DAYS) -> list[MoodObservation]:
        """Return observations from the last N days."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        return [o for o in self._obs if o.ts >= cutoff]

    def trend(self, days: int = _TREND_DAYS) -> Literal["improving", "stable", "declining", "unknown"]:
        """Compare first-half vs second-half average sentiment over N days."""
        obs = self.recent(days)
        if len(obs) < 4:
            return "unknown"

        mid = len(obs) // 2
        first_avg = sum(o.sentiment for o in obs[:mid]) / mid
        second_avg = sum(o.sentiment for o in obs[mid:]) / (len(obs) - mid)
        delta = second_avg - first_avg

        if delta > 0.1:   return "improving"
        if delta < -0.1:  return "declining"
        return "stable"

    def avg_sentiment(self, days: int = _TREND_DAYS) -> float | None:
        obs = self.recent(days)
        if not obs:
            return None
        return sum(o.sentiment for o in obs) / len(obs)

    def disclosure_rate(self, days: int = _TREND_DAYS) -> float:
        """Fraction of turns with self-disclosure in last N days."""
        obs = self.recent(days)
        if not obs:
            return 0.0
        return sum(1 for o in obs if o.self_disclosure) / len(obs)

    def weekly_summary(self) -> str:
        """Return a prose summary of the user's recent mood for the assembled prompt."""
        trend = self.trend()
        avg = self.avg_sentiment()
        disc = self.disclosure_rate()
        obs = self.recent()

        if not obs:
            return ""

        parts = []

        if avg is not None:
            if avg > 0.25:
                parts.append("Ostatnio przeważnie w dobrym nastroju")
            elif avg < -0.15:
                parts.append("Ostatnio jest mu trochę ciężej niż zwykle")
            else:
                parts.append("Nastrój ostatnio wyrównany, bez wyraźnego kierunku")

        if trend == "improving":
            parts.append("i wygląda na to, że idzie ku lepszemu")
        elif trend == "declining":
            parts.append("choć w ostatnich dniach widać pewne pogorszenie")

        if disc > 0.3:
            parts.append("Otwiera się — dzieli się więcej osobistymi rzeczami")

        if any(o.laughter for o in obs):
            parts.append("Zdarzają się też momenty prawdziwej lekkości")

        return ". ".join(parts) + "." if parts else ""
