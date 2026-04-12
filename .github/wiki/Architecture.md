# 🏗️ MonikAI Architecture

Document describing the overall architecture of the MonikAI system.

## 3-Layer Overview

MonikAI uses a **3-layer architecture with multiple runtime environments**:

```
┌──────────────────────────────────────────────────────┐
│        ELECTRON DESKTOP APP (Main UI)                │
│  - React 18 + Vite                                   │
│  - MediaPipe (authentication, gestures)              │
│  - Socket.IO client for real-time communication      │
└──────────────────────────────────────────────────────┘
                     ↓ Socket.IO
┌──────────────────────────────────────────────────────┐
│    PYTHON BACKEND (FastAPI + Socket.IO Server)       │
│  - Main computation layer                            │
│  - Gemini 2.5 Live API integration                   │
│  - All AI/personality engines                        │
│  - External service managers                         │
└──────────────────────────────────────────────────────┘
                   ↓ subprocess IPC
┌──────────────────────────────────────────────────────┐
│    NODE.JS MINECRAFT BOT (Optional subprocess)       │
│  - Mineflayer runtime for Minecraft tasks            │
│  - Independent process managed by Python             │
└──────────────────────────────────────────────────────┘
```

## Layer Components

### Frontend Layer (Electron + React)

**Technology:**
- React 18.2 - UI Framework
- Vite 7.3 - Build tool
- Socket.IO Client - WebSocket communication
- Tailwind CSS - Styling
- Framer Motion - Animations
- MediaPipe Vision - Computer vision

**Responsibility:**
- Render user interface
- Capture audio/video
- Emit WebSocket events
- Display personality state (sprite)
- Manage progression UI
- Handle user interactions

**Key Components:**
- `ChatModule` - Conversation interface
- `PersonalityWindow` - Mood display
- `ProgressionWindow` - Quests, achievements, metrics
- `MinecraftWindow` - Bot control
- `StudyWindow` - OCR materials
- `MemoryPrompt` - Journal interface

### Backend Layer (Python + FastAPI)

**Technology:**
- Python 3.10+
- FastAPI - REST framework
- Uvicorn - ASGI server
- Socket.IO-Python - WebSocket server
- Google Gemini 2.5 - LLM + native audio API
- SQLite - Memory indexing (FTS)

**Responsibility:**
- Manage Gemini Live session
- Observe personality state
- Execute progression systems
- Store/retrieve memory
- Tool management
- External service integration
- User state management

**Main Modules:**
- `monikai.py` - AI engine
- `personality.py` - Personality management
- `memory_engine.py` - Episodic memory
- `integrated_progression_system.py` - System coordinator
- `server.py` - REST API + WebSocket hub
- `session_manager.py` - Session persistence

### Game Agent Layer (Node.js)

**Technology:**
- Node.js
- Mineflayer - Minecraft bot library
- Socket stdio IPC

**Responsibility:**
- Connect to Minecraft server
- Automate tasks
- Track location and inventory
- Report state to backend

---

## Communication Pattern

### Real-Time Conversation Loop

```
1. USER INPUT (Frontend)
   ↓
2. AUDIO CHUNK via Socket.IO
   ↓
3. BACKEND RECEIVES (monikai.py)
   ├─ Send to Gemini 2.5 Live API
   ├─ Stream response Audio
   │
4. PERSONALITY OBSERVATION (personality.py)
   ├─ Analyze message content
   ├─ Extract emotional signals
   ├─ Call progression.observe_message()
   │
5. PROGRESSION PROCESSING (integrated_progression_system.py)
   ├─ RelationshipMetrics: Add XP
   ├─ QuestSystem: Check completion
   ├─ AchievementTracker: Check triggers
   ├─ NarrativeEngine: Story milestones
   ├─ ActivityLogger: Track interests
   ├─ UnlockTracker: Gate content
   │
6. TOOL EXECUTION (if requested)
   ├─ Execute web, skill, or other tool
   ├─ Get results
   │
7. RESPONSE EMISSION (Socket.IO + HTTP)
   ├─ emit('text_output', {...})
   ├─ emit('audio_output', chunks)
   ├─ emit('personality_state', {...})
   ├─ emit('notification', {...})
   │
8. FRONTEND UPDATES
   ├─ Display text response
   ├─ Play audio
   ├─ Update personality sprite
   ├─ Refresh progression metrics
```

### API Endpoints Pattern

**REST Endpoints (HTTP):**
```
GET    /api/progression/profile      - Demographics
GET    /api/progression/metrics      - 4-axis relationship
GET    /api/progression/quests/today - Today's quests
GET    /api/progression/achievements - Unlocked/locked
GET    /api/progression/state        - Full state
POST   /api/progression/action       - Log user action
GET    /spotify/status               - Auth status
GET    /minecraft/state              - Bot status
GET    /study/catalog                - Available resources
```

