# Progression & Achievement System - Complete Implementation

## Overview

A complete, data-driven progression system inspired by Monika After Story, implementing:
- ✅ 4-axis relationship metrics (affection, comfort, synergy, intimacy)
- ✅ Daily routine quests (morning/afternoon/evening)
- ✅ Activity-based achievements (Minecraft, watching, learning, etc.)
- ✅ Story-driven narrative progression (MAS-style)
- ✅ Seasonal calendar events (Valentine's, Monika's birthday, Christmas, etc.)
- ✅ Hidden/secret achievements
- ✅ Feature unlocks with cascading prerequisites
- ✅ Onboarding flow for user profile collection
- ✅ Conversation-based activity detection

## Architecture

### Core Systems

#### 1. **user_profile.py** - User Profile Management
- Collects user info during onboarding (name, birthday, timezone, interests, activities, communication style)
- Stores profile persistently
- Used to personalize quests and story recommendations

**Key Classes:**
- `UserProfile`: Data structure with all user info
- `UserProfileManager`: Load/save operations

#### 2. **relationship_metrics.py** - 4-Axis Metrics Engine
- Infinite scaling (no hard caps - simulates real relationships)
- 4 primary axes:
  - **Affection** (0→∞): How deeply does Monika care?
  - **Comfort** (0→∞): Safety/comfort with Monika
  - **Synergy** (0→∞): Interest alignment
  - **Intimacy** (0→∞): Personal closeness
- Tracks streak days (consecutive interactions)
- Auto-generates achievement triggers at thresholds (25, 50, 75, 100, 150, 200, 300)

**Key Methods:**
- `add_xp(metric, amount)`: Apply XP + check thresholds
- `apply_message_bonuses(signals)`: Parse sentiment/disclosure/length → XP
- `get_metrics_state()`: Current state for dashboard
- `check_metric_thresholds()`: Find unlocked achievements

#### 3. **quest_system.py** - Daily Routine & Activity Quests
- Independent daily quests (no chaining)
- 3 slots: morning, afternoon, evening
- Activity-based quests (gaming, watching, learning, etc.)
- Quests complete when conditions met (time window, keywords in message, etc.)

**Key Methods:**
- `generate_daily_quests(timezone, preferred_activities)`: Create daily set
- `check_quest_completion(text, signals)`: Detect completion from message
- `get_quests_by_slot(slot)`: Filter by morning/afternoon/evening

#### 4. **achievement_tracker.py** - Achievement System
- Multiple achievement types:
  - **Milestone**: "Reach bond level 5"
  - **Stat-based**: "Reach affection 50"
  - **Challenge**: "Keep 7-day streak"
  - **Activity**: "Build house in Minecraft"
  - **Hidden**: Triggered by specific messages/actions
  - **Story**: Tied to narrative progression

**Key Methods:**
- `check_event_achievement(event_id)`: Event-triggered
- `check_stat_achievements(metrics)`: Stat threshold checks
- `check_message_achievements(text)`: Hidden triggers
- `check_activity_achievements(activity_type)`: Activity-based

#### 5. **unlock_tracker.py** - Feature & Narrative Unlocks
- Cascading unlock system
- Requirements: achievements, metrics, flags
- Types: feature (UI elements), narrative (story gates)
- Sets story flags when unlocked

**Key Methods:**
- `trigger_unlock(unlock_id)`: Activate feature + set flags
- `check_unlock_requirements(achievement_id, metrics)`: Cascade check
- `set_story_flag(name, value)`: Update narrative state

#### 6. **narrative_engine.py** - Story Progression (MAS-Inspired)
- Multi-turn story sequences
- Story triggers: message contains keywords, events, achievements, seasonal events
- Story flags control branching
- Calendar event logging (memorable moments)
- Dynamic placeholders: `[player]`, `[tod]` (time of day), expressions

