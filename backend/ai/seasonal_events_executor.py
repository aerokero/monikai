"""Seasonal Events Executor"""
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
import uuid


class SeasonalEventsExecutor:
    """Manages and executes seasonal events"""

    def __init__(self, events_catalog_path: str = "data/seasonal_events/events_calendar.json"):
        self.catalog_path = events_catalog_path
        self.catalog = self._load_catalog()
        self.active_events: Dict[str, bool] = {}  # event_id -> is_active
        self.event_history: List[Dict[str, Any]] = []
        self.pending_notifications: List[Dict[str, Any]] = []

    def _load_catalog(self) -> Dict[str, Any]:
        """Load seasonal events catalog"""
        try:
            with open(self.catalog_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Could not load seasonal events from {self.catalog_path}")
            return {"events": []}

    def check_active_events(self, current_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Check which seasonal events are currently active.
        current_date: datetime object (defaults to now)
        Returns list of active events.
        """
        if not current_date:
            current_date = datetime.now()

        active = []
        events = self.catalog.get("events", [])

        for event in events:
            if self._is_event_active(event, current_date):
                event_id = event["id"]
                self.active_events[event_id] = True
                active.append(event)

        return active

    def _is_event_active(self, event: Dict[str, Any], current_date: datetime) -> bool:
        """Check if an event is currently active"""
        date_str = event.get("date")
        month_day = event.get("month_day")

        if not month_day:
            return False

        event_month, event_day = month_day
        current_month = current_date.month
        current_day = current_date.day

        # Calculate event window
        before_days = event.get("active_days_before", 3)
        after_days = event.get("active_days_after", 1)

        # Simple check (doesn't handle month boundaries perfectly)
        if event_month == current_month:
            start_day = max(1, event_day - before_days)
            end_day = event_day + after_days
            return start_day <= current_day <= end_day

        return False

    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get event details by ID"""
        return next((e for e in self.catalog.get("events", []) if e["id"] == event_id), None)

    def get_event_special_quests(self, event_id: str) -> List[str]:
        """Get special quest template IDs for an event"""
        event = self.get_event_by_id(event_id)
        if event:
            return event.get("special_quests", [])
        return []

    def get_event_special_achievements(self, event_id: str) -> List[str]:
        """Get special achievement IDs for an event"""
        event = self.get_event_by_id(event_id)
        if event:
            return event.get("special_achievements", [])
        return []

    def get_event_special_stories(self, event_id: str) -> List[str]:
        """Get special story IDs for an event"""
        event = self.get_event_by_id(event_id)
        if event:
            return event.get("special_stories", [])
        return []

    def get_xp_multiplier(self, event_id: str, metric: str) -> float:
        """Get XP multiplier for a metric during an event"""
        event = self.get_event_by_id(event_id)
        if event:
            multipliers = event.get("xp_multiplier_metrics", {})
            return multipliers.get(metric, 1.0)
        return 1.0

    def has_notification(self, event_id: str, days_ahead: int = 0) -> bool:
        """Check if event has notification due"""
        event = self.get_event_by_id(event_id)
        if not event:
            return False

        notification_before = event.get("notification_before_days", 0)
        return days_ahead <= notification_before

    def queue_event_notifications(self, current_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Queue notifications for upcoming/active events"""
        if not current_date:
            current_date = datetime.now()

        notifications = []
        events = self.catalog.get("events", [])

        for event in events:
            event_id = event["id"]
            month_day = event.get("month_day")

            if not month_day:
                continue

            event_month, event_day = month_day

            # Calculate days until event
            current_month = current_date.month
            current_day = current_date.day

            # Simple calculation (doesn't handle year boundary)
            if current_month <= event_month:
                days_until = (event_month - current_month) * 30 + (event_day - current_day)
            else:
                days_until = 365 - ((current_month - event_month) * 30 + (current_day - event_day))

            notification_before = event.get("notification_before_days", 0)
            if 0 <= days_until <= notification_before:
                notification = {
                    "type": "seasonal_event",
                    "event_id": event_id,
                    "event_name": event.get("name"),
                    "days_left": days_until,
                    "template": event.get("notification_template"),
                    "timestamp": datetime.utcnow().isoformat()
                }
                notifications.append(notification)
                self.pending_notifications.append(notification)

        return notifications

    def log_event_participation(self, event_id: str, participation_data: Dict[str, Any]) -> None:
        """Log when user participates in an event"""
        event_log = {
            "event_id": event_id,
            "event_name": self.get_event_by_id(event_id).get("name") if self.get_event_by_id(event_id) else None,
            "participated_at": datetime.utcnow().isoformat(),
            "participation_data": participation_data
        }
        self.event_history.append(event_log)

    def get_event_history(self) -> List[Dict[str, Any]]:
        """Get event participation history"""
        return self.event_history

    def get_pending_notifications(self) -> List[Dict[str, Any]]:
        """Get and clear pending notifications"""
        notifications = self.pending_notifications
        self.pending_notifications = []
        return notifications

    def save_state(self, filepath: str = "data/user_memory/seasonal_events_state.json") -> bool:
        """Save seasonal events state"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            data = {
                "active_events": self.active_events,
                "event_history": self.event_history
            }
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except (IOError, OSError):
            return False

    def load_state(self, filepath: str = "data/user_memory/seasonal_events_state.json") -> bool:
        """Load seasonal events state"""
        try:
            if not os.path.exists(filepath):
                return False
            with open(filepath, "r") as f:
                data = json.load(f)
                self.active_events = data.get("active_events", {})
                self.event_history = data.get("event_history", [])
            return True
        except (IOError, json.JSONDecodeError):
            return False
