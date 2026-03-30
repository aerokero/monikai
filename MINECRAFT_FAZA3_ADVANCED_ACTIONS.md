# Minecraft Bot Integration - Faza 3: Advanced Actions

## Status: COMPLETE ✅

### Overview

Faza 3 adds sophisticated gameplay actions to the Minecraft bot, enabling it to perform complex tasks like mining, crafting, combat, and navigation.

---

## Advanced Actions Implemented

### 1. **mine_ore** - Automated Ore Mining

**Purpose:** Find and extract ore resources from the mining world.

**Parameters:**
- `ore_type` (string, required): Type of ore to mine
  - Options: stone, iron, coal, diamond, copper, gold
- `max_blocks` (integer, optional): Maximum blocks to mine (default: 5, max: 20)
- `max_distance` (integer, optional): Maximum search radius (default: 50)

**Execution Flow:**
```
Choose ore_type → Search within max_distance radius
  ↓
Find nearest ore block matching type
  ↓
Pathfind to block location using Pathfinder plugin
  ↓
Break block with appropriate tool
  ↓
Collect dropped items into inventory
  ↓
Repeat up to max_blocks times
  ↓
Return: Count of blocks mined + positions
```

**Timeout:** 60 seconds (allows for pathfinding and mining)

**Example Usage:**
```
Gemini: "Mine 10 diamond ore blocks"
  ↓
Tool Call: minecraft_mine_ore(ore_type="diamond", max_blocks=10)
  ↓
Result: "Mined 3 diamond ore blocks" (may be less if not enough ore found)
```

**Returns:**
```json
{
  "success": true,
  "message": "Mined 3 diamond ore blocks",
  "blocks_mined": 3
}
```

---

### 2. **craft_recipe** - Item Crafting

**Purpose:** Convert raw materials into crafted items.

**Parameters:**
- `recipe` (string, required): Recipe name to craft
  - Supported: sticks, planks, charcoal (extensible)
- `count` (integer, optional): Number of items to craft (default: 1, max: 64)

**Supported Recipes:**
- **sticks**: Requires `planks` → produces 2x sticks
- **planks**: Requires `log` → produces 4x planks
- **charcoal**: Requires `log` → produces 1x charcoal (when smelted)

**Validation:**
- Checks inventory for required ingredients
- Validates recipe exists
- Respects inventory stack limits

**Timeout:** 15 seconds

**Example Usage:**
```
Gemini: "Craft 16 sticks from the planks in my inventory"
  ↓
Tool Call: minecraft_craft_recipe(recipe="sticks", count=16)
  ↓
Validation: Bot has planks ✓
  ↓
Result: "Crafted 16x sticks"
```

**Returns:**
```json
{
  "success": true,
  "message": "Crafted 16x sticks",
  "items_crafted": 16,
  "recipe": "sticks"
}
```

**Error Cases:**
```json
{
  "success": false,
  "error": "Missing ingredients for sticks. Need: planks"
}
```

---

### 3. **hunt_mobs** - Combat & Hostile Mob Hunting

**Purpose:** Locate and eliminate hostile mobs for combat experience and drops.

**Parameters:**
- `mob_type` (string, required): Type of mob to hunt
  - Options: zombie, spider, creeper, skeleton, enderman, blazes, etc.
- `max_distance` (integer, optional): Search radius (default: 50)
- `max_health_loss` (integer, optional): Retreat threshold (default: 5 health points)

**Combat Strategy:**
```
Find mob_type within max_distance
  ↓
Calculate distance and threat level
  ↓
Pathfind to mob position
  ↓
Attack with equipped tool/weapon
  ↓
Monitor bot health - retreat if loss > max_health_loss
  ↓
Continue until mob dies or health critical
  ↓
Return: Kill count + health status
```

**Timeout:** 30 seconds (combat duration)

**AI Prompt Integration:**
The bot automatically:
- Selects nearest mob if multiple found
- Manages retreat if health gets low
- Respects damage thresholds
- Tracks kills for resource gathering

**Example Usage:**
```
Gemini: "Hunt down some zombies, but don't take damage if possible"
  ↓
Tool Call: minecraft_hunt_mobs(mob_type="zombie", max_health_loss=2)
  ↓
Result: "Killed 2 zombie mobs, health lost: 4"
```

