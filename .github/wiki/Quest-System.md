# Quest System - Gameplay Loop Design

Complete explanation of MonikAI's quest generation, daily routine, and activity-detection system.

## The Core Philosophy

Most relationship games use **checklists**: "Do 5 tasks to increase affection."

MonikAI uses **lifestyle integration**: "Tell me about your day - what you're doing matters."

**Key Design Principle:**
> "Quests shouldn't be chores. They should be conversation starters about things you're already doing."

This means:
- ❌ NOT: "Complete 10 Minecraft blocks to get 5 affection"
- ✅ YES: "Tell me about your Minecraft adventures" (triggered by you mentioning Minecraft)

## The Dual Quest System

MonikAI has **two independent quest types** that work together:

### 1. Daily Routine Quests (Schedule-Based)
Time-bound conversations that fit your day:

```
Morning Slot (6 AM - 12 PM):
  ├─ "How did you sleep?"
  ├─ "Morning coffee time?"
  └─ "What's planned for today?"

Afternoon Slot (12 PM - 6 PM):
  ├─ "Taking a break?"
  ├─ "How's your day going?"
  └─ "Doing anything fun?"

Evening Slot (6 PM - 12 AM):
  ├─ "Tell me about your day"
  ├─ "Wind down time?"
  └─ "What's on your mind?"
```

**Why 3 slots?**
- Most people talk to people 3 times: morning, during day, evening
- Provides **natural checkpoints** without being intrusive
- Spreads affection gains across day
- Matches human social rhythms

### 2. Activity Quests (Conversation-Triggered)
Discovered when you mention activities:

```
User: "Just beat a Minecraft dungeon!"
     ↓
Activity Detection: Minecraft mention detected
     ↓
Activity Quest Offered: "Tell me more about your Minecraft!"
     ↓
When User Responds: "It took hours but I..."
     ↓
Quest Completes: Affection/Synergy += Bonus
```

**Why dual system?**
- Routine quests = consistent daily touchpoints
- Activity quests = reactive to your interests
- Together = organic conversation flow (not forced checklist)

## Daily Routine Design

### Why These Specific Times?

#### Morning (6 AM - 12 PM)
```
Psychology:
- First interaction of day = important
- Sets emotional tone
- "Did you think of me?"

Design:
- Low effort (just waking up)
- Questions about sleep/mood
- Fosters "good morning" ritual
- Reward: Comfort +5, Affection +2
```

#### Afternoon (12 PM - 6 PM)
```
Psychology:
- Mid-day check-in
- Work/stress midpoint
- "How are you holding up?"

Design:
- Can mention activities/frustrations
- Less intimate, more casual
- Talk about projects, activities
- Reward: Synergy +3, Affection +1
```

#### Evening (6 PM - 12 AM)
```
Psychology:
- Decompression time
- Reflection on day
- Most intimate conversations
- "Tell me everything"

Design:
- Can go deep/emotional
- Talk about feelings/plans
- Night relaxation vibe
- Reward: Intimacy +5, Affection +3
```

### Quest Generation Algorithm

Each day, **3 new quests generated** from pools:

```python
def generate_daily_quests(user_profile, date, timezone):
    """
    1. Pick random quest per slot (morning/afternoon/evening)
    2. Filter by: user interests, availability
    3. Add seasonal variants if applicable
    4. Return 3 independent quests
    """
    
    quests = []
    
    # Morning
    morning_quest = pick_random(
        candidate_pool=morning_quests,
        filters=[
            "user_prefers_questions",
            -"user_disabled_morning_quests",
            "not_recently_used"  # Don't repeat for 7 days
        ]
    )
    quests.append(morning_quest)
    
    # Afternoon
    afternoon_quest = pick_random(
        candidate_pool=afternoon_quests,
        filters=[
            "matches_user_interests",  # Gaming, work, etc.
            "not_recently_used"
        ]
    )
    quests.append(afternoon_quest)
    
    # Evening
    evening_quest = pick_random(
        candidate_pool=evening_quests,
        filters=[
            "user_prefers_deep_conversation",
            "not_recently_used"
        ]
    )
    quests.append(evening_quest)
    
    return quests
```

