"""Achievement Tracking System"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
import uuid


@dataclass
class UnlockedAchievement:
    """Achievement that has been unlocked"""
    achievement_id: str
    unlocked_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    xp_earned: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AchievementTracker:
    """Tracks and manages achievement unlocking"""

    def __init__(self, achievements_catalog_path: str = "data/achievements/achievements_catalog.json"):
        self.catalog_path = achievements_catalog_path
        self.catalog = self._load_catalog()
        self.unlocked_achievements: Dict[str, UnlockedAchievement] = {}
        self.pending_notifications: List[Dict[str, Any]] = []

    def _load_catalog(self) -> Dict[str, Any]:
        """Load achievements catalog from JSON"""
        try:
            with open(self.catalog_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Could not load achievements catalog from {self.catalog_path}")
            return {"achievements": []}

    def check_event_achievement(self, event_id: str) -> List[Dict[str, Any]]:
        """
        Check if any achievements are triggered by an event.
        Returns list of newly unlocked achievements.
        """
        newly_unlocked = []
        achievements = self.catalog.get("achievements", [])

        for achievement in achievements:
            if achievement["id"] in self.unlocked_achievements:
                continue  # Already unlocked

            condition = achievement.get("condition", {})
            if condition.get("type") == "event" and condition.get("event") == event_id:
                result = self._unlock_achievement(achievement)
                if result:
                    newly_unlocked.append(result)

        return newly_unlocked

    def check_stat_achievements(self, metrics: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Check if any stat-based achievements are triggered.
        metrics: {'affection': 50, 'comfort': 30, ...}
        Returns list of newly unlocked achievements.
        """
        newly_unlocked = []
        achievements = self.catalog.get("achievements", [])

        for achievement in achievements:
            if achievement["id"] in self.unlocked_achievements:
                continue  # Already unlocked

            condition = achievement.get("condition", {})
            if condition.get("type") == "metric_threshold":
                metric_name = condition.get("metric")
                operator = condition.get("operator", ">=")
                threshold = condition.get("value")

                current_value = metrics.get(metric_name, 0)

                # Evaluate condition
                if operator == ">=" and current_value >= threshold:
                    result = self._unlock_achievement(achievement)
                    if result:
                        newly_unlocked.append(result)
                elif operator == ">" and current_value > threshold:
                    result = self._unlock_achievement(achievement)
                    if result:
                        newly_unlocked.append(result)
                elif operator == "<=" and current_value <= threshold:
                    result = self._unlock_achievement(achievement)
                    if result:
                        newly_unlocked.append(result)

        return newly_unlocked

    def check_message_achievements(self, text: str) -> List[Dict[str, Any]]:
        """
        Check if any hidden/message-based achievements trigger.
        Returns list of newly unlocked achievements.
        """
        newly_unlocked = []
        achievements = self.catalog.get("achievements", [])

        for achievement in achievements:
            if achievement["id"] in self.unlocked_achievements:
                continue

            condition = achievement.get("condition", {})
            if condition.get("type") == "message_contains":
                keywords = condition.get("keywords", [])
                case_insensitive = condition.get("case_insensitive", True)
                search_text = text.lower() if case_insensitive else text

                if any(kw.lower() in search_text if case_insensitive else kw in search_text for kw in keywords):
                    result = self._unlock_achievement(achievement)
                    if result:
                        newly_unlocked.append(result)

        return newly_unlocked

    def check_activity_achievements(self, activity_type: str, activity_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Check if activity-based achievements trigger.
        activity_type: 'minecraft', 'watching', etc.
        activity_data: specific data about the activity
        """
        newly_unlocked = []
        achievements = self.catalog.get("achievements", [])

        for achievement in achievements:
            if achievement["id"] in self.unlocked_achievements:
                continue

            condition = achievement.get("condition", {})
            if condition.get("type") == "activity_detect":
                if condition.get("activity") == activity_type:
                    keywords = condition.get("keywords", [])
                    # Check if activity_data matches keywords
                    # This is flexible - implementation depends on activity_data structure
                    result = self._unlock_achievement(achievement)
                    if result:
                        newly_unlocked.append(result)

        return newly_unlocked

    def check_streak_achievements(self, streak_days: int) -> List[Dict[str, Any]]:
        """Check if streak-based achievements trigger"""
        newly_unlocked = []
        achievements = self.catalog.get("achievements", [])

        for achievement in achievements:
            if achievement["id"] in self.unlocked_achievements:
                continue

            condition = achievement.get("condition", {})
            if condition.get("type") == "streak_days":
                operator = condition.get("operator", ">=")
                value = condition.get("value")

                if operator == ">=" and streak_days >= value:
                    result = self._unlock_achievement(achievement)
                    if result:
                        newly_unlocked.append(result)

        return newly_unlocked

    def _unlock_achievement(self, achievement: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Unlock an achievement.
        Returns dict with achievement info and rewards.
        """
        achievement_id = achievement["id"]

        if achievement_id in self.unlocked_achievements:
            return None

        unlocked = UnlockedAchievement(
            achievement_id=achievement_id,
            xp_earned=achievement.get("reward", {}).get("xp_to_metrics", {})
        )
        self.unlocked_achievements[achievement_id] = unlocked

        # Queue notification
        notification = {
            "type": "achievement_unlocked",
            "event_id": str(uuid.uuid4()),
            "achievement_id": achievement_id,
            "title": achievement.get("title"),
            "description": achievement.get("description"),
            "icon": achievement.get("icon"),
            "rarity": achievement.get("rarity"),
            "timestamp": datetime.utcnow().isoformat()
        }
        self.pending_notifications.append(notification)

        return {
            "achievement_id": achievement_id,
            "title": achievement.get("title"),
            "description": achievement.get("description"),
            "rewards": achievement.get("reward"),
            "unlocked_at": unlocked.unlocked_at,
            "triggers_story": achievement.get("reward", {}).get("trigger_story")
        }

    def is_achievement_unlocked(self, achievement_id: str) -> bool:
        """Check if achievement is unlocked"""
        return achievement_id in self.unlocked_achievements

    def get_unlocked_achievements(self) -> List[Dict[str, Any]]:
        """Get all unlocked achievements"""
        result = []
        for achievement_id in self.unlocked_achievements:
            achievement_data = next(
                (a for a in self.catalog.get("achievements", []) if a["id"] == achievement_id),
                None
            )
            if achievement_data:
                result.append({
                    **achievement_data,
                    "unlocked_at": self.unlocked_achievements[achievement_id].unlocked_at
                })
        return result

    def get_locked_achievements(self) -> List[Dict[str, Any]]:
        """Get all locked achievements"""
        locked = []
        for achievement in self.catalog.get("achievements", []):
            if achievement["id"] not in self.unlocked_achievements:
                locked.append(achievement)
        return locked

    def get_achievements_progress(self) -> Dict[str, Any]:
        """
        Get progress towards achievements.
        Returns dict with unlocked count, total count, progress %
        """
        total = len(self.catalog.get("achievements", []))
        unlocked = len(self.unlocked_achievements)
        return {
            "unlocked": unlocked,
            "total": total,
            "progress_pct": (unlocked / total * 100) if total > 0 else 0
        }

    def get_pending_notifications(self) -> List[Dict[str, Any]]:
        """Get and clear pending notifications"""
        notifications = self.pending_notifications
        self.pending_notifications = []
        return notifications

    def save_achievements(self, filepath: str = "data/user_memory/achievements.json") -> bool:
        """Save unlocked achievements to file"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            data = {
                achievement_id: unlocked.to_dict()
                for achievement_id, unlocked in self.unlocked_achievements.items()
            }
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except (IOError, OSError):
            return False

    def load_achievements(self, filepath: str = "data/user_memory/achievements.json") -> bool:
        """Load unlocked achievements from file"""
        try:
            if not os.path.exists(filepath):
                return False
            with open(filepath, "r") as f:
                data = json.load(f)
                self.unlocked_achievements = {
                    k: UnlockedAchievement(**v) for k, v in data.items()
                }
            return True
        except (IOError, json.JSONDecodeError):
            return False
