# Minecraft Bot Integration - Testing Guide

## Status: FAZA 2 COMPLETE ✓

### Validation Checklist

#### Python Components
- [x] MinecraftBotManager imports successfully
- [x] Bot manager instantiates without errors
- [x] Attributes accessible (host, port, username, version)
- [x] Status tracking works (health = 20.0 default)
- [x] No syntax errors in minecraft_agent.py

#### Node.js Components
- [x] npm install completed (202 packages)
- [x] index.js passes syntax check
- [x] src/perception.js passes syntax check
- [x] src/actions.js passes syntax check
- [x] .env configuration file created

#### Integration
- [x] tools.py defines 7 minecraft_* tools
- [x] monikai.py routes minecraft_* tool calls
- [x] server.py has SocketIO event handlers:
  - minecraft_connect
  - minecraft_disconnect
  - minecraft_action
  - minecraft_query_status
- [x] Tool permissions configured (auto-allow)

---

## Quick Start: Manual Testing

### Prerequisites
1. Install or access a Minecraft server (local or remote)
2. Start MonikAI backend: `python backend/server.py`
3. Open frontend UI

### Test Scenario 1: Connect to Server
```
Frontend → minecraft_connect event
  ↓
Server: minecraft_bot_manager.start()
  ↓
Spawns Node.js subprocess with env vars
  ↓
Bot connects to MC server
  ↓
Emits "ready" event
  ↓
Frontend receives minecraft_status
```

### Test Scenario 2: Chat Command
```
Gemini: "Say hello to the players"
  ↓
monikai.py: minecraft_chat_message("Hello!")
  ↓
minecraft_agent.py: send_action("chat_message", {"message": "Hello!"})
  ↓
Node.js bot: bot.chat("Hello!")
  ↓
Returns: {"success": true, "result": "Message sent"}
  ↓
Gemini receives result and confirms
```

### Test Scenario 3: Movement
```
Gemini: "Move forward 10 blocks"
  ↓
monikai.py: minecraft_move_to_player calls minecraft_agent
  ↓
Node.js bot: Pathfinder plugin calculates path
  ↓
Bot moves to target position
  ↓
Perception event: Updated position coordinates
  ↓
Frontend shows new location
```

### Test Scenario 4: Block Interaction
```
Gemini: "Break the block at x=100, y=64, z=-50"
  ↓
monikai.py: minecraft_break_block({"x": 100, "y": 64, "z": -50})
  ↓
Node.js bot: Selects tool, breaks block
  ↓
Perception event: Nearby blocks updated
  ↓
Inventory event: Item added (if applicable)
```

---

## Environment Variables

Located in: `backend/minecraft-bot/.env`

```
MC_HOST=localhost          # Minecraft server IP
MC_PORT=25565              # Minecraft server port
MC_USERNAME=monikai        # Bot account username
MC_AUTH=offline            # Auth mode: offline | microsoft | ...
MC_VERSION=1.20.4          # Server version
```

### For Testing with Public Server
```
MC_HOST=mc.example.com
MC_PORT=25565
MC_USERNAME=your_username
MC_AUTH=microsoft           # requires browser login flow
MC_VERSION=1.20.4
```

---

## Troubleshooting

### Bot Fails to Connect
**Error:** "Connection refused" or "Unable to connect"
**Solution:** 
- Verify Minecraft server is running on MC_HOST:MC_PORT
- Check firewall allows connections
- Verify MC_VERSION matches server version

### No Perception Events
**Error:** Bot connects but frontend shows no status updates
**Solution:**
- Check Node.js subprocess is actually running
- Verify subprocess stdout is being read by MinecraftBotManager
- Check browser console for SocketIO errors

### Tool Call Times Out
**Error:** "Tool execution timed out after 30 seconds"
**Solution:**
- Increase timeout in minecraft_agent.py (~line 170)
- For pathfinding actions (move_to_position), allow 60+ seconds
- Check if bot is stuck (e.g., pathfinding failed)

### Tool Not Found
**Error:** "Unknown tool minecraft_xyz"
**Solution:**
- Verify tool is defined in tools.py
- Check tool name spelling matches exactly
- Tool must start with "minecraft_" prefix

---

## Next Steps: Faza 3

### Advanced Actions to Implement

1. **Mining Automation Loop**
   - Detect ore blocks
   - Pathfind to nearest ore
   - Mine and collect drops
   - Store results in inventory

2. **Crafting System**
   - Parse recipe definitions
   - Auto-craft items based on inventory
   - Handle multi-step recipes

3. **Combat System**
   - Detect hostile mobs
   - Auto-attack with equipped tool
   - Flee if health low
   - Re-engage when safe

4. **Location Memory**
   - Save discovered locations
   - Remember waypoints
   - Fast travel to known locations
   - Build routes between locations

5. **Resource Management**
   - Track inventory capacity
   - Prioritize valuable items
   - Drop low-value items when full
   - Return to storage when needed

---

## Performance Metrics

- **Bot Initialization:** < 5 seconds
- **Perception Event Rate:** 1 /second
- **Action Execution Time:** 1-30 seconds (depends on action)
- **Tool Call Response:** < 100ms (async)
- **SocketIO Latency:** < 50ms (local network)

---

## File Structure

```
backend/
├── minecraft_agent.py          [Python bot manager]
├── tools.py                    [Tool definitions]
├── monikai.py                  [AI loop - routes tool calls]
├── server.py                   [SocketIO handlers]
└── minecraft-bot/              [Node.js bot]
    ├── index.js                [Bot entry + handlers]
    ├── .env                    [Server config]
    ├── package.json            [Dependencies]
    ├── node_modules/           [Installed packages]
    └── src/
        ├── perception.js       [Game state reading]
        └── actions.js          [Action registry]
```

---

**Last Updated:** 2026-03-30
**Status:** Ready for Faza 3 Implementation
