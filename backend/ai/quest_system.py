"""Quest System - Daily routine and activity-based quests"""
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid


class QuestStatus(Enum):
    """Quest status enum"""
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    SKIPPED = "skipped"


@dataclass
class Quest:
    """Represents a single quest"""
    id: str
    template_id: str
    title: str
    description: str
    type: str  # 'daily_routine', 'activity', 'pursuit'
    slot: Optional[str]  # 'morning', 'afternoon', 'evening'
    status: str = QuestStatus.ACTIVE.value
    progress: float = 0.0
    target: float = 1.0  # For completion (0-1)
    reward_metric: str = "affection"
    reward_xp: float = 5.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    expires_at: Optional[str] = None
    required_bond_level: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def is_expired(self) -> bool:
        """Check if quest has expired"""
        if not self.expires_at:
            return False
        return datetime.fromisoformat(self.expires_at) < datetime.utcnow()

    def is_completed(self) -> bool:
        """Check if quest is completed"""
        return self.status == QuestStatus.COMPLETED.value

    def mark_completed(self) -> None:
        """Mark quest as completed"""
        self.status = QuestStatus.COMPLETED.value
        self.completed_at = datetime.utcnow().isoformat()
        self.progress = 1.0


class QuestSystem:
    """Manages daily quests and quest tracking"""

    def __init__(self, quest_catalog_path: str = "data/quests/quest_catalog.json"):
        self.quest_catalog_path = quest_catalog_path
        self.catalog = self._load_catalog()
        self.active_quests: List[Quest] = []

    def _load_catalog(self) -> Dict[str, Any]:
        """Load quest catalog from JSON"""
        try:
            with open(self.quest_catalog_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Could not load quest catalog from {self.quest_catalog_path}")
            return {"quest_templates": [], "quest_pools": {}}

    def generate_daily_quests(self, timezone: str = "UTC", preferred_activities: List[str] = None) -> List[Quest]:
        """
        Generate daily quests based on time of day and user preferences.
        Returns list of newly created quests.
        """
        if preferred_activities is None:
            preferred_activities = []

        new_quests = []
        templates = {t["id"]: t for t in self.catalog.get("quest_templates", [])}

        # Morning routine
        morning_quest = self._create_quest_from_template(
            templates.get("morning_checkin_sleep"),
            timezone
        )
        if morning_quest:
            new_quests.append(morning_quest)
            self.active_quests.append(morning_quest)

        # Activity-based (based on preferred_activities)
        for activity in preferred_activities[:2]:  # Max 2 activity quests
            activity_key = f"afternoon_activity_{activity}"
            if activity_key in templates:
                activity_quest = self._create_quest_from_template(templates[activity_key], timezone)
                if activity_quest:
                    new_quests.append(activity_quest)
                    self.active_quests.append(activity_quest)

        # Evening routine
        evening_quest = self._create_quest_from_template(
            templates.get("evening_reflection"),
            timezone
        )
        if evening_quest:
            new_quests.append(evening_quest)
            self.active_quests.append(evening_quest)

        return new_quests

    def _create_quest_from_template(self, template: Optional[Dict[str, Any]], timezone: str) -> Optional[Quest]:
        """Create a quest instance from a template"""
        if not template:
            return None

        # Calculate expiration (24 hours from now)
        expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()

        quest = Quest(
            id=str(uuid.uuid4()),
            template_id=template["id"],
            title=template["title"],
            description=template["description"],
            type=template.get("type", "daily_routine"),
            slot=template.get("slot"),
            reward_metric=template["reward_xp"]["metric"],
            reward_xp=template["reward_xp"]["amount"],
            expires_at=expires_at,
            required_bond_level=template.get("required_bond_level", 0)
        )
        return quest

    def check_quest_completion(self, text: str, signals: Dict[str, Any]) -> List[Quest]:
        """
        Check if message completes any active quests.
        Returns list of completed quests.
        """
        completed = []

        for quest in self.active_quests:
            if quest.is_expired() or quest.is_completed():
                continue

            # Check condition from template
            template_id = quest.template_id
            templates = {t["id"]: t for t in self.catalog.get("quest_templates", [])}
            template = templates.get(template_id)

            if not template:
                continue

            condition = template.get("condition", {})
            if self._check_condition(condition, text, signals):
                quest.mark_completed()
                completed.append(quest)

        return completed

    def _check_condition(self, condition: Dict[str, Any], text: str, signals: Dict[str, Any]) -> bool:
        """Evaluate if a quest condition is met"""
        cond_type = condition.get("type")

        if cond_type == "any_message_morning":
            hour = datetime.utcnow().hour
            after_hours = condition.get("after_hours", 6)
            before_hours = condition.get("before_hours", 12)
            return after_hours <= hour < before_hours

        elif cond_type == "any_message_evening":
            hour = datetime.utcnow().hour
            after_hours = condition.get("after_hours", 18)
            before_hours = condition.get("before_hours", 23)
            return after_hours <= hour < before_hours

        elif cond_type == "message_contains":
            keywords = condition.get("keywords", [])
            case_insensitive = condition.get("case_insensitive", False)
            search_text = text.lower() if case_insensitive else text
            return any(kw.lower() in search_text if case_insensitive else kw in search_text for kw in keywords)

        elif cond_type == "event":
            # Event-based conditions handled elsewhere
            return False

        return True

    def get_active_quests(self) -> List[Dict[str, Any]]:
        """Get list of active, non-expired quests"""
        active = [q for q in self.active_quests
                 if q.status == QuestStatus.ACTIVE.value and not q.is_expired()]
        return [q.to_dict() for q in active]

    def get_quests_by_slot(self, slot: str) -> List[Dict[str, Any]]:
        """Get active quests for a specific slot (morning/afternoon/evening)"""
        quests = [q for q in self.active_quests
                 if q.slot == slot and q.status == QuestStatus.ACTIVE.value and not q.is_expired()]
        return [q.to_dict() for q in quests]

    def clear_expired_quests(self) -> int:
        """Remove expired quests, return count"""
        before = len(self.active_quests)
        self.active_quests = [q for q in self.active_quests if not q.is_expired()]
        return before - len(self.active_quests)

    def save_quests(self, filepath: str = "data/sessions/current_quests.json") -> bool:
        """Save active quests to file"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as f:
                json.dump([q.to_dict() for q in self.active_quests], f, indent=2)
            return True
        except (IOError, OSError):
            return False

    def load_quests(self, filepath: str = "data/sessions/current_quests.json") -> bool:
        """Load quests from file"""
        try:
            if not os.path.exists(filepath):
                return False
            with open(filepath, "r") as f:
                data = json.load(f)
                self.active_quests = [Quest(**q) for q in data]
            return True
        except (IOError, json.JSONDecodeError):
            return False