**WebSocket Events (Socket.IO):**
```
Server → Client:
├─ text_output            - Text response
├─ audio_output          - Audio chunks
├─ voice_activity        - VAD status
├─ personality_state     - Mood changes
├─ notification          - Achievement alert
├─ minecraft_status      - Bot update
└─ reminder              - Time-based alert

Client → Server:
├─ audio_input          - Audio from user
├─ start_session        - Begin conversation
├─ stop_session         - End conversation
├─ tool_approval        - Grant permission
└─ minecraft_connect    - Request bot connection
```

---

## Data Models

### Persist Session

```
data/sessions/
└── 2026-04-12/
    └── sess_20260412_143022_001/
        ├── meta.json          # {timestamp, user_id, mode}
        └── turns.jsonl        # [{role, content, signals}]
```

### User Memory State

```
data/user_memory/
├── profile.json                # Demographics
├── metrics_state.json          # 4-axis progression
├── active_quests.json          # Current quests
├── achievements.json           # Unlocked/locked
├── unlocks_state.json          # Content gates
├── narrative_state.json        # Story progress
├── activity_log.json           # Interests
├── personality_state.json      # Mood variables
└── memory/
    ├── entries.jsonl           # Episodic entries
    └── pages/
        ├── journal/            # Date-organized
        ├── topics/             # By subject
        └── roleplay/           # Character interactions
```

### Configuration

```
data/
├── schemas/                    # JSON schema validators
├── quests/                     # Quest definitions
├── achievements/               # Achievement templates
├── unlocks/                    # Unlock gate rules
├── stories/                    # Narrative sequences
└── seasonal_events/            # Calendar-based events
```

---

## Integrations

### Minecraft Bot

```
Frontend
   ↓ (Socket.IO: minecraft_connect)
Backend (minecraft_agent.py)
   ├─ Spawn Node.js subprocess
   ├─ Connect to Minecraft server
   └─ Listen to bot output
   
Bot Status Flow:
   ↓ (stdout → stdin IPC)
   Backend tracks state (minecraft_state_tracker.py)
   ├─ Location
   ├─ Inventory
   ├─ Players nearby
   └─ Autonomy status
   
   ↓ (Socket.IO: minecraft_status)
   Frontend displays bot window
```

### Spotify Integration

```
OAuth 2.0 Flow:
   User login → Token to data/spotify_tokens.json
   
API Calls:
   GET /spotify/status              # Current playing
   GET /spotify/recommendations    # Mood-based
   
Personality Hook:
   Observe current song → Mood adjustments
```

### Telegram Bot

```
Telegram Message → telegram_bot.py
   ├─ Create TelegramChatSession
   ├─ Init full AudioLoop
   ├─ Process through personality system
   └─ Send response back to Telegram

Features:
   ├─ Commands (/mood, /memory, /remind)
   ├─ Voice messages
   ├─ Text messages
   └─ Allowlist security
```

### Smart Home (Kasa)

```
Backend discovery → Auto-detect TP-Link devices
   
Tool execution:
   turn_on(device_name)
   turn_off(device_name)
   set_brightness(device, level)
   
Voice command integration:
   User voice → Gemini understands request → Execute
```

---

## Architectural Decisions

### 1. Local-First Operation
✅ Everything works offline  
✅ Optional cloud integrations  
✅ User controls data  

### 2. Multi-Platform
✅ Desktop (Electron)  
✅ Web (browsers)  
✅ Mobile (Telegram bridge)  

### 3. Modular Integrations
✅ Each integration (Minecraft, Spotify) is independent  
✅ Failed integrations don't break main system  
✅ Easy to add new integrations  

### 4. State-Driven Personality
✅ All state in JSON (easy to DEBUG)  
✅ Deterministic state changes  
✅ Easy to reset/reload personality  

### 5. Streaming Architecture
✅ Audio streaming (not waiting for full response)  
✅ WebSocket for instant updates  
✅ No UI delays  

---

## Performance Considerations

| Aspect | Optimization |
|--------|---------------|
| **Audio Latency** | WebRTC + buffer optimization |
| **Memory Indexing** | SQLite FTS on episodic entries |
| **State Persistence** | Async write queue |
| **Tool Execution** | Concurrent task executor |
| **UI Rendering** | React Context batching + Framer Motion GPU |

---

## Security

| Layer | Mechanism |
|--------|-----------|
| **Desktop** | MediaPipe face auth (optional) |
| **API** | CORS, rate limiting |
| **Telegram** | Allowlist (whitelist of chat IDs) |
| **Data** | All stored locally in `data/` |
| **Tokens** | OAuth tokens in `data/spotify_tokens.json` |

---

## Scale Considerations

- Single user instance (designed for personal use)
- State file-based (no database needed)
- Threading/async for concurrent operations
- Can run on low-resource systems

---

**Next Read:** [Backend Documentation](./Backend.md) | [Frontend Documentation](./Frontend.md)
