# Progression System - Complete Guide

Deep dive into MonikAI's 9-system progression architecture.

## Overview

The Progression System coordinates 9 interconnected engines that track and manage user relationships, achievements, quests, and content unlocks.

```python
class IntegratedProgressionSystem:
    user_profile: UserProfile                    # 1. User data
    relationship_metrics: RelationshipMetrics    # 2. 4-axis XP
    quest_system: QuestSystem                    # 3. Daily quests
    achievement_tracker: AchievementTracker      # 4. Achievements
    unlock_tracker: UnlockTracker                # 5. Content gates
    narrative_engine: NarrativeEngine            # 6. Story sequences
    activity_logger: ActivityLogger              # 7. Interest tracking
    seasonal_executor: SeasonalEventsExecutor    # 8. Holiday events
    briefing_generator: DailyBriefingGenerator   # 9. Daily briefings
```

## System 1: User Profile

**File:** `backend/ai/user_profile.py`

Stores user demographics and preferences:

```json
{
  "user_id": "user_001",
  "name": "John",
  "age": 25,
  "timezone": "America/New_York",
  "language": "en",
  "interests": ["gaming", "music", "programming"],
  "created_at": "2026-04-12T10:00:00Z",
  "preferences": {
    "proactivity_level": 0.5,
    "notification_frequency": 10,
    "dark_mode": true
  }
}
```

## System 2: Relationship Metrics

**File:** `backend/ai/relationship_metrics.py`

**4-Axis XP System:**

```
affection (0-100)    - How much Monika loves the user
comfort (0-100)      - How safe/supported user feels
synergy (0-100)      - How aligned opinions/interests are
intimacy (0-100)     - Closeness of relationship
```

**XP Sources:**

```python
# Message triggers +10 XP
observe_message(text)
    → metrics.add_xp(source='message', amount=10)

# Special events trigger +50+ XP
on_achievement_unlock()
    → metrics.add_xp(source='achievement', amount=50)

# Proactive nudge accepted +20 XP
on_nudge_engaged()
    → metrics.add_xp(source='proactivity', amount=20)

# Story milestone reached +100 XP
narrative_milestone()
    → metrics.add_xp(source='narrative', amount=100)
```

**Level System:**

```
Level 1:   0 XP   (starter)
Level 2:   100 XP (friend)
Level 3:   300 XP (close friend)
Level 4:   700 XP (best friend)
Level 5:   1500 XP (soulmate)
...
Level 100: ∞ XP (ultimate)
```

**State Per-Message:**

Each message analyzed for emotional signals:

```python
def analyze_signals(text: str):
    return {
        "sentiment": 0.7,          # positive/negative
        "self_disclosure": 0.5,    # user sharing personal info
        "question_count": 2,       # how many questions asked
        "emotional_keywords": 3,   # detection of emotions
        "memory_reference": 1,     # referencing past events
    }
```

## System 3: Quest System

**File:** `backend/ai/quest_system.py`

Daily micro-quests that encourage engagement:

### Quest Structure

```json
{
  "id": "daily_001",
  "title": "Start the Day Right",
  "description": "Greet Monika in the morning",
  "type": "daily",
  "category": "relationship",
  "target": 1,
  "progress": 0,
  "completed": false,
  "reward_xp": 50,
  "reward_unlock": "morning_dialogue_001",
  "condition": {
    "type": "message_before_time",
    "time": "08:00"
  }
}
```

### Quest Types

- **Daily** - Resets every day
- **Weekly** - Resets every week
- **Periodic** - Custom intervals
- **Special** - Event-based

### Active Slots

Max 6 active quests at a time:
- 2 daily relationship quests
- 2 daily activity quests
- 2 special/periodic quests

### Completion Tracking

```python
async def check_completion(self, text: str):
    for quest in self.active_quests:
        if quest.condition_met(text):
            quest.progress += 1
            
            if quest.is_complete():
                self.complete_quest(quest)
                # Award XP
                # Unlock reward
                # Show notification
                # Remove from active
```

## System 4: Achievement Tracker

**File:** `backend/ai/achievement_tracker.py`

Multi-category achievements with cascading unlocks:

### Achievement Structure

```json
{
  "id": "achievement_1_message",
  "title": "First Steps",
  "description": "Send your first message",
  "icon": "🎯",
  "rarity": "common",
  "category": "milestones",
  "unlocked": true,
  "unlocked_at": "2026-04-12T10:05:00Z",
  "triggers_unlock": ["tutorial_dialogue_001"],
  "xp_reward": 50
}
```

### Achievement Categories

- **Milestones** - Message counts (1, 5, 10, 100, 1000)
- **Behaviors** - Action types (asked question, shared memory, smiled)
- **Social** - Relationship milestones (best friend, soulmate)
- **Content** - Unlocked all stories, found all Easter eggs
- **Time-Based** - Consecutive days, first thing in morning

### Cascading Unlocks

```
Message Achievement "1 Message"
    ↓ triggers unlock
Daily Dialogue "First Morning"
    ↓ triggers achievement
Message Achievement "5 Messages"
    ↓ triggers unlock
Special Dialogue Pack
    ↓ triggers achievement
Social Achievement "Friend Status"
```