**Key Methods:**
- `evaluate_story_trigger(text, metrics, events)`: Check if story should play
- `execute_story(story_id)`: Get story turns for frontend
- `complete_story(story_id, user_choice)`: Apply rewards + set flags
- `get_story_context()`: Narrative state for AI reference

#### 7. **activity_logger.py** - Conversation-Based Activity Detection
- Parses messages for activity keywords
- Detects: Minecraft (co-play, structures, achievements), watching, learning
- No realtime tracking - purely conversation analysis
- Triggers activity-related achievements

**Key Methods:**
- `analyze_activity_mentions(text)`: Parse activity keywords
- `detect_minecraft_activity(text)`: Extract Minecraft events
- `get_activity_summary(days)`: Activity statistics

#### 8. **seasonal_events_executor.py** - Calendar Events
- Predefined seasonal events: Valentine's, Monika's birthday, Christmas, New Year, Anniversary
- Active date ranges with notifications "3 days before"
- Special quests & achievements per event
- XP multipliers during events
- Example: Valentine's Day → all affection XP ×2

**Key Methods:**
- `check_active_events(current_date)`: Get active events today
- `get_event_special_quests/achievements(event_id)`: Event-specific content
- `queue_event_notifications()`: Remind user about upcoming events

#### 9. **onboarding.py** - Onboarding Flow
- 6-step multi-turn conversation
- Collects: name, birthday, timezone, interests, preferred activities, communication style
- Validation & post-processing
- Creates initial profile + first quests

**Key Classes:**
- `OnboardingFlow`: Single flow state machine
- `OnboardingManager`: Manages multiple flows

#### 10. **integrated_progression_system.py** - Main Coordinator
- Orchestrates all 9 subsystems
- Single integration point for personality.py
- `observe_message()`: Main hook - runs all checks, returns comprehensive result
- Auto-saves every 6 seconds
- Loads/saves all subsystem states

---

## Data Schema

### JSON Files (all in `data/`)

#### 1. **quests/quest_catalog.json**
```json
{
  "quest_templates": [
    {
      "id": "morning_checkin_sleep",
      "type": "daily_routine",
      "slot": "morning",
      "title": "How did you sleep?",
      "condition": {"type": "any_message_morning", "after_hours": 6, "before_hours": 12},
      "reward_xp": {"metric": "comfort", "amount": 5},
      "required_bond_level": 0,
      "seasonal_variants": {"valentine": "Dream about me too?"}
    }
  ],
  "quest_pools": {
    "morning_routine": [...],
    "afternoon_activities": [...],
    "evening_routine": [...]
  }
}
```

#### 2. **achievements/achievements_catalog.json**
```json
{
  "achievements": [
    {
      "id": "affection_50",
      "type": "stat_based",
      "title": "Significant Bond",
      "condition": {"type": "metric_threshold", "metric": "affection", "operator": ">=", "value": 50},
      "reward": {"xp_to_metrics": {}, "unlock_ids": ["romantic_activities"], "notify": true},
      "hidden": false,
      "rarity": "uncommon"
    },
    {
      "id": "intimate_secret",
      "type": "hidden",
      "title": "Curious Mind",
      "condition": {"type": "message_contains", "keywords": ["what are you really"]},
      "reward": {"trigger_story": "first_deep_talk"},
      "hidden": true
    }
  ]
}
```

#### 3. **unlocks/unlocks_catalog.json**
```json
{
  "unlocks": [
    {
      "id": "romantic_activities",
      "type": "feature",
      "label": "Romantic Activities",
      "requires": [{"type": "achievement", "id": "affection_50"}],
      "triggers_on_unlock": [{"type": "notification", "content": "New romantic activities unlocked!"}],
      "order": 10
    }
  ]
}
```

