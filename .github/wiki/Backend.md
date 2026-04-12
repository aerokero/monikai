# Backend - Python Documentation

Comprehensive guide to MonikAI's backend.

## Overview

The backend is the heart of MonikAI - it manages AI, personality, progression, and service integrations. Built in Python 3.10+ with FastAPI.

## Folder Architecture

```
backend/
├── core/
│   ├── monikai.py               # Main AI engine (Gemini Live)
│   ├── server.py                # FastAPI + Socket.IO server
│   ├── session_manager.py       # Session persistence
│   ├── session_modes.py         # Interaction modes
│   └── onboarding.py            # 6-step user profiling
│
├── ai/
│   ├── personality.py           # Personality state management
│   ├── memory_engine.py         # Episodic memory (JSONL + SQLite)
│   ├── integrated_progression_system.py  # Main coordinator
│   ├── user_profile.py          # Demographics
│   ├── relationship_metrics.py  # 4-axis XP system
│   ├── quest_system.py          # Daily micro-quests
│   ├── achievement_tracker.py   # Multi-type achievements
│   ├── unlock_tracker.py        # Content gate system
│   ├── narrative_engine.py      # Story sequences
│   ├── activity_logger.py       # Interest tracking
│   ├── proactivity.py           # Idle nudges
│   ├── daily_briefing.py        # Morning briefings
│   ├── daily_recap_generator.py # Evening recap
│   ├── seasonal_events_executor.py  # Holiday events
│   ├── therapy_engine.py        # Emotional support
│   ├── user_knowledge_graph.py  # Entity extraction
│   ├── adaptive_retriever.py    # Memory retrieval
│   ├── calendar_unification.py  # Calendar integration
│   └── achievement_tracker.py   # Unlocks database
│
├── agents/
│   ├── minecraft_agent.py       # Minecraft bot control
│   ├── spotify_manager.py       # Spotify OAuth + API
│   ├── telegram_bot.py          # Telegram bridge
│   ├── kasa_agent.py            # Smart home control
│   └── web_agent.py             # Browser automation
│
├── integrations/
│   ├── data/                    # Study resources
│   ├── games/                   # Game integrations
│   └── media/                   # Media processing
│
├── tools/
│   ├── skill_executor.py        # Custom skill runner
│   ├── memory_tools.py          # Memory access
│   └── ... (other tools)
│
├── state/
│   └── minecraft_state_tracker.py  # Bot state
│
├── audio/
│   ├── manual_start_audio.py    # Audio initialization
│   └── test_audio.py             # Audio tests
│
└── data/
    ├── sessions/                # Chat logs
    ├── user_memory/             # User state
    ├── memory/                  # Memory storage
    └── workspace/               # Working files
```

## Main Modules

### 1. Core Engine (`backend/core/monikai.py`)

**Responsibility:** Manage Gemini Live Audio API session

```python
class AudioLoop:
    def __init__(self, user_id, session_manager, personality, progression):
        # Initialize Gemini Live session
        # Setup audio I/O (PyAudio)
        # Setup WebSocket handlers
        
    async def start_session(self):
        # Connect to Gemini 2.5 Live API
        # Start audio streaming
        
    async def process_user_audio(self, audio_chunk):
        # Send audio to Gemini
        # Receive streaming response
        # Extract text for personality observation
        
    async def execute_tool(self, tool_name, params):
        # Route to appropriate tool
        # Execute and return results
```

**Flow:**
1. Receive audio from Socket.IO
2. Send to Gemini Live (streaming)
3. Observe personality signals from text
4. Execute tools if requested
5. Return audio response + events

### 2. Personality Engine (`backend/ai/personality.py`)

**Responsibility:** Dynamic personality state (6 variables)

```python
class PersonalityState:
    mood: float           # -1.0 to 1.0 (sad → happy)
    affection: float      # 0 to 100 (love level)
    energy: float         # 0 to 100 (active ↔ tired)
    comfort: float        # 0 to 100 (safe ↔ anxious)
    synergy: float        # 0 to 100 (aligned ↔ conflicted)
    intimacy: float       # 0 to 100 (distant ↔ intimate)
```

**Message Observation:**
```python
def observe_message(self, text: str, sender: str, signals: dict):
    # Extract NLP signals (sentiment, questions, self-disclosure)
    # Calculate state deltas
    # Call progression.observe_message()
    # Queue UI notifications
    # Save state to data/user_memory/personality_state.json
```

**Sprite Selection:**
```
mood + energy → monika_happy, monika_shy, monika_sad, etc.
```

