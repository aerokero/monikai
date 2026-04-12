"""Narrative/Story Engine - Story progression and flags"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
import uuid
from ..core.config import STORIES_CATALOG_PATH, NARRATIVE_STATE_PATH


class NarrativeEngine:
    """Manages story progression, triggers, and narrative state"""

    def __init__(self, stories_catalog_path: str = None):
        if stories_catalog_path is None:
            stories_catalog_path = str(STORIES_CATALOG_PATH)
        self.catalog_path = stories_catalog_path
        self.catalog = self._load_catalog()
        self.active_stories: Dict[str, Any] = {}  # Currently playing stories
        self.story_history: List[Dict[str, Any]] = []  # Completed story moments
        self.story_flags: Dict[str, bool] = {}
        self.calendar_events: List[Dict[str, Any]] = []  # Memorable calendar entries
        self.pending_notifications: List[Dict[str, Any]] = []

    def _load_catalog(self) -> Dict[str, Any]:
        """Load stories catalog from JSON"""
        try:
            with open(self.catalog_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Could not load stories catalog from {self.catalog_path}")
            return {"stories": []}

    def evaluate_story_trigger(
        self,
        text: str,
        metrics: Dict[str, float],
        events: List[str]
    ) -> Optional[str]:
        """
        Evaluate if a story should trigger based on message/event.
        Returns story_id if trigger matched, None otherwise.
        """
        stories = self.catalog.get("stories", [])

        for story in stories:
            if self.story_flags.get(f"{story['id']}_played", False):
                # Skip stories already played (unless repeatable)
                if not story.get("repeatable", False):
                    continue

            # Check requirements
            if not self._check_story_requirements(story, metrics):
                continue

            # Check trigger
            if self._check_story_trigger(story, text, events):
                return story["id"]

        return None

    def _check_story_requirements(self, story: Dict[str, Any], metrics: Dict[str, float]) -> bool:
        """Check if story requirements are met"""
        requires = story.get("requires", {})

        # Check metrics
        for metric_name, condition in requires.get("metrics", {}).items():
            current = metrics.get(metric_name, 0)
            operator = condition.get("operator", ">=")
            value = condition.get("value")

            if operator == ">=" and current < value:
                return False
            elif operator == ">" and current <= value:
                return False
            elif operator == "<=" and current > value:
                return False

        # Check flags (must not have certain flags)
        for flag in requires.get("flags_not", []):
            if self.story_flags.get(flag, False):
                return False

        # Check flags (must have certain flags)
        for flag in requires.get("flags", []):
            if not self.story_flags.get(flag, False):
                return False

        # Check unlocks
        # (would need to check against unlock_tracker - pass separately)

        return True

    def _check_story_trigger(self, story: Dict[str, Any], text: str, events: List[str]) -> bool:
        """Check if story trigger matches"""
        trigger = story.get("trigger", {})
        trigger_type = trigger.get("type")

        if trigger_type == "message_contains":
            keywords = trigger.get("keywords", [])
            case_insensitive = trigger.get("case_insensitive", True)
            search_text = text.lower() if case_insensitive else text
            return any(kw.lower() in search_text if case_insensitive else kw in search_text for kw in keywords)

        elif trigger_type == "event":
            event_id = trigger.get("event_id")
            return event_id in events

        elif trigger_type == "achievement":
            achievement_id = trigger.get("achievement_id")
            return achievement_id in events  # events list can contain achievement IDs

        elif trigger_type == "unlock":
            unlock_id = trigger.get("unlock_id")
            return unlock_id in events

        elif trigger_type == "seasonal_event":
            event_id = trigger.get("event_id")
            return event_id in events

        return False

    def execute_story(self, story_id: str) -> List[Dict[str, Any]]:
        """
        Execute a story sequence.
        Returns list of story turns (for frontend to display).
        """
        story = next((s for s in self.catalog.get("stories", []) if s["id"] == story_id), None)
        if not story:
            return []

        self.active_stories[story_id] = {
            "started_at": datetime.utcnow().isoformat(),
            "completed": False
        }

        sequence = story.get("sequence", [])
        turns = []

        for turn in sequence:
            turn_data = {
                "role": turn.get("role"),
                "content": turn.get("content"),
                "type": turn.get("type", "message"),  # message, choice
                "emotional_context": turn.get("emotional_context"),
                "expression": turn.get("expression"),
                "options": turn.get("options", []) if turn.get("type") == "choice" else None,
                "delay_ms": turn.get("delay_ms", 0)
            }
            turns.append(turn_data)

        return turns

    def complete_story(
        self,
        story_id: str,
        user_choice: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mark story as complete and apply rewards/flags.
        Returns dict with rewards and flags set.
        """
        story = next((s for s in self.catalog.get("stories", []) if s["id"] == story_id), None)
        if not story:
            return {}

        result = {}

        # Mark as played
        self.story_flags[f"{story_id}_played"] = True

        # Apply XP rewards
        on_complete = story.get("on_complete", {})
        result["xp_rewards"] = on_complete.get("add_xp", {})

        # Set flags
        for flag in on_complete.get("set_flags", []):
            self.story_flags[flag] = True
        result["flags_set"] = on_complete.get("set_flags", [])

        # Trigger unlocks (unlock IDs)
        result["unlock_ids"] = on_complete.get("unlock_ids", [])

        # Log story moment
        story_moment = {
            "story_id": story_id,
            "title": story.get("title"),
            "completed_at": datetime.utcnow().isoformat(),
            "user_choice": user_choice
        }
        self.story_history.append(story_moment)
        result["story_moment"] = story_moment

        # Queue notification
        notification = {
            "type": "story_complete",
            "event_id": str(uuid.uuid4()),
            "story_id": story_id,
            "title": story.get("title"),
            "timestamp": datetime.utcnow().isoformat()
        }
        self.pending_notifications.append(notification)

        self.active_stories[story_id]["completed"] = True

        return result

    def log_story_moment(self, trigger: str, metadata: Dict[str, Any]) -> None:
        """Log a story-related moment (for calendar events, etc.)"""
        moment = {
            "trigger": trigger,
            "metadata": metadata,
            "logged_at": datetime.utcnow().isoformat()
        }
        self.story_history.append(moment)

    def log_calendar_event(self, event_id: str, title: str, description: str = "") -> None:
        """Log a special calendar event"""
        event = {
            "id": event_id,
            "date": datetime.utcnow().isoformat().split("T")[0],
            "title": title,
            "description": description
        }
        self.calendar_events.append(event)

    def set_story_flag(self, flag_name: str, value: bool = True) -> None:
        """Set a story flag"""
        self.story_flags[flag_name] = value

    def get_story_flag(self, flag_name: str, default: bool = False) -> bool:
        """Get a story flag"""
        return self.story_flags.get(flag_name, default)

    def get_story_context(self) -> Dict[str, Any]:
        """
        Get narrative context for AI (what stories have happened, flags set, etc.)
        Useful for AI to reference past story moments.
        """
        return {
            "story_history": self.story_history,
            "story_flags": self.story_flags,
            "calendar_events": self.calendar_events,
            "active_stories": self.active_stories
        }

    def get_next_story_recommendation(
        self,
        metrics: Dict[str, float],
        recent_events: List[str]
    ) -> Optional[str]:
        """
        Recommend the next story to play based on state.
        Returns story_id or None.
        """
        # Find stories that:
        # 1. Haven't been played yet
        # 2. Requirements are met
        # 3. Return the one with highest "order" (priority)

        available_stories = []
        for story in self.catalog.get("stories", []):
            if self.story_flags.get(f"{story['id']}_played", False):
                continue
            if self._check_story_requirements(story, metrics):
                available_stories.append(story)

        if available_stories:
            # Sort by some priority (could be implicit order in catalog)
            available_stories.sort(key=lambda s: s.get("id"))
            return available_stories[0]["id"]

        return None

    def get_pending_notifications(self) -> List[Dict[str, Any]]:
        """Get and clear pending notifications"""
        notifications = self.pending_notifications
        self.pending_notifications = []
        return notifications

    def save_state(self, filepath: str = None) -> bool:
        """Save narrative state to file"""
        if filepath is None:
            filepath = str(NARRATIVE_STATE_PATH)
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            data = {
                "story_flags": self.story_flags,
                "story_history": self.story_history,
                "calendar_events": self.calendar_events
            }
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except (IOError, OSError):
            return False

    def load_state(self, filepath: str = None) -> bool:
        """Load narrative state from file"""
        if filepath is None:
            filepath = str(NARRATIVE_STATE_PATH)
        try:
            if not os.path.exists(filepath):
                return False
            with open(filepath, "r") as f:
                data = json.load(f)
                self.story_flags = data.get("story_flags", {})
                self.story_history = data.get("story_history", [])
                self.calendar_events = data.get("calendar_events", [])
            return True
        except (IOError, json.JSONDecodeError):
            return False