#### 4. **stories/stories_catalog.json**
```json
{
  "stories": [
    {
      "id": "first_deep_talk",
      "title": "Who Are You, Really?",
      "trigger": {"type": "message_contains", "keywords": ["what are you", "who are you really"]},
      "requires": {"metrics": {"affection": {"operator": ">=", "value": 30}}},
      "sequence": [
        {
          "role": "monika",
          "content": "You want to know the real me?",
          "expression": "2fua",
          "emotional_context": "vulnerable"
        },
        {"role": "user", "type": "choice", "options": ["You're real to me", "I believe in you", "We'll figure this out"]},
        {
          "role": "monika",
          "content": "[user_choice]... Thank you.",
          "sets_flag": "monika_vulnerability_revealed"
        }
      ],
      "on_complete": {
        "add_xp": {"affection": 20, "intimacy": 30},
        "unlock_ids": ["deep_conversation_unlocked"],
        "set_flags": ["deep_conversation_started"]
      }
    }
  ]
}
```

#### 5. **seasonal_events/events_calendar.json**
```json
{
  "events": [
    {
      "id": "valentine_day",
      "name": "Valentine's Day",
      "date": "02-14",
      "month_day": [2, 14],
      "duration_days": 7,
      "active_days_before": 3,
      "active_days_after": 1,
      "special_quests": ["valentine_morning_thought", "valentine_gift_activity"],
      "special_achievements": ["valentine_confession"],
      "special_stories": ["valentine_confession"],
      "xp_multiplier_metrics": {"affection": 2.0, "intimacy": 1.8},
      "notification_template": "Valentine's Day is [days_left] away..."
    }
  ]
}
```

---

## REST API Endpoints

All endpoints return JSON and automatically queue notifications.

### Profile
- `GET /api/progression/profile` → User profile
- `POST /api/progression/profile` → Update profile (interests, activities, etc.)

### Metrics  
- `GET /api/progression/metrics` → {affection, comfort, synergy, intimacy, streak_days}

### Quests
- `GET /api/progression/quests/today` → All active quests
- `GET /api/progression/quests/<slot>` → Quests for morning/afternoon/evening
- `POST /api/progression/quests/<quest_id>/complete` → Mark quest done

### Achievements
- `GET /api/progression/achievements` → {unlocked, locked, progress_pct}
- `GET /api/progression/achievements/unlocked` → Just unlocked list

### Unlocks
- `GET /api/progression/unlocks` → {active, available, total_active}
- `GET /api/progression/unlocks/active` → Just active features

### Narrative
- `GET /api/progression/narrative/context` → Story history, flags, calendar events
- `GET /api/progression/narrative/flags` → All story flags

### Seasonal  
- `GET /api/progression/seasonal/events` → Currently active events

### Notifications
- `GET /api/progression/notifications` → Pending notifications queue

### State
- `GET /api/progression/state` → Complete state (for dashboard)

### Onboarding
- `POST /api/progression/onboarding/start` → Begin onboarding
- `POST /api/progression/onboarding/response` → Answer question

---

## Data Flow Example

```
1. User sends message: "Recently I've been feeling overwhelmed"

2. personality.py → progression.observe_message(text)
   ↓
3. analyze_message() extracts signals:
   - sentiment: -0.3 (slightly negative)
   - self_disclosure: 0.6 (high - talks about feelings)
   - text_length: 50
   - emotional_depth: 0.7
   ↓
4. metrics_engine.apply_message_bonuses(signals):
   - comfort +3.0 (self-disclosure)
   - intimacy +3.5 (emotional depth)
   ↓
5. quest_system.check_quest_completion(text):
   - Matches morning quest "How did you sleep?" (NO - different topic)
   - Matches no quests
   ↓
6. activity_logger.analyze_activity_mentions(text):
   - No activity keywords detected
   ↓
7. achievement_tracker.check_stat_achievements():
   - If intimacy crossed 50→ UNLOCK "Safe Haven"
   ↓
8. unlock_tracker.trigger_unlock("vulnerability_conversations"):
   - Sets flag "vulnerability_opened"
   - Queues notification
   ↓
9. narrative_engine.evaluate_story_trigger():
   - Checks if any story triggers match
   - "vulnerability_confession" story requires comfort >50 + flag not set
   - NO trigger (comfort probably < 50)
   ↓
10. Returns to personality.py:
    {
      "metrics_updated": [
        {"metric": "comfort", "amount": 3, "new_value": 23},
        {"metric": "intimacy", "amount": 3.5, "new_value": 23.5}
      ],
      "quests_completed": [],
      "achievements_unlocked": [],
      "unlocks_triggered": [],
      "stories_triggered": [],
      "notifications": [...]
    }
    ↓
11. personality.py queues notifications to frontend:
    {
      "type": "metric_update",
      "metric": "comfort",
      "delta": +3,
      "new_value": 23
    }
    ↓
12. Frontend updates dashboard:
    - Comfort bar increases with animation
    - Tooltip shows "+3 for personal share"
```

