from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.soul.personality.signals import ConversationSignals
from backend.soul.user_model import MoodObservation, UserMoodTracker


def _signals(
    *,
    sentiment: float = 0.0,
    self_disclosure: bool = False,
    word_count: int = 4,
    laughter: bool = False,
    arousal_hint: float = 0.0,
) -> ConversationSignals:
    return ConversationSignals(
        sentiment=sentiment,
        self_disclosure=self_disclosure,
        question=False,
        novelty=0.5,
        arousal_hint=arousal_hint,
        laughter=laughter,
        word_count=word_count,
        length_score=min(1.0, word_count / 20.0),
    )


def test_user_mood_tracker_observe_and_persist(tmp_path):
    path = tmp_path / "user_mood.jsonl"
    tracker = UserMoodTracker.load(path)

    tracker.observe(_signals(sentiment=0.4, self_disclosure=True, laughter=True))
    tracker.save()

    reloaded = UserMoodTracker.load(path)
    recent = reloaded.recent()
    assert len(recent) == 1
    assert recent[0].sentiment == 0.4
    assert recent[0].self_disclosure is True
    assert recent[0].laughter is True


def test_user_mood_tracker_discards_old_entries(tmp_path):
    path = tmp_path / "user_mood.jsonl"
    old = MoodObservation(
        ts=datetime.now(tz=timezone.utc) - timedelta(days=45),
        sentiment=-0.6,
        self_disclosure=False,
        word_count=3,
        laughter=False,
        arousal_hint=0.1,
    )
    path.write_text(json.dumps(old.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8")

    tracker = UserMoodTracker.load(path)

    assert tracker.recent(days=60) == []


def test_user_mood_tracker_trend_improving():
    now = datetime.now(tz=timezone.utc)
    observations = [
        MoodObservation(now - timedelta(days=6), -0.4, False, 3, False, 0.0),
        MoodObservation(now - timedelta(days=5), -0.2, False, 4, False, 0.0),
        MoodObservation(now - timedelta(days=2), 0.2, True, 6, False, 0.0),
        MoodObservation(now - timedelta(days=1), 0.5, True, 7, True, 0.0),
    ]
    tracker = UserMoodTracker(observations)

    assert tracker.trend() == "improving"
    summary = tracker.weekly_summary()
    assert "idzie ku lepszemu" in summary
    assert "Otwiera się" in summary
