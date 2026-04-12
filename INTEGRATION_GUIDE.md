"""
INTEGRATION GUIDE - How to wire the new progression system
"""

# ============================================================================
# STEP 1: In personality.py - at the top level (in MonikAI class or similar)
# ============================================================================

# Add to imports:
from backend.ai.integrated_progression_system import IntegratedProgressionSystem

# In __init__:
class MonikAI:
    def __init__(self, user_id="default"):
        # ... existing init code ...
        self.progression = IntegratedProgressionSystem(user_id)
        self.progression.initialize_or_load()

    # Hook into message observation:
    def observe_message(self, sender: str, text: str):
        """
        Existing method - modify to integrate progression system
        """
        # Existing code...
        # ... analyze text, etc ...

        # NEW: Process through progression system
        progression_result = self.progression.observe_message(text, sender)

        # Use these results:
        # - progression_result["metrics_updated"]
        # - progression_result["quests_completed"]
        # - progression_result["achievements_unlocked"]
        # - progression_result["unlocks_triggered"]
        # - progression_result["stories_triggered"]
        # - progression_result["notifications"]

        # Queue notifications to frontend
        for notif in progression_result["notifications"]:
            self._queue_notification(notif)

        # Trigger story if needed
        for story_id in progression_result["stories_triggered"]:
            self._trigger_story(story_id)

        # Continue with existing personality code...


# ============================================================================
# STEP 2: In server.py - register new endpoints
# ============================================================================

# Add to imports:
from backend.core.progression_endpoints import create_progression_endpoints

# In your Flask app setup (in create_app function or similar):
def create_app():
    app = Flask(__name__)
    # ... existing setup ...

    # Register progression endpoints
    progression_bp = create_progression_endpoints(app.monikai.progression)
    app.register_blueprint(progression_bp)

    return app

# Now endpoints are available at /api/progression/*


# ============================================================================
# STEP 3: Frontend integration points
# ============================================================================

# New API endpoints available:

# GET /api/progression/profile
# Returns: user profile (name, birthday, interests, etc.)

# GET /api/progression/metrics
# Returns: {affection, comfort, synergy, intimacy, streak_days, progress_towards_next}

# GET /api/progression/quests/today
# Returns: list of quests for today (morning/afternoon/evening)

# POST /api/progression/quests/<quest_id>/complete
# Mark quest as complete

# GET /api/progression/achievements
# Returns: {unlocked: [...], locked: [...], progress: {...}}

# GET /api/progression/unlocks
# Returns: {active: [...], available: [...]}

# GET /api/progression/narrative/context
# Returns: story history, flags, calendar events

# GET /api/progression/seasonal/events
# Returns: currently active seasonal events

# GET /api/progression/notifications
# Returns: pending notifications

# GET /api/progression/state
# Returns: complete progression state (for dashboard)

# POST /api/progression/onboarding/start
# Start onboarding flow

# POST /api/progression/onboarding/response
# Answer onboarding question


# ============================================================================
# STEP 4: WebSocket events (optional - for real-time updates)
# ============================================================================

# When progression event fires, broadcast to frontend:
@socketio.on('progression_update')
def on_progression_update(data):
    """
    Example: after message -> quest completes -> achievement unlocks
    Frontend receives: {
        'type': 'achievement_unlocked',
        'achievement_id': 'affection_50',
        'title': 'Significant Bond',
        'xp_rewards': {'affection': 0, ...},
        'unlocks_triggered': ['romantic_activities']
    }
    """
    emit('progression_event', data, broadcast=True)


# ============================================================================
# STEP 5: Frontend Component Structure (React example)
# ============================================================================

"""
Components to create:

1. <ProgressionDashboard />
   - Shows Profile, Metrics, Quests, Achievements, Unlocks
   - Pulls from /api/progression/state

2. <RelationshipMetrics />
   - 4 bars: affection, comfort, synergy, intimacy
   - Shows progress to next milestone
   - Updates from WebSocket events

3. <DailyQuests />
   - Morning / Afternoon / Evening tabs
   - Quest cards with descriptions + rewards
   - POST to /api/progression/quests/<id>/complete

4. <AchievementsList />
   - Grid/tree of unlocked and locked achievements
   - Shows rarity, requirements, unlock date

5. <UnlockTimeline />
   - Timeline of unlocked features
   - Shows story + unlock connections

6. <Calendar />
   - Highlights active seasonal events
   - Shows memorable dates (first_deep_talk, minecraft_home_built, etc.)

7. <OnboardingFlow />
   - Used once on first run
   - POST to /api/progression/onboarding/start
   - Loop: display prompt -> get input -> POST response

8. <NotificationCenter />
   - Real-time notifications  
   - Quest complete, Achievement unlocked, etc.
   - Pulls from /api/progression/notifications or WebSocket
"""


# ============================================================================
# STEP 6: Data Flow Example
# ============================================================================

"""
User sends message to AI:

1. personality.py observe_message(text)
   ↓
2. progression.observe_message(text)
   - analyze_message(text) → extract signals
   - metrics_engine.add_xp(...) → update metrics
   - quest_system.check_quest_completion(text) → complete quests
   - achievement_tracker.check_stat_achievements() → unlock achievements
   - unlock_tracker.trigger_unlocks() → cascade unlocks
   - narrative_engine.evaluate_story_trigger() → fire stories
   - Returns: {metrics_updated, quests_completed, achievements_unlocked, ...}
   ↓
3. personality.py queues notifications from progression_result
   ↓
4. WebSocket broadcasts to frontend:
   {
     "type": "metric_update",
     "metric": "affection",
     "new_value": 55,
     "old_value": 50
   }
   {
     "type": "quest_complete",
     "quest_id": "...",
     "reward_xp": 10
   }
   {
     "type": "achievement_unlock",
     "achievement_id": "affection_50",
     "title": "Significant Bond"
   }
   ↓
5. Frontend updates dashboards:
   - Metrics bar animates +5 affection
   - Quest disappears from list
   - Achievement appears with animation
   - Unlock tree updates
"""


# ============================================================================
# STEP 7: Initial Setup / Testing
# ============================================================================

"""
1. First user load:
   - Start progression system
   - Initialize → onboarding flow starts
   - POST /api/progression/onboarding/start
   - Loop until completed
   - Profile saved, first quests generated

2. Daily cycle:
   - Each morning (based on timezone):
   - seasonal_executor.check_active_events()
   - quest_system.generate_daily_quests(timezone, activities)
   - Push daily_quests_ready notification

3. Ongoing:
   - Each message: progression.observe_message()
   - Track all metrics, achievements, unlocks
   - Auto-save every 6 seconds
   - Emit real-time updates to frontend
"""


# ============================================================================
# STEP 8: Configuration
# ============================================================================

"""
All configuration is data-driven via JSON:

1. Quest templates: data/quests/quest_catalog.json
   - Add new quest types without code changes
   - Define conditions, rewards, slots

2. Achievements: data/achievements/achievements_catalog.json
   - Add achievements: stat-based, hidden, milestones
   - Define unlock conditions

3. Unlocks: data/unlocks/unlocks_catalog.json
   - Features that unlock progressively
   - Define prerequisites (achievements, metrics)

4. Stories: data/stories/stories_catalog.json
   - Multi-turn conversations
   - Define triggers, requirements, branches

5. Seasonal Events: data/seasonal_events/events_calendar.json
   - Calendar-tied events (Valentine's, birthdays, etc.)
   - Define special quests, achievements, story overrides
"""