**Returns:**
```json
{
  "success": true,
  "message": "Killed 1 zombie mob(s)",
  "health_remaining": 16,
  "health_lost": 4
}
```

---

### 4. **navigate_to_location** - Precision Navigation

**Purpose:** Move bot to exact coordinates with pathfinding and vertical navigation.

**Parameters:**
- `x` (number, required): Target X coordinate
- `y` (number, required): Target Y coordinate (affects vertical climbing)
- `z` (number, required): Target Z coordinate
- `label` (string, optional): Location name for logging (e.g., "Spawn", "Base", "Gold Deposits")

**Navigation Features:**
```
Parse target coordinates (x, y, z)
  ↓
Calculate path using Pathfinder
  ↓
Horizontal movement: Navigate to (x, z) using A* pathfinding
  ↓
Vertical movement: Jump/climb to match Y coordinate
  ↓
Monitor progress and detect obstacles
  ↓
Return: Distance traveled + final position
```

**Timeout:** 60 seconds (allows for complex pathfinding)

**Vertical Logic:**
- Bot automatically jumps if target Y is higher
- Handles terrain climbing
- Stops at correct height when reached

**Example Usage:**
```
Gemini: "Navigate to the base at coordinates 1000, 64, -500"
  ↓
Tool Call: minecraft_navigate_to_location(x=1000, y=64, z=-500, label="Base")
  ↓
Result: "Reached Base, distance: 1243.45 blocks"
```

**Returns Success:**
```json
{
  "success": true,
  "message": "Reached Base",
  "distance_traveled": 1243.45,
  "final_position": {
    "x": "1000.00",
    "y": "64.00",
    "z": "-500.00"
  }
}
```

**Returns Error:**
```json
{
  "success": false,
  "error": "Failed to navigate to Base: Pathfinding blocked",
  "current_position": {
    "x": "850.50",
    "y": "62.00",
    "z": "-380.25"
  }
}
```

---

## Advanced Tool Definitions (Gemini Integration)

All 4 advanced tools are registered in `tools.py` with proper schemas:

**minecraft_mine_ore_tool:**
- Inputs: ore_type, max_blocks, max_distance
- Outputs: success, message, blocks_mined

**minecraft_craft_recipe_tool:**
- Inputs: recipe, count
- Outputs: success, message, items_crafted, recipe

**minecraft_hunt_mobs_tool:**
- Inputs: mob_type, max_distance, max_health_loss
- Outputs: success, message, health_remaining, health_lost

**minecraft_navigate_to_location_tool:**
- Inputs: x, y, z, label
- Outputs: success, message, distance_traveled, final_position

---

## Gemini AI Prompting Strategy

The AI model now understands:

1. **Resource Gathering Workflow**
   ```
   "Mine ore with minecraft_mine_ore"
   → "Craft sticks from logs with minecraft_craft_recipe"
   → "Navigate to storage with minecraft_navigate_to_location"
   ```

2. **Combat Scenarios**
   ```
   "Hunt mobs for experience"
   → "Monitor health with minecraft_inventory_status"
   → "Retreat if health low with minecraft_navigate_to_location"
   ```

3. **Exploration & Discovery**
   ```
   "Navigate to coordinates to scout"
   → "Find ore with mine_ore (search mode)"
   → "Return to base"
   ```

---

## Timeout Configuration

| Action | Timeout | Reason |
|--------|---------|--------|
| mine_ore | 60s | Pathfinding + mining loops |
| craft_recipe | 15s | Crafting + inventory management |
| hunt_mobs | 30s | Combat + health monitoring |
| navigate_to_location | 60s | Long-distance pathfinding |

---

## Parameter Mapping (monikai.py)

Tool call parameters are correctly mapped to action parameters:

```python
# Example: minecraft_mine_ore tool parameters
{
  "ore_type": str,       # maps to ore_type
  "max_blocks": int,     # maps to max_blocks
  "max_distance": int    # maps to max_distance
}

# Executed as:
await bot_manager.send_action("mine_ore", {
  "ore_type": "diamond",
  "max_blocks": 10,
  "max_distance": 50
})
```