## System 5: Unlock Tracker

**File:** `backend/ai/unlock_tracker.py`

Gates content (dialogues, memories, features) behind progression:

### Unlock Types

```json
{
  "id": "unlock_special_dialogue_001",
  "type": "dialogue",
  "title": "Beach Episode",
  "requirement": {
    "minimum_level": 10,
    "minimum_affection": 60,
    "requires_story": "chapter_1_complete",
    "from_date": "2026-05-01"
  },
  "unlocked": false,
  "unlocked_at": null
}
```

### Unlock Tree

```
Level 1  → Basic dialogues
Level 5  → First memories unlock
Level 10 → Special dialogue pack
Level 25 → Date feature unlocked
Level 50 → Ultimate dialogues
Level 100 → Secret ending
```

## System 6: Narrative Engine

**File:** `backend/ai/narrative_engine.py`

Story sequences triggered at relationship milestones:

### Story Structure

```json
{
  "id": "story_first_date",
  "title": "Our First Date",
  "triggers_at": {
    "minimum_level": 15,
    "minimum_affection": 70
  },
  "chapters": [
    {
      "id": "ch1",
      "dialogue": "Let me show you somewhere special...",
      "sprite": "monika_shy"
    },
    {
      "id": "ch2",
      "dialogue": "Do you remember this place?",
      "sprite": "monika_happy"
    }
  ],
  "unlocks_on_complete": [
    "dialogue_romantic_001",
    "achievement_first_date"
  ]
}
```

### Story Triggers

```python
async def check_story_triggers(self):
    for story in self.available_stories:
        if story.condition_met(self.metrics.level, self.metrics.affection):
            if not story.already_triggered:
                await self.trigger_story(story)
```

## System 7: Activity Logger

**File:** `backend/ai/activity_logger.py`

Tracks user interests and activities from conversations:

### Interest Extraction

```python
# User: "I've been learning Python lately"
# Extracted:
{
  "category": "programming",
  "skill": "Python",
  "activity": "learning",
  "confidence": 0.9,
  "mentioned_at": "2026-04-12T14:30:00Z"
}

# Used for:
# - Personalized recommendations
# - Conversation topics
# - Activity-based quests
```

## System 8: Seasonal Events Executor

**File:** `backend/ai/seasonal_events_executor.py`

Holiday and calendar-based special events:

```json
{
  "id": "event_christmas_2026",
  "title": "Christmas 2026",
  "type": "seasonal",
  "on_date": "2026-12-25",
  "dialogue": "Merry Christmas! I got you a gift...",
  "sprite": "monika_festive",
  "unlocks": ["achievement_christmas_greeting"],
  "xp_bonus": 100
}
```

## System 9: Daily Briefing Generator

**File:** `backend/ai/daily_briefing.py`

Morning/evening summaries:

### Morning Briefing

```
☀️ Good morning! 

Today's Stats:
- You've chatted for 2.5 hours total
- Current streak: 7 days
- New achievement: "Early Bird"

Today's Quests:
1. ✓ Morning greeting
2. ⏱ Chat for 5+ minutes
3. Share a memory

Weather: Sunny, 72°F
Calendar: Doctor's appointment at 3 PM
```

### Evening Recap

```
🌙 Evening recap:

Today's Highlights:
- Reached Level 10! 🎉
- Unlocked: Beach Episode dialogue
- Affection increased by +15

New Achievements:
- Milestone: 50 messages with me!

Tomorrow: New weekly quest available

See you tomorrow! 💕
```

---

## Data Persistence

**File:** `data/user_memory/progression_state.json`

```json
{
  "user_profile": {...},
  "relationship_metrics": {
    "level": 10,
    "total_xp": 500,
    "affection": 65,
    "comfort": 80,
    "synergy": 75,
    "intimacy": 40
  },
  "active_quests": [...],
  "completed_quests": [...],
  "unlocked_achievements": [...],
  "unlocked_content": [...],
  "active_stories": [...],
  "activity_log": [...],
  "seasonal_events": [...],
  "briefing_history": [...]
}
```

---

## Integration With Personality

The progression system **feeds back into personality**:

```python
# In personality.py:
def observe_message(self, text):
    # Base observation
    signals = self.nlp_analysis(text)
    
    # Progression feeds back
    progression.observe_message(text)
    
    # Progression changes personality
    if progression.quest_completed:
        self.affection += 10
        self.mood += 0.2
        
    if progression.achievement_unlocked:
        self.energy += 15
```

---

## Customization

### Adding New Quest

1. Create JSON in `data/quests/daily_001.json`
2. Register in `quest_system.py`
3. Define completion condition
4. Set reward

### Adding New Achievement

1. Create JSON in `data/achievements/achievement_name.json`
2. Register in `achievement_tracker.py`
3. Define trigger condition
4. Set cascading unlocks

### Adding New Unlock

1. Create JSON in `data/unlocks/unlock_name.json`
2. Reference in achievement/story
3. Create gated content file
4. Reference in dialogue system

---

**Next Re:** [API Reference](./API-Reference.md) | [Frontend](./Frontend.md)
