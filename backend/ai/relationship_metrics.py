"""Relationship Metrics System - 4-axis model"""
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field, asdict


@dataclass
class RelationshipMetrics:
    """4-axis relationship metrics: affection, comfort, synergy, intimacy"""
    affection: float = 0.0  # How deeply does Monika care?
    comfort: float = 0.0    # Safety/comfort with Monika
    synergy: float = 0.0    # Interest alignment
    intimacy: float = 0.0   # Personal closeness
    streak_days: int = 0    # Consecutive interaction days
    last_interaction: Optional[str] = None  # ISO timestamp
    total_xp_earned: Dict[str, float] = field(default_factory=lambda: {
        "affection": 0.0,
        "comfort": 0.0,
        "synergy": 0.0,
        "intimacy": 0.0
    })

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationshipMetrics":
        """Create from dictionary"""
        return cls(**data)


class RelationshipMetricsEngine:
    """Manages relationship metrics progression"""

    # XP thresholds for achievements
    ACHIEVEMENT_THRESHOLDS = {
        "affection": [25, 50, 75, 100, 150, 200, 300],
        "comfort": [25, 50, 75, 100, 150, 200],
        "synergy": [25, 50, 75, 100, 150],
        "intimacy": [25, 50, 75, 100, 150]
    }

    def __init__(self, metrics: Optional[RelationshipMetrics] = None):
        self.metrics = metrics or RelationshipMetrics()
        self.pending_notifications: List[Dict[str, Any]] = []

    def add_xp(self, metric_name: str, amount: float) -> Dict[str, Any]:
        """
        Add XP to a metric.
        Returns dict with:
            - 'old_value': previous metric value
            - 'new_value': new metric value
            - 'xp_added': amount added
            - 'level_up': True if threshold crossed
            - 'achievement_unlocked': achievement ID if applicable
        """
        if metric_name not in ["affection", "comfort", "synergy", "intimacy"]:
            return {"error": f"Unknown metric: {metric_name}"}

        old_value = getattr(self.metrics, metric_name)
        new_value = old_value + amount
        setattr(self.metrics, metric_name, new_value)

        # Track total XP
        self.metrics.total_xp_earned[metric_name] += amount

        # Update last interaction
        self.metrics.last_interaction = datetime.utcnow().isoformat()

        result = {
            "old_value": old_value,
            "new_value": new_value,
            "xp_added": amount,
            "level_up": False,
            "achievements_unlocked": []
        }

        # Check for achievement thresholds crossed
        thresholds = self.ACHIEVEMENT_THRESHOLDS.get(metric_name, [])
        for threshold in thresholds:
            if old_value < threshold <= new_value:
                achievement_id = f"{metric_name}_{threshold}"
                result["achievements_unlocked"].append(achievement_id)
                result["level_up"] = True

        return result

    def update_streak(self) -> int:
        """Update streak days (called on each interaction)"""
        if not self.metrics.last_interaction:
            self.metrics.streak_days = 1
            return 1

        last = datetime.fromisoformat(self.metrics.last_interaction)
        now = datetime.utcnow()
        days_since = (now.date() - last.date()).days

        if days_since == 0:
            # Same day, no streak update
            return self.metrics.streak_days
        elif days_since == 1:
            # Next day, increment streak
            self.metrics.streak_days += 1
        else:
            # Streak broken, reset
            self.metrics.streak_days = 1

        self.metrics.last_interaction = now.isoformat()
        return self.metrics.streak_days

    def get_metrics_state(self) -> Dict[str, Any]:
        """Get current metrics state"""
        return {
            "affection": self.metrics.affection,
            "comfort": self.metrics.comfort,
            "synergy": self.metrics.synergy,
            "intimacy": self.metrics.intimacy,
            "streak_days": self.metrics.streak_days,
            "total_xp_earned": self.metrics.total_xp_earned,
            "last_interaction": self.metrics.last_interaction
        }

    def check_metric_thresholds(self) -> List[Dict[str, Any]]:
        """
        Check if any metric has crossed achievement thresholds.
        Returns list of {metric, threshold, achievement_id}
        """
        unlocked = []
        for metric_name, thresholds in self.ACHIEVEMENT_THRESHOLDS.items():
            current_value = getattr(self.metrics, metric_name)
            for threshold in thresholds:
                if current_value >= threshold:
                    achievement_id = f"{metric_name}_{threshold}"
                    unlocked.append({
                        "metric": metric_name,
                        "threshold": threshold,
                        "achievement_id": achievement_id,
                        "current_value": current_value
                    })
        return unlocked

    def get_recommendation_progress(self) -> Dict[str, float]:
        """
        Get progress towards next achievement for each metric.
        Returns dict of metric -> {"current": value, "next_threshold": value, "progress_pct": 0-100}
        """
        progress = {}
        for metric_name, thresholds in self.ACHIEVEMENT_THRESHOLDS.items():
            current = getattr(self.metrics, metric_name)
            # Find next threshold
            next_threshold = None
            for threshold in sorted(thresholds):
                if current < threshold:
                    next_threshold = threshold
                    break

            if next_threshold:
                progress_pct = (current / next_threshold) * 100
            else:
                # Already passed all thresholds
                progress_pct = 100.0
                if thresholds:
                    next_threshold = max(thresholds) + 50

            progress[metric_name] = {
                "current": current,
                "next_threshold": next_threshold,
                "progress_pct": min(progress_pct, 100.0)
            }

        return progress

    def apply_message_bonuses(self, signals: Dict[str, Any]) -> Dict[str, float]:
        """
        Apply XP bonuses based on message analysis signals.
        Signals expected: {
            'sentiment': float (-1 to 1),
            'self_disclosure': float (0-1),
            'question_asked': bool,
            'text_length': int,
            'emotional_depth': float (0-1)
        }
        Returns dict of metrics modified with amounts
        """
        bonuses = {}

        # Sentiment contributes to affection
        if "sentiment" in signals:
            sentiment = signals["sentiment"]
            if sentiment > 0.5:
                xp = 2.0 + (sentiment * 2)  # 2-4 affection
                bonuses["affection"] = bonuses.get("affection", 0) + xp

        # Self-disclosure contributes to comfort & intimacy
        if "self_disclosure" in signals:
            disclosure = signals["self_disclosure"]
            if disclosure > 0.3:
                comfort_xp = disclosure * 5  # 0-5 comfort
                intimacy_xp = disclosure * 8  # 0-8 intimacy
                bonuses["comfort"] = bonuses.get("comfort", 0) + comfort_xp
                bonuses["intimacy"] = bonuses.get("intimacy", 0) + intimacy_xp

        # Questions contribute to synergy
        if signals.get("question_asked", False):
            bonuses["synergy"] = bonuses.get("synergy", 0) + 2.0

        # Longer messages show engagement -> comfort
        if "text_length" in signals:
            length = signals["text_length"]
            if length > 50:
                length_xp = min(length / 100, 2.0)  # Max 2 comfort
                bonuses["comfort"] = bonuses.get("comfort", 0) + length_xp

        # Emotional depth -> intimacy
        if "emotional_depth" in signals:
            depth = signals["emotional_depth"]
            if depth > 0.4:
                bonuses["intimacy"] = bonuses.get("intimacy", 0) + (depth * 5)

        return bonuses

    def save_to_dict(self) -> Dict[str, Any]:
        """Serialize metrics to dictionary"""
        return self.metrics.to_dict()

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """Load metrics from dictionary"""
        self.metrics = RelationshipMetrics.from_dict(data)