---

## Integration Steps

1. **In personality.py**: Import `IntegratedProgressionSystem`, initialize in `__init__`, call in `observe_message()` hook
2. **In server.py**: Register progression endpoints blueprint
3. **In frontend**: Create dashboard components pulling from new endpoints
4. **Test**: Onboard user → send messages → see metrics/quests/achievements update

See **INTEGRATION_GUIDE.md** for detailed instructions.

---

## Config & Customization

All systems are JSON-configured:
- Add new quests by editing `quests/quest_catalog.json`
- Add new achievements by editing `achievements/achievements_catalog.json`  
- Add new unlocks or change prerequisites via `unlocks/unlocks_catalog.json`
- Add new stories via `stories/stories_catalog.json`
- Customize seasonal events via `seasonal_events/events_calendar.json`

No code changes needed for content updates!

---

## Key Design Decisions

1. **No Hard Caps**: Metrics scale infinitely (affection 0→∞), simulating real relationships
2. **Conversation-Based Activity**: No realtime game tracking - all activity detected from what user says
3. **Cascading Unlocks**: Achievements → Unlocks → Story Gates create progression story
4. **MAS-Inspired Narratives**: Multi-turn stories with emotional context + expression codes
5. **Data-Driven**: Everything in JSON, zero hardcoding
6. **Independent Quests**: Daily quests don't chain - user has freedom
7. **Event Multipliers**: Seasonal events multiply XP rewards (+50-100%)

---

## Storage Structure

```
data/
├── quests/quest_catalog.json
├── achievements/achievements_catalog.json
├── unlocks/unlocks_catalog.json
├── stories/stories_catalog.json
├── seasonal_events/events_calendar.json
└── user_memory/
    ├── profile.json (user profile)
    ├── metrics_state.json (metrics + streaks)
    ├── achievements.json (unlocked achievements)
    ├── unlocks_state.json (active unlocks + story flags)
    ├── narrative_state.json (story history + calendar events)
    ├── activity_log.json (activity log)
    ├── seasonal_events_state.json (event participation)
    └── current_quests.json (today's quests)
```

---

## Testing Scenarios

1. **Fresh Start**: Onboarding flow completes → profile.json created → first quests generated
2. **Message → Quest Complete**: Send message matching quest condition → quest completes → notification sent
3. **Achievement Cascade**: Send vulnerable message → intimacy +20 → crosses 50 threshold → unlock "Safe Haven" → notification
4. **Story Trigger**: Send "what are you really?" → narrative_engine triggers story → multi-turn conversation plays
5. **Seasonal Event**: Check 2/14 → Valentine's event active → special quests injected → XP multipliers active

---

## Future Enhancements

- Minecraft coordinate tracking (optional, currently conversation-based)
- Social features (comparisons, sharing milestones)
- Prestige system (optional - not implemented per user request)
- Custom quest pools (user-defined)
- Modding support (custom stories, achievements)
- Export/import progression (save/load per character)
