"""Activity Logger System - Conversation-based activity detection"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
import uuid
from ..core.config import QUESTS_CATALOG_PATH, ACTIVITY_LOG_PATH


class ActivityLogger:
    """
    Detects and logs activities from conversation.
    Conversation-based analysis only (no realtime tracking).
    """

    def __init__(self, activity_patterns_path: str = None):
        """
        Initialize with quest catalog that contains activity patterns.
        Patterns are extracted from quest conditions.
        """
        if activity_patterns_path is None:
            activity_patterns_path = str(QUESTS_CATALOG_PATH)
        self.activity_patterns = self._load_patterns(activity_patterns_path)
        self.activity_log: List[Dict[str, Any]] = []
        self.pending_notifications: List[Dict[str, Any]] = []

    def _load_patterns(self, catalog_path: str) -> Dict[str, List[str]]:
        """Extract activity patterns from quest catalog"""
        patterns = {}
        try:
            with open(catalog_path, "r") as f:
                catalog = json.load(f)
                for template in catalog.get("quest_templates", []):
                    activity = template.get("activity")
                    if activity:
                        condition = template.get("condition", {})
                        keywords = condition.get("keywords", [])
                        if activity not in patterns:
                            patterns[activity] = []
                        patterns[activity].extend(keywords)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        return patterns

    def analyze_activity_mentions(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse message for activity mentions.
        Returns list of detected activities with metadata.
        """
        detected = []
        text_lower = text.lower()

        for activity_type, keywords in self.activity_patterns.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    detected.append({
                        "activity": activity_type,
                        "keyword": keyword,
                        "confidence": 0.8  # Keyword match confidence
                    })

        return detected

    def log_activity(
        self,
        activity_type: str,
        metadata: Dict[str, Any],
        message_context: str = ""
    ) -> Dict[str, Any]:
        """
        Log an activity.
        activity_type: 'minecraft', 'watching', 'learning', 'gaming', 'conversation'
        metadata: activity-specific data
        Returns logged activity object.
        """
        activity_log_entry = {
            "id": str(uuid.uuid4()),
            "activity_type": activity_type,
            "metadata": metadata,
            "message_context": message_context,
            "logged_at": datetime.utcnow().isoformat()
        }
        self.activity_log.append(activity_log_entry)

        return activity_log_entry

    def detect_minecraft_activity(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect Minecraft-specific activities from message"""
        text_lower = text.lower()

        # Check for co-play indicators
        coplay_keywords = ["we played", "we exploring", "we built", "together"]
        is_coplay = any(kw in text_lower for kw in coplay_keywords)

        # Check for structure/achievement keywords
        structures = ["house", "home", "base", "farm", "castle", "temple"]
        achievements = ["diamond", "goal", "achievement", "level", "boss"]

        detected_structures = [s for s in structures if s in text_lower]
        detected_achievements = [a for a in achievements if a in text_lower]

        if detected_structures or detected_achievements or is_coplay:
            activity_data = {
                "co_play": is_coplay,
                "structures": detected_structures,
                "achievements": detected_achievements,
                "detected_at": datetime.utcnow().isoformat()
            }
            self.log_activity("minecraft", activity_data, text)
            return activity_data

        return None

    def detect_watching_activity(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect watching/media consumption from message"""
        text_lower = text.lower()

        watching_keywords = ["watched", "watching", "series", "movie", "film", "show", "episode", "video"]
        if any(kw in text_lower for kw in watching_keywords):
            activity_data = {
                "detected_at": datetime.utcnow().isoformat()
            }
            self.log_activity("watching", activity_data, text)
            return activity_data

        return None

    def detect_learning_activity(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect learning/studying from message"""
        text_lower = text.lower()

        learning_keywords = ["learned", "learning", "studying", "studied", "reading", "read", "research"]
        if any(kw in text_lower for kw in learning_keywords):
            activity_data = {
                "detected_at": datetime.utcnow().isoformat()
            }
            self.log_activity("learning", activity_data, text)
            return activity_data

        return None

    def get_activity_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        Get summary of activities in past N days.
        Returns dict with activity counts and breakdown.
        """
        cutoff = datetime.utcnow().timestamp() - (days * 86400)
        recent_activities = [
            a for a in self.activity_log
            if datetime.fromisoformat(a["logged_at"]).timestamp() > cutoff
        ]

        summary = {
            "period_days": days,
            "total_activities": len(recent_activities),
            "by_type": {}
        }

        for activity in recent_activities:
            activity_type = activity["activity_type"]
            summary["by_type"][activity_type] = summary["by_type"].get(activity_type, 0) + 1

        return summary

    def check_activity_triggers(self, triggered_activities: List[str]) -> List[Dict[str, Any]]:
        """
        Check if detected activities trigger any achievement conditions.
        triggered_activities: list of detected activity types from message analysis
        Returns list of potential achievement triggers.
        """
        # This is simplified - actual implementation would check
        # against achievement conditions stored elsewhere
        triggers = []

        for activity in triggered_activities:
            if activity == "minecraft":
                # Check for minecraft-specific achievements
                triggers.append({
                    "type": "activity_detect",
                    "activity": "minecraft",
                    "potential_achievements": [
                        "minecraft_builder",
                        "minecraft_companion"
                    ]
                })

        return triggers

    def get_activity_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent activity log entries"""
        return self.activity_log[-limit:]

    def get_pending_notifications(self) -> List[Dict[str, Any]]:
        """Get and clear pending notifications"""
        notifications = self.pending_notifications
        self.pending_notifications = []
        return notifications

    def save_log(self, filepath: str = None) -> bool:
        """Save activity log to file"""
        if filepath is None:
            filepath = str(ACTIVITY_LOG_PATH)
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(self.activity_log, f, indent=2)
            return True
        except (IOError, OSError):
            return False

    def load_log(self, filepath: str = None) -> bool:
        """Load activity log from file"""
        if filepath is None:
            filepath = str(ACTIVITY_LOG_PATH)
        try:
            if not os.path.exists(filepath):
                return False
            with open(filepath, "r") as f:
                self.activity_log = json.load(f)
            return True
        except (IOError, json.JSONDecodeError):
            return False
