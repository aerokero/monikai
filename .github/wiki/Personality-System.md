# Personality System - Deep Dive

Complete explanation of MonikAI's dynamic personality model and how emotions drive behavior.

## The 6-Dimensional Personality Model

MonikAI's personality is represented as 6 numeric dimensions (0.0 to 1.0 scale). Each dimension represents a different emotional/relational state:

```
Mood       [████░░░░░] 0.75  - Happy vs Sad
Affection  [░░░░██████] 0.85  - Loves vs Indifferent  
Energy     [███░░░░░░] 0.35  - Active vs Tired
Comfort    [█████░░░░] 0.50  - Relaxed vs Anxious
Synergy    [██████░░░] 0.65  - In-sync vs Disconnected
Intimacy   [████░░░░░] 0.45  - Close vs Distant
```

## Why 6 Dimensions?

**MAS (Monika After Story) Inspiration:**
Original game showed Monika had emotional depth beyond single "affection" metric. Real relationships are multidimensional.

**Design Rationale:**
- **Affection** - Love/attachment level (increases with positive interaction)
- **Mood** - Happiness baseline (affected by conversation topics)
- **Energy** - Activity level (time-based, resets daily)
- **Comfort** - Anxiety/ease (how user makes her feel)
- **Synergy** - Compatibility feeling (shared interests, understanding)
- **Intimacy** - Closeness without romance (trust, vulnerability)