---

## Error Handling

### Graceful Failures

1. **Ore Not Found**
   - Returns count=0 instead of error
   - Allows incomplete missions

2. **Recipe Ingredients Missing**
   - Explicit error message with required items
   - Suggests inventory check

3. **Pathfinding Blocked**
   - Returns last known position
   - Allows retry with different target
   - Provides distance traveled info

4. **Combat Health Critical**
   - Retreat mechanism prevents bot death
   - Returns before killing blow

---

## Testing Scenarios

### Scenario 1: Mining Quest
```
User: "Mine 10 coal ore blocks and craft wood sticks from the logs nearby"

Expected Flow:
1. minecraft_mine_ore(ore_type="coal", max_blocks=10)
2. minecraft_mine_ore(ore_type="log", max_blocks=5)
3. minecraft_craft_recipe(recipe="sticks", count=16)
4. Result: "Mined coal and wood, crafted sticks"
```

### Scenario 2: Exploration & Base Return
```
User: "Explore the area at coordinates 2000, 100, 3000 and hunt any mobs, then return to base at 0, 64, 0"

Expected Flow:
1. minecraft_navigate_to_location(x=2000, y=100, z=3000, label="Exploration Site")
2. minecraft_hunt_mobs(mob_type="zombie")
3. minecraft_navigate_to_location(x=0, y=64, z=0, label="Base")
4. Result: "Explored and returned safely"
```

### Scenario 3: Health Management
```
User: "Hunt spiders but stop if health drops below 10"

Expected Flow:
1. minecraft_hunt_mobs(mob_type="spider", max_health_loss=10)
   - Monitors health
   - Triggers retreat at threshold
2. Result: "Killed X spiders, health critical"
3. Suggestion: "Rest or find food to recover"
```

---

## Performance Metrics (Estimated)

| Action | Average Duration | Notes |
|--------|------------------|-------|
| mine_ore (5 blocks) | 15-30s | Depends on ore abundance |
| craft_recipe (16 items) | 2-5s | Instant in gameplay |
| hunt_mobs (1 kill) | 10-20s | Depends on mob difficulty |
| navigate_to_location (100 blocks) | 15-30s | Depends on terrain |

---

## Limitations & Future Enhancements

### Current Limitations
1. No advanced pathfinding around obstacles (relies on mineflayer)
2. No swimming/water navigation
3. No equipping specific tools for mining
4. Crafting limited to simple 2x2 recipes
5. No multi-target combat (single mob at a time)

### Faza 4+ Enhancements
1. **Smart Tool Selection**: Equip best tool for ore type
2. **Swimming & Water Navigation**: Navigate through oceans
3. **Advanced Crafting**: 3x3 workbench recipes
4. **Mob Farming**: Automated spawner management
5. **Base Management**: Auto-storage and sorting
6. **Trading System**: interact with NPCs
7. **Potion Brewing**: Advanced alchemy

---

## Code Statistics

| Component | Lines | Status |
|-----------|-------|--------|
| actions.js (with Faza 3) | 685 | ✅ Complete |
| tools.py (with Faza 3) | 382 | ✅ Complete |
| monikai.py (handlers) | ~130 | ✅ Complete |
| server.py (SocketIO) | ~90 | ✅ Complete |
| **Total Bot Backend** | **~1200** | **✅ Full Stack Ready** |

---

## Next Steps: Faza 4 - Frontend

### UI Components to Build
1. **MinecraftWindow.jsx**: Main window with tabs
2. **StatusPanel**: Health, hunger, position display
3. **ChatLog**: Real-time chat history
4. **InventoryViewer**: Current inventory items
5. **ActionQueue**: Pending/executing actions
6. **MapViewer**: Location visualization (optional)

### Integration Points
- SocketIO event listeners for:
  - `minecraft_status`
  - `minecraft_perception`
  - `minecraft_action_result`
- Real-time updates from percetion events
- Action confirmation before execution (optional)

---

**Faza 3 Status:** ✅ COMPLETE
**Ready for:** Faza 4 Frontend Development
**Last Updated:** 2026-03-30
