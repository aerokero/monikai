# API Reference

Complete REST API and WebSocket event reference.

## REST API Endpoints

### Base URL
```
http://localhost:8000
```

### Progression System

#### Get User Profile
```
GET /api/progression/profile
Response:
{
  "user_id": "user_001",
  "name": "John",
  "level": 10,
  "created_at": "2026-04-12T10:00:00Z"
}
```

#### Get Relationship Metrics
```
GET /api/progression/metrics
Response:
{
  "level": 10,
  "total_xp": 500,
  "affection": 65,
  "comfort": 80,
  "synergy": 75,
  "intimacy": 40
}
```

#### Get Today's Quests
```
GET /api/progression/quests/today
Response:
[
  {
    "id": "daily_001",
    "title": "Morning Greeting",
    "progress": 0,
    "target": 1,
    "reward_xp": 50
  }
]
```

#### Get Achievements
```
GET /api/progression/achievements
Query parameters:
  ?status=unlocked   # unlocked, locked, or all

Response:
{
  "unlocked": [
    {"id": "ach_1_msg", "title": "First Steps", "unlocked_at": "..."}
  ],
  "locked": [
    {"id": "ach_5_msg", "title": "Getting Familiar", "requirement": "5 messages"}
  ]
}
```

#### Get Content Unlocks
```
GET /api/progression/unlocks
Response:
{
  "unlocked": [
    {"id": "dialogue_morning", "title": "Morning Dialogue Pack"},
    {"id": "feature_memory", "title": "Memory Feature"}
  ],
  "locked": [
    {"id": "dialogue_date", "title": "Date Dialogue", "requirement": "Level 15"}
  ]
}
```

#### Get Full Progression State
```
GET /api/progression/state
Response:
{
  "profile": {...},
  "metrics": {...},
  "active_quests": [...],
  "achievements": {...},
  "unlocks": {...},
  "notifications": [...]
}
```

#### Get Pending Notifications
```
GET /api/progression/notifications
Response:
[
  {
    "id": "notif_001",
    "type": "achievement",
    "title": "First Steps Achieved!",
    "content": "You sent your first message",
    "timestamp": "2026-04-12T14:30:00Z"
  }
]
```

#### Log User Action
```
POST /api/progression/action
Body:
{
  "action_type": "quest_completed",
  "quest_id": "daily_001",
  "timestamp": "2026-04-12T14:35:00Z"
}

Response:
{
  "success": true,
  "message": "Action logged",
  "progression_update": {...}
}
```

---

### External Services

#### System Health
```
GET /status
Response:
{
  "backend": "running",
  "database": "connected",
  "services": {
    "spotify": "connected",
    "minecraft": "disconnected",
    "telegram": "running"
  }
}
```

#### Minecraft Bot Status
```
GET /minecraft/state
Response:
{
  "connected": true,
  "location": {
    "x": 100.5,
    "y": 64,
    "z": 200.3
  },
  "health": 20,
  "food": 20,
  "inventory_count": 47
}
```

#### Spotify Status
```
GET /spotify/status
Response:
{
  "authenticated": true,
  "token_expires_in": 3400,
  "current_track": {
    "name": "Song Name",
    "artist": "Artist",
    "album": "Album",
    "progress_ms": 120000,
    "duration_ms": 300000
  }
}
```

#### Start Spotify OAuth
```
GET /spotify/auth/start
Redirects to Spotify OAuth URL
```

#### Spotify OAuth Callback
```
GET /spotify/callback?code=...&state=...
Handles OAuth callback, stores token, redirects to frontend
```

#### Study Resources Catalog
```
GET /study/catalog
Response:
[
  {
    "id": "study_001",
    "title": "Python Tutorial",
    "type": "pdf",
    "size": "2.5 MB",
    "uploaded_at": "2026-04-10"
  }
]
```

#### Get Study File
```
GET /study/file?id=study_001
Returns file content
```

---

## WebSocket Events (Socket.IO)

### Connection
```javascript
const socket = io('http://localhost:8000', {
  transports: ['websocket', 'polling'],
  reconnection: true,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
  reconnectionAttempts: 5
});
```

### Server → Client Events

#### text_output
```javascript
socket.on('text_output', (data) => {
  console.log(data.text);     // Response text
  console.log(data.timestamp); // When response was sent
});
```

#### audio_output
```javascript
socket.on('audio_output', (data) => {
  playAudio(data.chunk);      // Audio bytes
  // Called multiple times for streaming
});
```

#### voice_activity
```javascript
socket.on('voice_activity', (data) => {
  console.log(data.is_active); // boolean
  console.log(data.confidence); // 0-1
});
```

#### personality_state
```javascript
socket.on('personality_state', (state) => {
  console.log({
    mood: 0.7,                  // -1 to 1
    affection: 45,              // 0 to 100
    energy: 60,                 // 0 to 100
    comfort: 75,                // 0 to 100
    synergy: 80,                // 0 to 100
    intimacy: 35                // 0 to 100
  });
});
```

#### notification
```javascript
socket.on('notification', (notif) => {
  console.log({
    type: 'achievement',        // achievement, quest, content_unlock
    title: 'First Steps!',
    description: 'You sent your first message',
    icon: '🏆',
    timestamp: '2026-04-12T14:30:00Z'
  });
});
```

#### minecraft_status
```javascript
socket.on('minecraft_status', (status) => {
  console.log({
    connected: true,
    location: { x, y, z },
    health: 20,
    inventory: {...}
  });
});
```

#### reminder
```javascript
socket.on('reminder', (reminder) => {
  console.log({
    type: 'morning_briefing',   // or other reminder types
    title: 'Good Morning!',
    content: 'Summary of today...'
  });
});
```

### Client → Server Events

#### audio_input
```javascript
socket.emit('audio_input', audioChunkBuffer);
// Call multiple times with consecutive audio chunks
```

#### start_session
```javascript
socket.emit('start_session', {
  mode: 'normal'    // or 'proactive', 'study', etc.
});
```

#### stop_session
```javascript
socket.emit('stop_session', {});
```

#### tool_approval
```javascript
socket.emit('tool_approval', {
  tool: 'web_search',
  granted: true
});
```

#### minecraft_connect
```javascript
socket.emit('minecraft_connect', {
  server: 'localhost:25565',
  username: 'MonikAI'
});
```

---

## Response Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK - Request successful |
| 201 | Created - Resource created |
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Authentication required |
| 404 | Not Found - Endpoint doesn't exist |
| 500 | Server Error - Backend error |
| 503 | Service Unavailable - Backend offline |

---

## Error Responses

All errors return JSON:
```json
{
  "error": "error_code",
  "message": "Human readable error message",
  "details": {}
}
```

Example:
```json
{
  "error": "invalid_quest_id",
  "message": "Quest with ID 'invalid_123' not found",
  "details": {
    "quest_id": "invalid_123",
    "available_quests": ["daily_001", "daily_002"]
  }
}
```

---

## Rate Limiting

REST endpoints rate-limited to **100 requests/minute** per IP.

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1712943600
```

---

## Authentication

Currently no authentication required (local system). 
Future updates will add JWT token support.

---

**Next Read:** [Setup & Installation](./Setup.md) | [Development Guide](./Development.md)
