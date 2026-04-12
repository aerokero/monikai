"""Unlock Tracker System - Feature and narrative unlocks"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any, Set
import uuid
from ..core.config import UNLOCKS_CATALOG_PATH, UNLOCKS_STATE_PATH


class UnlockTracker:
    """Manages feature and narrative unlocks"""

    def __init__(self, unlocks_catalog_path: str = None):
        if unlocks_catalog_path is None:
            unlocks_catalog_path = str(UNLOCKS_CATALOG_PATH)
        self.catalog_path = unlocks_catalog_path
        self.catalog = self._load_catalog()
        self.active_unlocks: Set[str] = set()  # IDs of unlocked features
        self.pending_notifications: List[Dict[str, Any]] = []
        self.story_flags: Dict[str, bool] = {}

    def _load_catalog(self) -> Dict[str, Any]:
        """Load unlocks catalog from JSON"""
        try:
            with open(self.catalog_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Could not load unlocks catalog from {self.catalog_path}")
            return {"unlocks": []}

    def fulfill_requirements(self, unlock: Dict[str, Any]) -> bool:
        """
        Check if all requirements for an unlock are fulfilled.
        Requirements can be:
        - achievements (achievement must be unlocked)
        - metrics (metric must reach threshold)
        - flags (story flags must be set)
        """
        requires = unlock.get("requires", [])

        for req in requires:
            req_type = req.get("type")

            if req_type == "achievement":
                # Achievements are checked before calling this - should be passed separately
                pass
            elif req_type == "metric":
                # Metrics are checked before calling this
                pass
            elif req_type == "flag":
                # Story flag requirement
                flag_name = req.get("name")
                if not self.story_flags.get(flag_name, False):
                    return False

        return True

    def trigger_unlock(
        self,
        unlock_id: str,
        triggered_by: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Trigger an unlock.
        triggered_by: {"type": "achievement", "id": "achievement_id"} or similar
        Returns unlock data or None if already unlocked
        """
        if unlock_id in self.active_unlocks:
            return None

        # Find unlock in catalog
        unlock = next((u for u in self.catalog.get("unlocks", []) if u["id"] == unlock_id), None)
        if not unlock:
            return None

        # Mark as active
        self.active_unlocks.add(unlock_id)

        # Set story flags if any
        for flag in unlock.get("sets_story_flags", []):
            self.story_flags[flag] = True

        # Handle triggers
        for trigger in unlock.get("triggers_on_unlock", []):
            trigger_type = trigger.get("type")

            if trigger_type == "notification":
                notification = {
                    "type": "unlock",
                    "event_id": str(uuid.uuid4()),
                    "unlock_id": unlock_id,
                    "title": unlock.get("label"),
                    "content": trigger.get("content"),
                    "category": unlock.get("category"),
                    "timestamp": datetime.utcnow().isoformat()
                }
                self.pending_notifications.append(notification)

            elif trigger_type == "story":
                # Story should be triggered by narrative engine
                pass

        return {
            "unlock_id": unlock_id,
            "label": unlock.get("label"),
            "description": unlock.get("description"),
            "category": unlock.get("category"),
            "type": unlock.get("type"),
            "triggered_by": triggered_by,
            "unlocked_at": datetime.utcnow().isoformat()
        }

    def check_unlock_requirements(
        self,
        achievement_id: str,
        metrics: Dict[str, float],
        achieved_ids: List[str]
    ) -> List[str]:
        """
        After an achievement/metric achievement, check which unlocks should trigger.
        Returns list of unlock IDs to activate.
        """
        to_unlock = []
        unlocks = self.catalog.get("unlocks", [])

        for unlock in unlocks:
            if unlock["id"] in self.active_unlocks:
                continue  # Already unlocked

            requires = unlock.get("requires", [])
            all_met = True

            for req in requires:
                req_type = req.get("type")

                if req_type == "achievement":
                    req_id = req.get("id")
                    if req_id not in achieved_ids:
                        all_met = False
                        break

                elif req_type == "metric":
                    metric_name = req.get("metric")
                    operator = req.get("operator", ">=")
                    value = req.get("value")
                    current = metrics.get(metric_name, 0)

                    if operator == ">=" and current < value:
                        all_met = False
                        break
                    elif operator == ">" and current <= value:
                        all_met = False
                        break

            if all_met:
                to_unlock.append(unlock["id"])

        return to_unlock

    def is_unlock_active(self, unlock_id: str) -> bool:
        """Check if unlock is active"""
        return unlock_id in self.active_unlocks

    def get_active_unlocks(self) -> List[Dict[str, Any]]:
        """Get list of active unlocks"""
        result = []
        for unlock_id in self.active_unlocks:
            unlock_data = next(
                (u for u in self.catalog.get("unlocks", []) if u["id"] == unlock_id),
                None
            )
            if unlock_data:
                result.append(unlock_data)
        return result

    def get_available_unlocks(self) -> List[Dict[str, Any]]:
        """Get unlocks that haven't been activated yet"""
        return [u for u in self.catalog.get("unlocks", []) if u["id"] not in self.active_unlocks]

    def set_story_flag(self, flag_name: str, value: bool = True) -> None:
        """Set a story progression flag"""
        self.story_flags[flag_name] = value

    def get_story_flag(self, flag_name: str, default: bool = False) -> bool:
        """Get a story flag value"""
        return self.story_flags.get(flag_name, default)

    def get_all_flags(self) -> Dict[str, bool]:
        """Get all story flags"""
        return self.story_flags.copy()

    def get_pending_notifications(self) -> List[Dict[str, Any]]:
        """Get and clear pending notifications"""
        notifications = self.pending_notifications
        self.pending_notifications = []
        return notifications

    def save_state(self, filepath: str = None) -> bool:
        """Save unlock state to file"""
        if filepath is None:
            filepath = str(UNLOCKS_STATE_PATH)
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            data = {
                "active_unlocks": list(self.active_unlocks),
                "story_flags": self.story_flags
            }
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except (IOError, OSError):
            return False

    def load_state(self, filepath: str = None) -> bool:
        """Load unlock state from file"""
        if filepath is None:
            filepath = str(UNLOCKS_STATE_PATH)
        try:
            if not os.path.exists(filepath):
                return False
            with open(filepath, "r") as f:
                data = json.load(f)
                self.active_unlocks = set(data.get("active_unlocks", []))
                self.story_flags = data.get("story_flags", {})
            return True
        except (IOError, json.JSONDecodeError):
            return False
