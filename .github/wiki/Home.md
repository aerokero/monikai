# 🎮 MonikAI - Complete Project Wiki

Welcome to the MonikAI wiki! Here you'll find everything you need to know about the architecture, structure, and operation of this project.

## 📋 Table of Contents

1. **[System Overview](https://github.com/yourusername/monikai/wiki/Home)** ← You are here
2. **[Architecture](https://github.com/yourusername/monikai/wiki/Architecture)** - How everything connects
3. **[Backend](https://github.com/yourusername/monikai/wiki/Backend)** - Python documentation
4. **[Frontend](https://github.com/yourusername/monikai/wiki/Frontend)** - React documentation
5. **[Integrations](https://github.com/yourusername/monikai/wiki/Integrations)** - Minecraft, Spotify, Telegram, etc.
6. **[Progression System](https://github.com/yourusername/monikai/wiki/Progression-System)** - Achievements, quests, personality
7. **[API Reference](https://github.com/yourusername/monikai/wiki/API-Reference)** - All endpoints
8. **[Setup & Installation](https://github.com/yourusername/monikai/wiki/Setup)** - How to run the project
9. **[Development Guide](https://github.com/yourusername/monikai/wiki/Development)** - How to contribute
10. **[Troubleshooting](https://github.com/yourusername/monikai/wiki/Troubleshooting)** - Problem solving

---

## 🚀 Quick Start

### What is MonikAI?

**MonikAI** is an advanced AI system with personality, built around the Gemini 2.5 Live API. It combines:

- 🎙️ **Conversational AI** - Natural voice/text conversations
- 💫 **Dynamic Personality** - Mood, affection, energy changing over time
- 🎯 **Progression System** - 9 connected systems (relationships, quests, achievements, unlocks, narrative)
- 🎮 **Game Integrations** - Minecraft bot with autonomy
- 🎵 **Media Integrations** - Spotify awareness, Telegram bridge
- 🏠 **Smart Home** - Control TP-Link devices
- 📝 **Advanced Memory** - JSONL + SQLite FTS for episodic memories
- 🚀 **Multi-Platform** - Desktop (Electron), Web, Telegram

### Key Features

| Feature | Description |
|---------|-------------|
| **Personality System** | Dynamic personality state (mood, affection, energy, comfort, synergy, intimacy) |
| **Progression Track** | 9 systems: profile, metrics, quests, achievements, unlocks, narrative, activities, briefing, seasonal |
| **Memory Engine** | Episodic memory with FTS indexing in SQLite, organized into pages and topics |
| **Real-time Communication** | Socket.IO WebSocket for instant audio/text output |
| **Tool Ecosystem** | Web automation, skills system, external service integrations |
| **Autonomous Agents** | Minecraft bot, Spotify, Telegram, Kasa smart home |
| **Local-First** | Entire operation offline, optional cloud integrations |

---

## 🏗️ Technology Stack

```
┌─────────────────────────────────────────────────┐
│         ELECTRON DESKTOP APP (React 18 + Vite)  │
│  - Socket.IO client                             │
│  - MediaPipe (face auth, gestures)              │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│   PYTHON BACKEND (FastAPI + Socket.IO Server)   │
│  - Gemini 2.5 Live API                          │
│  - AI engines (personality, memory, etc.)       │
│  - Tool execution                               │
│  - Service integrations                         │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│   NODE.JS MINECRAFT BOT (Optional subprocess)   │
│  - Mineflayer for Minecraft automation          │
└─────────────────────────────────────────────────┘
```

**Frontend Stack:**
- React 18.2, Vite 7.3, Socket.IO, Tailwind CSS, Framer Motion, MediaPipe

**Backend Stack:**
- Python 3.10+, FastAPI, Uvicorn, Socket.IO-Python
- Google Gemini 2.5 API (native audio), PyAudio, OpenCV, Playwright, SQLite

**Desktop:**
- Electron 40.1, electron-builder

**Mobile Bridge:**
- Telegram Bot API

---

## 📁 Folder Structure

```
monikai/
├── backend/
│   ├── core/              # Server, AI engine, session manager
│   ├── ai/                # 9 progression engines, memory, personality
│   ├── agents/            # External service managers
│   ├── integrations/      # Minecraft, Spotify, Telegram
│   ├── state/             # State tracking
│   ├── tools/             # Tool definitions
│   ├── audio/             # Audio I/O
│   └── data/              # User data, sessions, memory
│
├── frontend/
│   └── src/
│       ├── components/    # React components
│       ├── contexts/      # Context providers
│       ├── hooks/         # Custom hooks
│       ├── layout/        # Layout components
│       ├── styles/        # Global styles
│       └── config/        # Configuration
│
├── scripts/               # Migration, setup scripts
├── skills/                # Integration skills
├── .github/wiki/          # Wiki documentation (YOU ARE HERE)
│
└── package.json, requirements.txt, vite.config.js, etc.
```

---

## 🔄 How Everything Works

### 1. Start Conversation
```
User speaks → Frontend captures audio → Socket.IO sends to Backend
```

### 2. AI Processing
```
Backend routes to Gemini 2.5 Live API → Streaming response received
```

### 3. Personality Observation
```
Personality engine analyzes message → Progression system observes
→ RelationshipMetrics +XP
→ QuestSystem checks completion
→ AchievementTracker triggers unlocks
→ NarrativeEngine checks story milestones
```

### 4. Tool Execution
```
If tool requested → Execute (web automation, skills, integrations)
```

### 5. Send Response
```
Audio response → Socket.IO back to Frontend
State changes → HTTP updates for progression
Notifications → For achievements/quests
```

---

## 📊 Key Components

| Component | Location | Description |
|-----------|----------|-------------|
| **Gemini Live Loop** | `backend/core/monikai.py` | Main AI engine |
| **Personality Engine** | `backend/ai/personality.py` | Personality state management |
| **Progression Coordinator** | `backend/ai/integrated_progression_system.py` | Coordinator of 9 systems |
| **Memory Storage** | `backend/ai/memory_engine.py` | JSONL + SQLite FTS |
| **Session Manager** | `backend/core/session_manager.py` | Conversation persistence |
| **FastAPI Server** | `backend/core/server.py` | REST API + WebSocket hub |
| **Frontend Audio** | `src/components/ChatModule.jsx` | Conversation interface |
| **Minecraft Agent** | `backend/agents/minecraft_agent.py` | Bot manager |
| **Spotify Manager** | `backend/agents/spotify_manager.py` | OAuth + API |
| **Telegram Bot** | `backend/agents/telegram_bot.py` | Mobile bridge |

---

## 💾 Data Persistence

Everything is stored locally in the `data/` folder:

```
data/
├── sessions/              # Conversation logs (JSONL)
├── user_memory/           # Profile, metrics, achievements
├── memory/                # Episodic memory entries
├── quests/                # Quest templates
├── achievements/          # Achievement definitions
├── stories/               # Narrative sequences
├── unlocks/               # Content unlock requirements
└── seasonal_events/       # Holiday/calendar events
```

---

## 🎯 Next Steps

- **Setup**: Go to [Setup & Installation](https://github.com/yourusername/monikai/wiki/Setup) to run the project
- **Understand Architecture**: Read [Architecture Guide](https://github.com/yourusername/monikai/wiki/Architecture)
- **Contributing**: Go to [Development Guide](https://github.com/yourusername/monikai/wiki/Development)
- **Issues**: Check [Troubleshooting](https://github.com/yourusername/monikai/wiki/Troubleshooting)

---

## 📞 Support

If something is unclear or you need more information, open a [GitHub Issue](https://github.com/yourusername/monikai/issues) or review this wiki more carefully.

**Last Updated**: April 2026