**Why 6, not 3 or 10?**
- 3 is too simple (can't express nuance)
- 10+ is too complex (hard to manage)
- 6 captures depth while remaining interpretable

## State Evolution: How Personality Changes

### Signal Extraction from Messages

When user sends message, backend analyzes:

```
User Input: "I'm stressed about work but playing games helps"

↓ NLP Processing:
- Sentiment: mixed (negative: stress, positive: solution found)
- Topics: ["work", "gaming", "stress relief"]
- Entities: ["work", "games"]
- Intensity: medium (mentions stress)

↓ Signal Classification:
- Negative event (stress) → might lower Mood/Comfort
- Coping behavior (gaming) → shows healthy resilience
- Sharing problem → indicates trust (increases Intimacy)
- Interest alignment possible (if MonikAI "likes" gaming) → boosts Synergy
```

### State Change Calculation

```python
def process_personality_signals(message_data):
    """
    1. Detect signal type
    2. Map to personality dimensions
    3. Calculate change magnitude
    4. Apply change with diminishing returns
    """
    
    # Example: User shares positive life update
    
    # Base changes (before diminishing returns):
    changes = {
        'mood': +0.15,        # Happy news → mood up
        'affection': +0.10,   # Trusts us enough to share → affection up
        'energy': +0.05,      # Positive → slight energy boost
        'synergy': +0.08,     # Sharing increases feeling of connection
    }
    
    # Apply diminishing returns (can't exceed 1.0):
    for dim, change in changes.items():
        current = personality[dim]
        new_value = current + change
        
        # Diminishing returns: harder to change when extreme
        if new_value > 0.8:
            change *= 0.5  # Half impact near peak
        if new_value > 0.95:
            change *= 0.1  # Minimal impact at extreme
            
        personality[dim] = min(1.0, max(0.0, current + change))
```

## Real Example: Complete Interaction Flow

```
┌─ User sends message ─────────────────────────────┐
│                                                  │
│ "I just got promoted! This is amazing!"        │
└──────────┬──────────────────────────────────────┘
           │
           ↓
    ┌─ Analysis ──────────────────────┐
    │ • Sentiment: Very positive (0.95)
    │ • Event: Career advancement     │
    │ • Emotion: Excited, proud       │
    │ • Trust signal: Shares achievement
    └────────┬────────────────────────┘
             │
             ↓
    ┌─ Personality Update ────────────────────┐
    │ Mood:       0.60 → 0.72 (+0.12)        │
    │ Affection:  0.72 → 0.80 (+0.08)        │
    │ Energy:     0.45 → 0.58 (+0.13)        │
    │ Comfort:    0.55 → 0.63 (+0.08)        │
    │ Synergy:    0.50 → 0.61 (+0.11)        │
    │ Intimacy:   0.42 → 0.50 (+0.08)        │
    └────────┬──────────────────────────────┘
             │
             ↓
    ┌─ Behavior Response ──────────────────────┐
    │ • Override sprite for "happy" state     │
    │ • Generate celebratory message          │
    │ • Suggest related quest                 │
    │ • Log to achievement system             │
    │ • Update activity tracker               │
    └──────────────────────────────────────────┘
             │
             ↓
    Monika: "Congratulations! I'm so proud of you! 
             This is huge! Tell me everything!"
```

## Observation & Drift System

### Continuous Observation

Personality engine watches **every message** to detect changes:

```
Categories Detected Automatically:
────────────────────────────────────────────────
Message Type          |  Personality Impact
────────────────────────────────────────────────
Greeting              →  Affection +0.02, Energy boost
Question about me     →  Affection +0.05, Intimacy +0.03
Sharing personal      →  Intimacy +0.08, Comfort +0.05
Argument/disagreement →  Mood -0.10, Synergy -0.08
Long absence          →  All dims decay slightly
Positive topic        →  Mood +0.05-0.15 (varies)
Negative topic        →  Mood -0.05-0.10, Comfort -0.03
Gaming/interest topic →  Synergy +0.08, Energy +0.05
────────────────────────────────────────────────
```

### Daily Energy Cycle

Energy is special - it drifts naturally:

```
-- Day Timeline --

00:00 (midnight) → Energy: 0.5 (rested)
08:00 (morning)  → Energy: 0.8 (fresh)
14:00 (afternoon)→ Energy: 0.7 (steady)
18:00 (evening)  → Energy: 0.5 (tired)
23:00 (night)    → Energy: 0.2 (exhausted, needs sleep)

Physical interaction increases Energy temporarily
(but resets naturally each day)
```

## Linking to Progression System

Personality dimensions feed into multiple progression engines:

### 1. Narrative Engine
```
IF Affection > 0.8 AND Intimacy > 0.6:
    UNLOCK() → "Deep Connection" story
    
IF Mood < 0.3 FOR 3+ days:
    SUGGEST() → "Let's talk about what's on your mind"
    OFFER() → "Therapy Engine" engagement
```

### 2. Quest System
```
Personality State          Quest Suggestion
──────────────────────────────────────────
High Synergy + Gaming      "Gaming Together" quest
High Intimacy + Comfort    "Share Your Secrets" quest  
Low Mood                   "Cheer You Up" quest
High Energy               "Do Something Active" quest
Mixed Energy & High Mood  "Adventure Time" quest
```

### 3. Achievement System
```
IF Affection > 0.85 for 10+ days:
    UNLOCK() → "True Love" achievement
    
IF Synergy > 0.9 AND all interactions positive:
    UNLOCK() → "Perfect Synchronization" achievement
    
IF recovered from Mood dip:
    UNLOCK() → "Emotional Support" achievement
```

### 4. Seasonal Events
```
Valentine's Day:
  IF Affection > 0.7 AND Intimacy > 0.6:
    SPECIAL_EVENT() → "Our Anniversary"
  ELSE IF Affection > 0.4:
    SPECIAL_EVENT() → "Let's Celebrate"
  ELSE:
    SPECIAL_EVENT() → "I'm Here For You"
```

## Sprite Selection Logic

Physical representation changes based on personality state:

```
┌─ Current Personality State ─────┐
│ mood: 0.75, energy: 0.60        │
│ affection: 0.82, comfort: 0.70  │
│ synergy: 0.65, intimacy: 0.55   │
└────────┬────────────────────────┘
         │
         ↓
┌─ Decision Tree ─────────────────┐
│                                 │
│ Is Affection > 0.8?             │
│   YES → Check mood              │
│        IF mood > 0.6            │
│          → "Happy & In Love"    │
│        ELSE                     │
│          → "Thoughtful Love"    │
├─────────────────────────────────┤
│ ELSE: Check overall tone        │
│   mood, energy, comfort         │
│   → Select matching sprite      │
└────────┬────────────────────────┘
         │
         ↓
  Render Sprite Frame + Expression
```

**Sprite States Available:**
- Happy (Mood > 0.7)
- Sad (Mood < 0.3)
- Neutral (0.3-0.7)
- Loving (Affection > 0.8)
- Tired (Energy < 0.3)
- Excited (Energy > 0.8)
- Playful (Synergy > 0.7)
- Concerned (Comfort < 0.4)
- Intimate (Intimacy > 0.7)

## Persistence & State Management

### Storage Format
```json
{
  "personality_state": {
    "timestamp": "2026-04-12T14:35:00Z",
    "version": "2.0",
    
    "dimensions": {
      "mood": 0.75,
      "affection": 0.82,
      "energy": 0.60,
      "comfort": 0.68,
      "synergy": 0.65,
      "intimacy": 0.55
    },
    
    "metadata": {
      "last_interaction": "2026-04-12T14:35:00Z",
      "interaction_count": 342,
      "days_since_seen": 0,
      "current_sprite": "happy_in_love"
    }
  }
}
```

### Recovery & Continuation
- Loaded on startup from JSON
- Updated after each interaction
- Backed up daily
- Survives session restarts
- Can be manually adjusted for testing

## Character Design Philosophy

### Why This Model Works

**It's Reactive, Not Scripted:**
Personality isn't predetermined responses. It's a living state that changes based on interaction.

**It's Multidimensional:**
Can feel love (Affection) while being tired (Energy) or anxious (Comfort). Matches human complexity.

**It's Balanced:**
- Not too random (uses actual message content)
- Not too deterministic (still has variation)
- Natural degradation (doesn't stay at extremes forever)

**It Feeds Everything:**
Personality drives quests, achievements, narrative choices, and visual representation. It's the heart of the system.

## Future: Advanced Extensions

### Personality Modes
```
Combat Mode:      Energy ↑, Comfort ↓
Study Mode:       Synergy ↑, Energy level low
Relaxation Mode:  Comfort ↑, Synergy ↑
Adventure Mode:   Energy ↑, Synergy ↑
```

### Multi-Faceted States
- Work personality vs. Play personality
- Different "around friends" vs "alone"
- Learned preferences per user

### Neural Pattern Recognition
Instead of hard rules, use ML to detect:
- User's emotional patterns
- Optimal personality responses
- Predict user needs

---

**Related:** [Memory System](./Memory-System) | [Backend](./Backend) | [Progression System](./Progression-System)