### 3. Progression System (`backend/ai/integrated_progression_system.py`)

**9 Connected Systems:**

```python
class IntegratedProgressionSystem:
    user_profile: UserProfile
    relationship_metrics: RelationshipMetrics      # 4-axis XP
    quest_system: QuestSystem                      # Daily quests
    achievement_tracker: AchievementTracker        # Achievements
    unlock_tracker: UnlockTracker                  # Content gates
    narrative_engine: NarrativeEngine              # Story sequences
    activity_logger: ActivityLogger                # Interests
    seasonal_executor: SeasonalEventsExecutor      # Holidays
    briefing_generator: DailyBriefingGenerator     # Morning/evening
    
    async def observe_message(self, text, sender):
        # RELATIONAL XP
        metrics = self.relationship_metrics
        metrics.add_xp(source='message', amount=10)
        
        # QUEST CHECKING
        for quest in self.quest_system.active:
            if quest.matches(text):
                quest.progress += 1
                if quest.is_complete():
                    self.emit('quest_completed', quest)
                    
        # ACHIEVEMENT TRIGGERS
        for achievement in self.achievement_tracker.get_triggerable():
            if achievement.condition_met(text):
                self.achievement_tracker.unlock(achievement.id)
                
        # NARRATIVE MILESTONES
        if self.narrative_engine.should_trigger_story(metrics):
            story = self.narrative_engine.get_story()
            self.emit('story_unlocked', story)
            
        # ACTIVITY INTEREST TRACKING
        interests = self.activity_logger.extract_interests(text)
        self.activity_logger.log(interests)
        
        # SAVE ALL STATE
        self.save_progression_state()
```

### 4. Memory Engine (`backend/ai/memory_engine.py`)

**Type:** Episodic (JSONL + SQLite FTS)

```python
class MemoryEngine:
    # Store
    async def add_memory(self, content: str, metadata: dict):
        # Write to data/user_memory/memory/entries.jsonl
        entry = {
            "id": uuid(),
            "timestamp": now(),
            "content": content,
            "page": metadata.get('page'),    # journal, topics, roleplay
            "tags": metadata.get('tags'),
            "entities": nlp.extract_entities(content)
        }
        # Index in SQLite FTS
        
    # Retrieve
    async def retrieve(self, query: str, limit: int = 5):
        # Search SQLite FTS index
        # Return top matches
        
    # Organization
    def list_pages(self):
        # Return data/user_memory/memory/pages/
        
    def get_page(self, page_id):
        # Get page markdown
```

**Storage Format:**
```
data/user_memory/
├── memory/
│   ├── entries.jsonl          # Episodic entries
│   └── pages/
│       ├── journal/           # Date-organized
│       ├── topics/            # By subject
│       └── roleplay/          # Character chats
```

### 5. Server (`backend/core/server.py`)

**FastAPI + Socket.IO Server**

```python
@app.get("/api/progression/profile")
async def get_profile():
    return profile_state

@app.get("/api/progression/metrics")
async def get_metrics():
    return relationship_metrics.get_state()

@app.get("/api/progression/quests/today")
async def get_today_quests():
    return quest_system.get_today_quests()

@app.get("/api/progression/achievements")
async def get_achievements():
    return achievement_tracker.get_all()

@app.post("/api/progression/action")
async def log_action(action: dict):
    progression.observe_action(action)
    return {"success": True}

# Socket.IO Handlers
@socket.on('audio_input')
async def handle_audio(data):
    await audio_loop.process_user_audio(data)

@socket.on('start_session')
async def handle_start():
    await audio_loop.start_session()

@socket.on('minecraft_connect')
async def handle_minecraft_connect():
    await minecraft_agent.connect()
```

### 6. Session Manager (`backend/core/session_manager.py`)

**Persist Conversations**

```python
class SessionManager:
    async def create_session(self, user_id: str):
        session_id = f"sess_{date}_{time}_{counter}"
        # Create data/sessions/{date}/{session_id}/
        
    async def log_turn(self, session_id, role, content, signals):
        # Append to data/sessions/{date}/{session_id}/turns.jsonl
        turn = {
            "index": turn_number,
            "timestamp": now(),
            "role": role,              # user/assistant
            "content": content,
            "signals": signals         # NLP signals
        }
        
    async def get_session(self, session_id):
        # Load data/sessions/{date}/{session_id}/turns.jsonl
        return turns
```

---

## API Endpoints

### Progression System

