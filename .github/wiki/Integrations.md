# Integrations - External Services

Guide to all external service integrations in MonikAI.

## Overview

MonikAI integrates with multiple external services to extend functionality:

- **Minecraft** - Game bot with autonomy
- **Spotify** - Music awareness and recommendations
- **Telegram** - Mobile chat bridge
- **Kasa** - Smart home device control
- **Web** - Browser automation

## Minecraft Integration

### Architecture

```
Frontend (web interface)
     ↓ Socket.IO: minecraft_connect
Backend (minecraft_agent.py)
     ├─ Spawn Node.js subprocess
     ├─ Run minecraft-bot/index.js
     └─ Listen to bot output
     
Bot (Mineflayer)
     ├─ Connect to server
     ├─ Execute actions
     └─ Report state via stdout/stdin
```

### Features

- **Autonomous Exploration** - Bot explores world automatically
- **Resource Gathering** - Collects resources in background
- **Location Tracking** - Real-time location display
- **Inventory Management** - Monitor items collected
- **Player Detection** - See nearby players
- **Command Execution** - Send commands from UI

### Configuration

```python
# backend/agents/minecraft_agent.py
class MinecraftAgent:
    async def connect(self, server_address="localhost", port=25565):
        # Spawn subprocess
        self.process = subprocess.Popen([
            'node', 'minecraft-bot/index.js',
            '--server', server_address,
            '--port', str(port),
            '--username', self.username
        ])
```

### State Tracking

Tracked in `backend/state/minecraft_state_tracker.py`:

```json
{
  "connected": true,
  "player_location": {
    "x": 100.5,
    "y": 64,
    "z": 200.3
  },
  "health": 20,
  "food": 20,
  "inventory": {
    "diamond_ore": 5,
    "wood": 32,
    "stone": 64
  },
  "nearby_players": ["Steve", "Alex"],
  "autonomous_state": "gathering_wood"
}
```

## Spotify Integration

### OAuth 2.0 Flow

```
1. User clicks "Connect Spotify" button
2. Frontend opens Spotify auth flow (opens browser)
3. User approves permissions
4. Redirect to http://localhost:8000/spotify/callback
5. Backend stores token in data/spotify_tokens.json
6. Frontend updates status
```

### Token Storage

```json
// data/spotify_tokens.json
{
  "access_token": "BQDx...",
  "refresh_token": "AQC...",
  "expires_in": 3600,
  "expires_at": 1712943600
}
```

### Data Access

```python
# backend/agents/spotify_manager.py
class SpotifyManager:
    async def get_current_track(self):
        # GET /v1/me/player/currently-playing
        return {
            "name": "Song Name",
            "artist": "Artist Name",
            "album": "Album Name",
            "progress_ms": 120000,
            "duration_ms": 300000
        }
        
    async def get_recent_tracks(self, limit=50):
        # GET /v1/me/player/recently-played
        return tracks
        
    async def get_recommendations(self, seed_artists, mood):
        # Mood-based recommendations
```

### Personality Hook

```python
# backend/ai/personality.py
async def observe_spotify():
    current = await spotify.get_current_track()
    
    # Emotional analysis
    if current['mood'] == 'sad':
        personality.mood -= 0.1
    elif current['mood'] == 'happy':
        personality.mood += 0.1
```

## Telegram Integration

### Bot Setup

1. Create bot via @BotFather on Telegram
2. Get bot token
3. Configure in backend

```python
# backend/agents/telegram_bot.py
class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.allowed_chats = [123456789]  # Whitelist
```

### Command Handling

```
/mood              - Show current mood
/memory [query]    - Search memory
/remind [time]     - Set reminder
/profile           - Show profile
/quests            - List active quests
/achievements      - List achievements
```

### Message Processing

Each Telegram message creates independent session:

```python
async def handle_message(self, chat_id, message):
    # Create session
    session = TelegramChatSession(self.user_id, chat_id)
    
    # Process through full personality system
    audio_loop = AudioLoop(
        session_manager=self.session_manager,
        personality=self.personality,
        progression=self.progression
    )
    
    # Get response
    response = await audio_loop.process_text(message)
    
    # Send back to Telegram
    await self.send_message(chat_id, response)
```

### Voice Message Support

```python
async def handle_voice(self, chat_id, voice_file):
    # Download voice file
    audio_data = await download_file(voice_file)
    
    # Transcribe with Google Speech-to-Text
    text = await transcribe(audio_data)
    
    # Process as text message
    response = await self.process_text(chat_id, text)
```

## Kasa Smart Home

### Device Discovery

```python
# backend/agents/kasa_agent.py
class KasaAgent:
    async def discover_devices(self, network="192.168.1.0/24"):
        # Scan network for TP-Link devices
        devices = await Discover.discover_single(address, port=9999)
        return devices
```

### Supported Devices

- Smart plugs (turn on/off)
- Smart bulbs (on/off, brightness, color)
- Smart switches
- Smart strips

### Control Methods

```python
async def turn_on(self, device_name: str):
    device = self.devices[device_name]
    await device.turn_on()
    
async def turn_off(self, device_name: str):
    device = self.devices[device_name]
    await device.turn_off()
    
async def set_brightness(self, device_name: str, brightness: int):
    device = self.devices[device_name]
    await device.brightness = brightness
```

### Voice Integration

```python
# User: "Turn on the lights"
# Gemini understands and calls:
await kasa.turn_on("bedroom_light")
```

## Web Agent - Browser Automation

### Technology

Uses Playwright for GUI automation:
- Chrome/Chromium browser
- DOM access
- Screenshot capture
- Form filling
- Navigation

### Capabilities

```python
# backend/agents/web_agent.py
class WebAgent:
    async def navigate_to(self, url: str):
        await self.page.goto(url)
        
    async def fill_form(self, selectors: dict, values: dict):
        for field, selector in selectors.items():
            await self.page.fill(selector, values[field])
            
    async def take_screenshot(self):
        return await self.page.screenshot()
        
    async def get_page_text(self):
        return await self.page.inner_text('body')
```

### Example Tasks

- Search Google
- Fill out forms
- Extract data from websites
- Monitor website changes
- Capture screenshots

---

## Adding New Integrations

### Template

```python
# backend/agents/new_service_agent.py

class NewServiceAgent:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = NewServiceClient(api_key)
        
    async def authenticate(self):
        # Setup auth
        pass
        
    async def execute_action(self, action: str, params: dict):
        # Execute service action
        pass
        
    async def get_state(self):
        # Get current state for UI
        pass
```

### Integration Points

1. Add agent to `backend/agents/`
2. Import in `backend/core/server.py`
3. Initialize in `server.py:create_app()`
4. Add WebSocket handlers in `server.py`
5. Add REST endpoints if needed
6. Add to progression system observations if relevant

### Testing

```bash
python backend/agents/new_service_agent.py
```

---

**Next Read:** [Progression System](./Progression-System.md) | [API Reference](./API-Reference.md)
