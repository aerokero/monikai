"""
Integrated Progression System - Combines all new engines
Provides clean interface for personality.py to plug into
"""
import json
import os
from datetime import datetime
from typing import Dict, Optional, Any, List, Tuple

from backend.ai.user_profile import UserProfileManager, UserProfile
from backend.ai.relationship_metrics import RelationshipMetricsEngine, RelationshipMetrics
from backend.ai.quest_system import QuestSystem
from backend.ai.achievement_tracker import AchievementTracker
from backend.ai.unlock_tracker import UnlockTracker
from backend.ai.narrative_engine import NarrativeEngine
from backend.ai.activity_logger import ActivityLogger
from backend.ai.seasonal_events_executor import SeasonalEventsExecutor


class IntegratedProgressionSystem:
    """
    Main progression engine that coordinates all subsystems.
    This is the interface personality.py should use.
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id

        # Initialize all subsystems
        self.profile_manager = UserProfileManager()
        self.metrics_engine = RelationshipMetricsEngine()
        self.quest_system = QuestSystem()
        self.achievement_tracker = AchievementTracker()
        self.unlock_tracker = UnlockTracker()
        self.narrative_engine = NarrativeEngine()
        self.activity_logger = ActivityLogger()
        self.seasonal_executor = SeasonalEventsExecutor()

        # State tracking
        self.pending_notifications: List[Dict[str, Any]] = []
        self.last_save_ts = datetime.utcnow().timestamp()
        self.save_interval_sec = 6

    def initialize_or_load(self) -> bool:
        """Initialize fresh or load existing progression state"""
        # Try to load profile
        if self.profile_manager.load_profile():
            # Load all subsystem states
            self.metrics_engine.load_from_dict(self._load_json("data/user_memory/metrics_state.json", {}))
            self.quest_system.load_quests()
            self.achievement_tracker.load_achievements()
            self.unlock_tracker.load_state()
            self.narrative_engine.load_state()
            self.activity_logger.load_log()
            self.seasonal_executor.load_state()
            return True
        return False

    def start_onboarding(self) -> Tuple[str, str]:
        """
        Start onboarding flow.
        Returns (onboarding_started_message, next_prompt)
        """
        from backend.core.onboarding import OnboardingManager
        self.onboarding_manager = OnboardingManager()
        user_id = self.onboarding_manager.start_onboarding(self.user_id)
        flow = self.onboarding_manager.get_flow(user_id)
        return ("Witam! Zanim zaczniemy, chciałbym cię lepiej poznać.", flow.get_current_prompt())

    def process_onboarding_response(self, user_input: str) -> Dict[str, Any]:
        """Process onboarding response"""
        if not hasattr(self, 'onboarding_manager'):
            return {"error": "Onboarding not started"}

        result = self.onboarding_manager.process_response(self.user_id, user_input)

        # If completed, create profile
        if result.get("completed"):
            completed_data = self.onboarding_manager.complete_onboarding(self.user_id)
            if completed_data:
                profile = UserProfile(**completed_data)
                self.profile_manager.save_profile(profile)
                self.profile_manager.profile = profile

                # Fire first_meeting achievement
                achievements = self.achievement_tracker.check_event_achievement("onboarding_complete")
                self.pending_notifications.extend(
                    [self.achievement_tracker._unlock_achievement(a) for a in self.achievement_tracker.catalog.get("achievements", [])
                     if a["id"] in [ach["achievement_id"] for ach in achievements]]
                )

                # Generate initial quests
                self.quest_system.generate_daily_quests(
                    profile.timezone,
                    profile.preferred_activities
                )

                self.save_all()

        return result

    def observe_message(
        self,
        text: str,
        sender: str = "user",
        signals: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a message through all progression systems.
        This is the main hook from personality.py.

        Returns dict with:
        - metrics_updated: list of metric changes
        - quests_completed: list of completed quests
        - achievements_unlocked: list of new achievements
        - unlocks_triggered: list of new unlocks
        - stories_triggered: list of story IDs to play
        - notifications: list of notifications to queue
        """
        profile = self.profile_manager.get_profile()
        if not profile:
            return {"error": "No profile loaded"}

        if signals is None:
            signals = self._analyze_message(text)

        result = {
            "metrics_updated": [],
            "quests_completed": [],
            "achievements_unlocked": [],
            "unlocks_triggered": [],
            "stories_triggered": [],
            "notifications": []
        }

        # 1. Update relationship metrics
        bonuses = self.metrics_engine.apply_message_bonuses(signals)
        for metric_name, amount in bonuses.items():
            metric_result = self.metrics_engine.add_xp(metric_name, amount)
            result["metrics_updated"].append({
                "metric": metric_name,
                "amount": amount,
                "new_value": metric_result["new_value"]
            })

        # 2. Update streak
        self.metrics_engine.update_streak()

        # 3. Check quest completion
        completed_quests = self.quest_system.check_quest_completion(text, signals)
        for quest in completed_quests:
            # Award XP
            metric_result = self.metrics_engine.add_xp(quest.reward_metric, quest.reward_xp)
            result["quests_completed"].append({
                "quest_id": quest.id,
                "reward_xp": quest.reward_xp,
                "reward_metric": quest.reward_metric
            })

        # 4. Check story triggers
        story_id = self.narrative_engine.evaluate_story_trigger(
            text,
            self.metrics_engine.get_metrics_state(),
            []
        )
        if story_id:
            result["stories_triggered"].append(story_id)

        # 5. Check activity-based triggers
        activities = self.activity_logger.analyze_activity_mentions(text)
        for activity in activities:
            if activity["activity"] == "minecraft":
                self.activity_logger.detect_minecraft_activity(text)
            elif activity["activity"] == "watching":
                self.activity_logger.detect_watching_activity(text)

        # 6. Check stat-based achievements
        metrics_state = self.metrics_engine.get_metrics_state()
        stat_achievements = self.achievement_tracker.check_stat_achievements(metrics_state)
        for ach in stat_achievements:
            result["achievements_unlocked"].append(ach["achievement_id"])

        # 7. Check message-based achievements (hidden triggers)
        message_achievements = self.achievement_tracker.check_message_achievements(text)
        for ach in message_achievements:
            result["achievements_unlocked"].append(ach["achievement_id"])

        # 8. Check for unlock cascades
        for achievement_id in result["achievements_unlocked"]:
            # Get unlocks tied to this achievement
            to_unlock = self.unlock_tracker.check_unlock_requirements(
                achievement_id,
                metrics_state,
                result["achievements_unlocked"]
            )
            for unlock_id in to_unlock:
                unlock_result = self.unlock_tracker.trigger_unlock(unlock_id)
                if unlock_result:
                    result["unlocks_triggered"].append(unlock_id)

        # 9. Collect notifications
        result["notifications"].extend(self.achievement_tracker.get_pending_notifications())
        result["notifications"].extend(self.unlock_tracker.get_pending_notifications())
        result["notifications"].extend(self.narrative_engine.get_pending_notifications())
        result["notifications"].extend(self.activity_logger.get_pending_notifications())

        self.pending_notifications.extend(result["notifications"])

        # 10. Save if needed
        self.save_if_needed()

        return result

    def _analyze_message(self, text: str) -> Dict[str, Any]:
        """Basic message analysis (extract signals)"""
        # This should be replaced with actual NLP analysis from personality.py
        signals = {
            "sentiment": self._estimate_sentiment(text),
            "self_disclosure": self._estimate_self_disclosure(text),
            "question_asked": "?" in text,
            "text_length": len(text),
            "emotional_depth": self._estimate_emotional_depth(text)
        }
        return signals

    def _estimate_sentiment(self, text: str) -> float:
        """Rough sentiment estimation (-1 to 1)"""
        positive_words = ["dobrze", "wspaniale", "kocham", "szczęśliwy", "wesoły", "fajnie"]
        negative_words = ["smutno", "źle", "straszne", "nienawidzę", "martwi", "zły"]

        text_lower = text.lower()
        positive_count = sum(1 for w in positive_words if w in text_lower)
        negative_count = sum(1 for w in negative_words if w in text_lower)

        return (positive_count - negative_count) / max(1, positive_count + negative_count)

    def _estimate_self_disclosure(self, text: str) -> float:
        """Rough self-disclosure estimation (0-1)"""
        disclosure_words = ["czuję", "myślę", "boje", "chcę", "marzę", "potrzebuję"]
        text_lower = text.lower()
        disclosure_count = sum(1 for w in disclosure_words if w in text_lower)
        # Normalize
        return min(disclosure_count * 0.15, 1.0)

    def _estimate_emotional_depth(self, text: str) -> float:
        """Rough emotional depth estimation (0-1)"""
        # Longer messages with emotional words
        if len(text) < 20:
            return 0.0
        depth = min(len(text) / 200, 1.0)
        depth *= (0.5 + self._estimate_sentiment(text) * 0.5)  # Boost for emotional messages
        return min(depth, 1.0)

    def get_daily_quests(self) -> List[Dict[str, Any]]:
        """Get today's quest set"""
        return self.quest_system.get_active_quests()

    def get_progression_state(self) -> Dict[str, Any]:
        """Get full progression state for dashboard"""
        return {
            "profile": self.profile_manager.get_profile().to_dict() if self.profile_manager.get_profile() else None,
            "metrics": self.metrics_engine.get_metrics_state(),
            "quests": self.quest_system.get_active_quests(),
            "achievements": {
                "unlocked": self.achievement_tracker.get_unlocked_achievements(),
                "progress": self.achievement_tracker.get_achievements_progress()
            },
            "unlocks": {
                "active": self.unlock_tracker.get_active_unlocks(),
                "available": self.unlock_tracker.get_available_unlocks()
            },
            "narrative": self.narrative_engine.get_story_context(),
            "seasonal": {
                "active_events": self.seasonal_executor.check_active_events()
            }
        }

    def get_pending_notifications(self) -> List[Dict[str, Any]]:
        """Get and clear pending notifications"""
        notifications = self.pending_notifications
        self.pending_notifications = []
        return notifications

    def save_if_needed(self) -> None:
        """Save state if save interval exceeded"""
        now = datetime.utcnow().timestamp()
        if now - self.last_save_ts > self.save_interval_sec:
            self.save_all()

    def save_all(self) -> bool:
        """Save all subsystem states"""
        try:
            self.profile_manager.save_profile()
            self._save_json(
                "data/user_memory/metrics_state.json",
                self.metrics_engine.save_to_dict()
            )
            self.quest_system.save_quests()
            self.achievement_tracker.save_achievements()
            self.unlock_tracker.save_state()
            self.narrative_engine.save_state()
            self.activity_logger.save_log()
            self.seasonal_executor.save_state()
            self.last_save_ts = datetime.utcnow().timestamp()
            return True
        except Exception as e:
            print(f"Error saving progression state: {e}")
            return False

    def _load_json(self, path: str, default: Any = None) -> Any:
        """Load JSON file"""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default or {}

    def _save_json(self, path: str, data: Any) -> None:
        """Save JSON file"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