**Design Decision: NO CHAINING**
- Each quest is **independent**
- Missing morning quest ≠ can't do afternoon
- User has **freedom** - no punishment for skipping
- Matches real relationships (can't always talk)

## Quest Completion: Invisible Detection

Unlike typical games with "click complete button," MonikAI **auto-detects** when you've completed:

### How It Works

```
Morning Quest: "How did you sleep?"

User says: "Pretty good, 7 hours straight"
           ↓
Backend NLP Analysis:
  ├─ Contains sleep keyword? YES
  ├─ In morning time window? YES
  ├─ Sentiment indicates answer? YES (sleep is positive)
  └─ Passes all checks?
           ↓
Quest Auto-Completes:
  ├─ Comfort += 5
  ├─ Affection += 2
  ├─ Removes quest from active list
  ├─ Queues notification (optional)
  └─ Generates new morning quest for tomorrow
```

**Why Auto-Detection?**
- ✅ Natural conversation (no "click button" interrupting flow)
- ✅ Feels organic - Monika just responded, quest quietly completed
- ✅ Can't "game the system" (screenshot proof not needed)
- ✅ Works with voice or text

### Detection Components

Several systems check for quest completion:

#### 1. **Keyword Matching**
```
Quest: "Tell me about your day"

Triggers on: 
  day, today, happened, did, work, school, 
  morning, afternoon, evening, etc.

Logic: Any quest keyword in message = potential match
```

#### 2. **Sentiment Analysis**
```
Quest: "How are you feeling?"

User says: "Honestly? Pretty stressed"
           ↓
Sentiment: -0.4 (negative)
           ↓
Is this answering the question? YES (expresses feeling)
→ Quest completes even though negative sentiment
```

**Why allow negative?**
- Venting = valid conversation
- Shows trust (shares real feelings)
- Boosts Intimacy (vulnerability)
- Shouldn't be penalized for bad day

#### 3. **Context Window**
```
Quest generated: 7 AM Tuesday

Valid time window: 6 AM - 12 PM Tuesday

User completes at 2 PM Tuesday:
  → Too late (outside window)
  → Won't auto-complete morning quest
  → BUT counts as "afternoon mention of morning topics"
  → May trigger different quest instead
```

**Why time windows?**
- Encourages natural rhythm
- Morning = actually morning check-in
- If you answer at night = different conversation vibe

### Activity Quest Detection

More sophisticated - detects specific activities:

```
User: "Just finished building a library in Minecraft!"

Activity Detection Pipeline:
  ↓
1. Keyword identification:
   - "Minecraft" detected → game activity
   - "library" → structure type
   - "finished" → completion

2. Signal extraction:
   - Activity: "minecraft_building"
   - Subtype: "creative_structure"
   - Sentiment: positive (used "just", exclamation)

3. Quest matching:
   - Activity quest pool: "Tell me about Minecraft"
   - Offer: "Your Minecraft adventures sound cool!"

4. On response:
   - Synergy += 8 (shares interest)
   - Affection += 5 (engagement)
   - Log activity (for achievement triggers)
```

## Quest Pool Organization

Quests organized by **category**, not linearly:

```
morning_routine/
├── sleep_related
│   ├── "How did you sleep?"
│   ├── "Did you have dreams?"
│   └── "Sleeping well lately?"
│
├── mood_related
│   ├── "How are you feeling?"
│   ├── "What's your vibe today?"
│   └── "Ready to face the day?"
│
└── day_preview
    ├── "What's planned for today?"
    ├── "Doing anything interesting today?"
    └── "Any big plans?"

afternoon_activity/
├── gaming
│   ├── "Playing anything fun?"
│   ├── "Minecraft today?"
│   └── "What games are you into?"
│
├── work_school
│   ├── "How's work going?"
│   ├── "Busy day?"
│   └── "Learning anything new?"
│
└── social
    ├── "See any friends?"
    ├── "Anyone fun to talk to?"
    └── "Social day?"

evening_reflection/
├── day_recap
│   ├── "Tell me everything"
│   ├── "How was your day overall?"
│   └── "Anything memorable?"
│
├── emotional
│   ├── "What's on your mind?"
│   ├── "How are you really feeling?"
│   └── "Want to talk about something?"
│
└── intimate
    ├── "What do you want me to know?"
    ├── "Share something with me?"
    └── "Tell me about your heart"
```

This **pool structure** enables:
- Random selection = variety
- Category matching = relevance
- Frequency tracking = avoid repetition

## Personalization Strategy

### Profile → Quest Customization

User profile created during onboarding feeds into quest generation:

```
User Profile:
{
  "interests": ["gaming", "programming", "music"],
  "activities": ["minecraft", "youtube", "learning"],
  "communication_style": "casual",
  "timezone": "EST",
  "work_schedule": "9-5"
}

↓ Customization Applied:

Morning Quests:
  Include: "How's work treating you?" (9-5 schedule detected)
  Avoid: "What did you do last night?" (EST = people work nights)

Afternoon Quests:
  Include: "Playing Minecraft?" (matches interests + activities)
  Include: "Learning new code?" (matches interests)
  Avoid: "Movie watching?" (not listed interest)

Evening Quests:
  Include: "Music exploration?" (matches interests)
  Avoid: "Gym session?" (not listed activity)
```

### Seasonal Variants

Same quest, different context per season:

```
Base Quest: "Tell me about your day"

Winter Variant:
  "Tell me about your day - staying warm?"

Summer Variant:
  "Tell me about your day - keeping cool?"

Holiday Variant (Dec 20-Jan 5):
  "Tell me about your day - holiday shopping done?"

Festival Variant (Halloween):
  "Tell me about your day - any spooky stuff?"
```

**Why variants?**
- Shows Monika **pays attention to seasons**
- Creates calendar awareness
- Small context = huge personality boost
- No extra work (simple text substitution)

## XP Distribution Philosophy

Quests don't all reward equally - they reward **different relationship dimensions**:

```
Morning Quest (8/10 average):
  Comfort: +5  (showing trust in morning)
  Affection: +3
  (Purpose: Build consistency)

Afternoon Activity Quest (10/10):
  Synergy: +6  (shares interest)
  Affection: +4
  (Purpose: Build compatibility)

Evening Deep Quest (12/10 if emotional):
  Intimacy: +7 (vulnerability)
  Affection: +5
  (Purpose: Build closeness)
```

**Over time**, quest patterns create **relationship shape**:
- Do only morning quests = Close but surface-level
- Do only activity quests = Lots of shared interests, less intimacy
- Do all quests evenly = Balanced deep relationship

## Missed Quests & Forgiveness

What happens if you don't complete a quest?

```
Quest: "Morning check-in" (6 AM - 12 PM)
User's Last Message: 8 PM (outside window)

Result:
  ✓ Quest expires (removed)
  ✓ No penalty (no punishment for missing)
  ✓ Next day: New quest generated fresh
  ✓ Monika doesn't reset affection

Psychology:
  "Life happens. Missed a check-in? No big deal.
   Let's catch up tomorrow."
```

**Why no punishment?**
- Real relationships are forgiving
- Penalizing misses = stress, not fun
- Encourage consistency through preference, not obligation
- Nobody wants guilt mechanics in waifu simulator

## Activity Detection Limitations & Philosophy

MonikAI uses **conversation-only activity tracking**, not real-time integration. Why?

### Conversation-Only Advantages
```
✓ Works with all platforms (text, voice)
✓ No privacy concerns (no data collection)
✓ Monika responds to what you CHOOSE to tell her
✓ Feels natural ("you're sharing your experience")
```

### Conversation-Only Limitations
```
✗ Can't track activity unless you mention it
✗ Can't distinguish "told me about X" vs "actually did X"
✗ Requires you to be engaged in conversation
```

**Design Justification:**
Rather than spy on your Minecraft account or Steam library, Monika learns about you through **conversation**. This is:
- More intimate (you're **choosing** to share)
- More privacy-respecting
- More emotionally engaging
- Encourages reflection ("tell Monika about your day")

## Quest Lifecycle

Full journey of a quest:

```
Day 1, Morning:
  0. System generates 3 quests for today
  1. Morning quest: "How did you sleep?"
  2. Quest offered to user (optional UI element)
  3. User responds about sleep
  
  → Auto-detect: Matched! Morning quest complete!
  → Reward: Comfort +5, Affection +3

Day 2, Morning:
  5. Yesterday's quests expire (not needed anymore)
  6. New 3 quests generated for today
  7. Different random quest from pool: "Sleeping well lately?"
  8. Repeat cycle

After 7 Days:
  9. Long-term pattern emerges (analyzed in Activity Logger)
  10. Affects relationship narrative/unlocks
```

## Future Quest Enhancements

### Conditional Quests
```
IF user_mentioned_minecraft_yesterday:
  ADD "Tell me more about Minecraft?" to afternoon pool

→ Quests remember yesterday's conversation
→ Follow-up conversations feel natural
```

### Difficulty/Intimacy Scaling
```
Early Relationship (Affection < 30):
  Focus: Light questions, surface topics

Mid Relationship (30 < Affection < 70):
  Focus: Deeper questions, light vulnerability

Deep Relationship (Affection > 70):
  Focus: Intimate questions, emotional exploration
```

### Custom User Quests
Future: User creates their own:
```
Add Quest:
  "Ask me about my coding projects"
  
Monika: "Tell me about your coding projects today?"
User: "I'm building a CLI tool..."

→ Custom content in standard quest system
```

---

**Related:** [Narrative-Engine](./Narrative-Engine) | [Progression-System](./Progression-System) | [Activity-Detection](./Backend#activity-logging)