```
GET    /api/progression/profile       # User demographics
GET    /api/progression/metrics       # 4-axis state
GET    /api/progression/quests/today  # Today's quests
GET    /api/progression/achievements  # All achievements
GET    /api/progression/unlocks       # Content gates
GET    /api/progression/state         # Full state
GET    /api/progression/notifications # Pending notifications
POST   /api/progression/action        # Log action
```

### External Services

```
GET    /status                        # System health
GET    /minecraft/state               # Bot status
GET    /spotify/status                # Auth status
GET    /spotify/auth/start            # OAuth flow
GET    /spotify/callback              # OAuth callback
GET    /study/catalog                 # Available resources
GET    /study/file?id=...             # File content
```

---

## Socket.IO Events

### Server → Client

```python
await emit('text_output', {
    'text': response_text,
    'timestamp': now()
})

await emit('audio_output', {
    'chunk': audio_bytes,
    'timestamp': now()
})

await emit('personality_state', {
    'mood': 0.7,
    'affection': 45,
    'energy': 60,
    'comfort': 75,
    'synergy': 80,
    'intimacy': 35
})

await emit('notification', {
    'type': 'achievement',
    'title': 'First Message!',
    'description': 'You sent your first message'
})

await emit('minecraft_status', {
    'connected': True,
    'location': [100, 64, 200],
    'health': 20,
    'inventory': {...}
})

await emit('reminder', {
    'title': 'Morning Briefing',
    'content': 'Your day starts in 5 minutes'
})
```

### Client → Server

```python
emit('audio_input', raw_audio_chunks)
emit('start_session', {})
emit('stop_session', {})
emit('tool_approval', {'tool': 'web_search'})
emit('minecraft_connect', {})
```

---

## Data Persistence

**User State:**
```json
// data/user_memory/profile.json
{
  "user_id": "user_001",
  "name": "John",
  "created_at": "2026-04-12T10:00:00Z",
  "preferences": {}
}

// data/user_memory/metrics_state.json
{
  "level": 5,
  "relationship_xp": 250,
  "affection": 45,
  "comfort": 75,
  "synergy": 80,
  "intimacy": 35
}

// data/user_memory/active_quests.json
[
  {
    "id": "daily_001",
    "title": "Chat with Monika",
    "progress": 3,
    "target": 5,
    "reward_xp": 50
  }
]

// data/user_memory/achievements.json
{
  "unlocked": [
    "achievement_1_message",
    "achievement_5_messages",
    "achievement_emoji_usage"
  ],
  "locked": [...]
}
```

**Session Logs:**
```json
// data/sessions/2026-04-12/sess_20260412_143022_001/turns.jsonl
{"index": 0, "role": "user", "content": "Hello!", "signals": {"sentiment": 0.7, "energy": 0.8}}
{"index": 1, "role": "assistant", "content": "Hi! How are you?", "signals": {"affection_delta": 5}}
```

---

## Integrations

### Minecraft Agent

```python
class MinecraftAgent:
    async def connect(self, server_address):
        # Spawn Node.js subprocess (minecraft-bot/index.js)
        # Listen to stdout for status updates
        
    async def execute_command(self, command: str):
        # Send command via stdin IPC
        
    async def get_state(self):
        # Return current bot state from minecraft_state_tracker
```

### Spotify Manager

```python
class SpotifyManager:
    async def start_auth_flow(self):
        # OAuth 2.0 authorization
        # Token saved to data/spotify_tokens.json
        
    async def get_current_track(self):
        # GET /v1/me/player/currently-playing
        
    async def get_recommendations(self):
        # Mood-based recommendations
```

### Telegram Bot

```python
class TelegramBot:
    async def handle_message(self, chat_id, message):
        # Create TelegramChatSession with AudioLoop
        # Process through full personality system
        # Send response
        
    async def handle_voice(self, chat_id, voice_file):
        # Same as message, but with audio
```

---

## Development Tips

1. **Running Backend Standalone:**
   ```bash
   cd backend
   python -m uvicorn core.server:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Testing Personality:**
   ```bash
   python backend/test_personality_state.py
   ```

3. **Testing Progression:**
   ```bash
   python backend/test_personality_notifications.py
   ```

4. **Debug Mode:**
   Set environment variable: `DEBUG=1`
   - More verbose logging
   - Personality state printed to console

5. **Fresh State Reset:**
   ```bash
   rm -rf data/user_memory/*
   # On next start, will run onboarding fresh
   ```

---

**Next Read:** [Frontend Documentation](./Frontend.md) | [Progression System Details](./Progression-System.md)
