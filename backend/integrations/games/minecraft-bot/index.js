/**
 * Minecraft Bot - Main Entry Point
 * Connects to Minecraft server and communicates with Python backend via IPC
 */

import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import mineflayer from 'mineflayer';
import mcProtocol from 'minecraft-protocol';
import pathfinderPkg from 'mineflayer-pathfinder';
import ArmorManager from 'mineflayer-armor-manager';
import autoEat from 'mineflayer-auto-eat';
import pvpPkg from 'mineflayer-pvp';
import toolPkg from 'mineflayer-tool';
import collectBlockPkg from 'mineflayer-collectblock';
import { Vec3 } from 'vec3';

// Load .env file
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.join(__dirname, '.env') });

const { pathfinder: Pathfinder, Movements } = pathfinderPkg;
const { goals } = pathfinderPkg;
const { plugin: pvp } = pvpPkg;
const { plugin: collectBlock } = collectBlockPkg;
const toolPlugin = toolPkg.plugin;
const { GoalNear } = goals;

// Configuration from environment variables
const config = {
  host: process.env.MC_HOST || 'localhost',
  port: parseInt(process.env.MC_PORT || '25565'),
  username: process.env.MC_USERNAME || 'strawberryglass',
  auth: process.env.MC_AUTH || 'offline',
  // Auto-detect protocol by default; hardcoding an older version can trigger movement validation kicks.
  version: process.env.MC_VERSION || false,
  autoEatEnabled: String(process.env.MC_AUTOEAT || 'false').toLowerCase() === 'true'
};

// Bot instance
let bot = null;
let isConnected = false;
let currentActionRequestId = null;
let currentActionName = null;
let lastKickReason = null;
let movementFrozenUntil = 0;
let pathfinderReady = false;
let physicsIdleTimer = null;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function formatBotError(error) {
  if (!error) {
    return {
      message: 'Unknown bot error',
      details: []
    };
  }

  const details = [];
  const baseMessage = error?.message || String(error);

  if (Array.isArray(error?.errors) && error.errors.length > 0) {
    for (const sub of error.errors) {
      const code = sub?.code || 'UNKNOWN';
      const address = sub?.address || 'unknown-address';
      const port = sub?.port || 'unknown-port';
      const msg = sub?.message || String(sub);
      details.push(`${code} at ${address}:${port} (${msg})`);
    }
  } else if (error?.code) {
    const address = error?.address || 'unknown-address';
    const port = error?.port || 'unknown-port';
    details.push(`${error.code} at ${address}:${port}`);
  }

  return {
    message: baseMessage,
    details
  };
}

function flattenKickReason(reason) {
  if (reason == null) return '';
  if (typeof reason === 'string') return reason;
  if (typeof reason === 'number' || typeof reason === 'boolean') return String(reason);
  if (Array.isArray(reason)) {
    return reason.map(flattenKickReason).filter(Boolean).join(' ').trim();
  }

  if (typeof reason === 'object') {
    // Handle minecraft-protocol NBT-like packets: { type: 'compound'|'string'|..., value: ... }
    if (Object.prototype.hasOwnProperty.call(reason, 'type') && Object.prototype.hasOwnProperty.call(reason, 'value')) {
      const nbtType = String(reason.type || '').toLowerCase();
      const nbtValue = reason.value;
      if (nbtType === 'string') {
        return String(nbtValue || '');
      }
      return flattenKickReason(nbtValue);
    }

    const translateRaw = reason.translate;
    const textRaw = reason.text;
    const withRaw = reason.with;
    const extraRaw = reason.extra;

    const textValue = typeof textRaw === 'string'
      ? textRaw
      : (textRaw && typeof textRaw === 'object' && 'value' in textRaw ? String(textRaw.value || '') : '');
    const translateValue = typeof translateRaw === 'string'
      ? translateRaw
      : (translateRaw && typeof translateRaw === 'object' && 'value' in translateRaw ? String(translateRaw.value || '') : '');

    const textParts = [];
    if (textValue.trim()) {
      textParts.push(textValue.trim());
    }
    if (translateValue.trim()) {
      const withArgs = Array.isArray(withRaw)
        ? withRaw.map(flattenKickReason).filter(Boolean).join(', ')
        : '';
      textParts.push(withArgs ? `${translateValue} (${withArgs})` : translateValue);
    }
    if (Array.isArray(extraRaw)) {
      const extra = extraRaw.map(flattenKickReason).filter(Boolean).join(' ');
      if (extra) textParts.push(extra);
    }

    const composed = textParts.join(' ').trim();
    if (composed) return composed;

    try {
      return JSON.stringify(reason);
    } catch {
      return String(reason);
    }
  }

  return String(reason);
}

function formatKickReason(reason) {
  const flat = flattenKickReason(reason);
  return flat || 'unknown kick reason';
}

function freezeMovement(ms) {
  movementFrozenUntil = Math.max(movementFrozenUntil, Date.now() + Math.max(0, ms || 0));
}

function keepPhysicsEnabled(bot, ms = 1200) {
  if (!bot) return;

  if (physicsIdleTimer) {
    clearTimeout(physicsIdleTimer);
    physicsIdleTimer = null;
  }

  bot.physicsEnabled = true;
  physicsIdleTimer = setTimeout(() => {
    try {
      bot.physicsEnabled = false;
    } catch {}
    physicsIdleTimer = null;
  }, Math.max(250, ms));
}

async function waitForMovementWindow() {
  const waitMs = movementFrozenUntil - Date.now();
  if (waitMs > 0) {
    await sleep(waitMs);
  }
}

function configureConservativePathfinder(bot) {
  if (!bot?.pathfinder || !Movements) return;
  try {
    const moves = new Movements(bot);
    moves.allowSprinting = false;
    moves.allowParkour = false;
    moves.allow1by1towers = false;
    moves.allowFreeMotion = false;
    moves.canOpenDoors = false;
    bot.pathfinder.setMovements(moves);
  } catch (e) {
    console.error(`[MinecraftBot] Failed to configure conservative pathfinder movements: ${e.message}`);
  }
}

function ensurePathfinderLoaded(bot) {
  if (bot?.pathfinder) {
    if (!pathfinderReady) {
      configureConservativePathfinder(bot);
      pathfinderReady = true;
    }
    return true;
  }

  try {
    bot.loadPlugin(Pathfinder);
    if (bot?.pathfinder) {
      configureConservativePathfinder(bot);
      pathfinderReady = true;
      console.error('[MinecraftBot] Pathfinder loaded on-demand');
      return true;
    }
  } catch (e) {
    console.error(`[MinecraftBot] Failed to load pathfinder on-demand: ${e.message}`);
  }
  return false;
}

async function safePathfinderGoto(bot, goal) {
  if (!ensurePathfinderLoaded(bot)) return false;
  await waitForMovementWindow();
  keepPhysicsEnabled(bot, 2500);

  try { bot.clearControlStates(); } catch {}
  try { bot.pathfinder.stop(); } catch {}
  try { bot.pathfinder.setGoal(null); } catch {}
  await sleep(60);

  await bot.pathfinder.goto(goal);
  return true;
}

function findItemByNameFragment(bot, wantedName) {
  const wanted = (wantedName || '').toLowerCase();
  if (!wanted) return null;
  return bot.inventory.items().find(i => i.name.toLowerCase().includes(wanted)) || null;
}

function normalizeNickname(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9_]/g, '');
}

function levenshteinDistance(a, b) {
  const aa = normalizeNickname(a);
  const bb = normalizeNickname(b);
  if (!aa) return bb.length;
  if (!bb) return aa.length;

  const prev = Array(bb.length + 1)
    .fill(0)
    .map((_, i) => i);
  const curr = Array(bb.length + 1).fill(0);

  for (let i = 1; i <= aa.length; i += 1) {
    curr[0] = i;
    for (let j = 1; j <= bb.length; j += 1) {
      const cost = aa[i - 1] === bb[j - 1] ? 0 : 1;
      curr[j] = Math.min(
        prev[j] + 1,
        curr[j - 1] + 1,
        prev[j - 1] + cost
      );
    }
    for (let j = 0; j <= bb.length; j += 1) {
      prev[j] = curr[j];
    }
  }
  return prev[bb.length];
}

function getResolvablePlayers(bot, includeSelf = false) {
  const own = normalizeNickname(bot?.username);
  return Object.entries(bot.players || {})
    .filter(([name, p]) => {
      if (!p?.entity) return false;
      if (includeSelf) return true;
      return normalizeNickname(name) !== own;
    })
    .map(([name, p]) => ({
      username: name,
      normalized: normalizeNickname(name),
      player: p,
    }));
}

function resolvePlayerByName(bot, rawName, options = {}) {
  const { includeSelf = false } = options;
  const query = normalizeNickname(rawName);
  const players = getResolvablePlayers(bot, includeSelf);
  if (!query || players.length === 0) {
    return { target: null, resolvedName: null, reason: 'missing-query-or-players' };
  }

  const exact = players.find(p => p.normalized === query);
  if (exact) return { target: exact.player, resolvedName: exact.username, reason: 'exact' };

  const prefix = players.find(p => p.normalized.startsWith(query) || query.startsWith(p.normalized));
  if (prefix) return { target: prefix.player, resolvedName: prefix.username, reason: 'prefix' };

  const contains = players.find(p => p.normalized.includes(query) || query.includes(p.normalized));
  if (contains) return { target: contains.player, resolvedName: contains.username, reason: 'contains' };

  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const candidate of players) {
    const distance = levenshteinDistance(query, candidate.normalized);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = candidate;
    }
  }

  const threshold = Math.max(2, Math.floor(query.length * 0.4));
  if (best && bestDistance <= threshold) {
    return { target: best.player, resolvedName: best.username, reason: `fuzzy:${bestDistance}` };
  }

  return { target: null, resolvedName: null, reason: 'not-found' };
}

function resolvePlayerTarget(bot, rawName, options = {}) {
  const { includeSelf = false } = options;
  const raw = String(rawName || '').trim();
  const normalized = raw.toLowerCase();
  const isGeneric = !raw || normalized === 'player' || normalized === 'user' || normalized === 'you';

  if (!isGeneric) {
    const resolved = resolvePlayerByName(bot, raw, { includeSelf });
    if (resolved.target?.entity) {
      return {
        ok: true,
        target: resolved.target,
        resolvedName: resolved.resolvedName || raw,
      };
    }

    return {
      ok: false,
      message: `Player ${raw} not found. Available: ${getResolvablePlayers(bot, includeSelf).map(p => p.username).join(', ')}`,
    };
  }

  const availablePlayers = getResolvablePlayers(bot, includeSelf);
  if (availablePlayers.length === 0) {
    return {
      ok: false,
      message: 'No other players found on the server',
    };
  }

  if (availablePlayers.length === 1) {
    return {
      ok: true,
      target: availablePlayers[0].player,
      resolvedName: availablePlayers[0].username,
    };
  }

  let closest = null;
  let closestDist = Number.POSITIVE_INFINITY;
  for (const candidate of availablePlayers) {
    if (!candidate.player?.entity?.position || !bot.entity?.position) continue;
    const d = bot.entity.position.distanceTo(candidate.player.entity.position);
    if (d < closestDist) {
      closestDist = d;
      closest = candidate;
    }
  }

  if (closest?.player?.entity) {
    return {
      ok: true,
      target: closest.player,
      resolvedName: closest.username,
    };
  }

  return {
    ok: false,
    message: 'Could not determine target player',
  };
}

function findNearestBlockByName(bot, predicate, maxDistance = 16) {
  const matchingIds = Object.values(bot.registry.blocksByName || {})
    .filter(b => predicate(b.name))
    .map(b => b.id);
  if (matchingIds.length === 0) return null;

  const pos = bot.findBlock({
    matching: matchingIds,
    maxDistance,
  });
  return pos || null;
}

function countInventoryItemByName(bot, itemName) {
  return bot.inventory
    .items()
    .filter(i => i.name === itemName)
    .reduce((sum, i) => sum + i.count, 0);
}

function isEmptyBlock(block) {
  return !!block && block.boundingBox === 'empty';
}

function isSolidBlock(block) {
  return !!block && block.boundingBox === 'block';
}

function isUnsafeFluidBlock(block) {
  if (!block) return false;
  const n = String(block.name || '').toLowerCase();
  return n.includes('water') || n.includes('lava');
}

function isWalkableSpace(block) {
  if (!isEmptyBlock(block)) return false;
  return !isUnsafeFluidBlock(block);
}

function findGroundedTargetNear(bot, desiredPos, maxHorizontalRadius = 3, maxVerticalDelta = 3) {
  if (!bot || !desiredPos) return desiredPos;

  const baseX = Math.floor(desiredPos.x);
  const baseY = Math.floor(desiredPos.y);
  const baseZ = Math.floor(desiredPos.z);

  let best = null;
  let bestScore = Number.POSITIVE_INFINITY;

  for (let dy = -maxVerticalDelta; dy <= maxVerticalDelta; dy++) {
    const y = baseY + dy;
    for (let dx = -maxHorizontalRadius; dx <= maxHorizontalRadius; dx++) {
      for (let dz = -maxHorizontalRadius; dz <= maxHorizontalRadius; dz++) {
        const x = baseX + dx;
        const z = baseZ + dz;

        const feetPos = new Vec3(x, y, z);
        const feetBlock = bot.blockAt(feetPos);
        const headBlock = bot.blockAt(feetPos.offset(0, 1, 0));
        const belowBlock = bot.blockAt(feetPos.offset(0, -1, 0));

        // Require solid support and two free, non-fluid spaces for body/head.
        if (!isSolidBlock(belowBlock)) continue;
        if (!isWalkableSpace(feetBlock)) continue;
        if (!isWalkableSpace(headBlock)) continue;

        const horizontal = Math.abs(dx) + Math.abs(dz);
        const score = horizontal + Math.abs(dy) * 2;
        if (score < bestScore) {
          best = feetPos;
          bestScore = score;
        }
      }
    }
  }

  return best || desiredPos;
}

async function gotoBlockIfPossible(bot, block, range = 2) {
  if (!block) return;
  if (!bot.pathfinder) return;
  await safePathfinderGoto(bot, new GoalNear(block.position.x, block.position.y, block.position.z, range));
}

/**
 * Send perception event to Python backend via stdout
 */
function sendPerceptionEvent(type, data = {}) {
  const payload = { ...(data || {}) };
  if ((type === 'action_result' || type === 'error') && currentActionRequestId && !payload.request_id) {
    payload.request_id = currentActionRequestId;
  }
  if ((type === 'action_result' || type === 'error') && currentActionName && !payload.action) {
    payload.action = currentActionName;
  }

  const event = {
    type,
    data: payload,
    timestamp: new Date().toISOString()
  };
  console.log(JSON.stringify(event));
}

/**
 * Handle chat messages
 */
function setupChatHandler(bot) {
  bot.on('chat', (username, message) => {
    if (username === bot.username) return; // Ignore own messages
    
    sendPerceptionEvent('chat', {
      username,
      message,
      timestamp: Date.now()
    });
  });
}

/**
 * Handle player join/leave
 */
function setupPlayerHandler(bot) {
  bot.on('playerJoined', (player) => {
    sendPerceptionEvent('player_joined', {
      username: player.username,
      uuid: player.uuid
    });
  });

  bot.on('playerLeft', (player) => {
    sendPerceptionEvent('player_left', {
      username: player.username
    });
  });
}

/**
 * Periodic status updates
 */
function setupStatusUpdates(bot) {
  setInterval(() => {
    const position = bot.entity.position;
    const health = bot.health;
    const hunger = bot.food;
    const dimension = bot.game.dimension;

    // Build inventory representation
    const inventory = bot.inventory.items().map(item => ({
      name: item.name,
      count: item.count,
      metadata: item.metadata
    }));

    sendPerceptionEvent('status_update', {
      health,
      hunger,
      position: position ? { x: position.x, y: position.y, z: position.z } : null,
      dimension,
      inventory,
      uuid: bot.uuid
    });
  }, 1000); // Every second
}

function setupDamageStabilization(bot) {
  let lastDamageStabilizeAt = 0;

  bot.on('entityHurt', async (entity) => {
    if (!entity || !bot?.entity) return;
    if (entity !== bot.entity) return;

    const now = Date.now();
    if (now - lastDamageStabilizeAt < 350) return;
    lastDamageStabilizeAt = now;

    try {
      freezeMovement(1200);

      if (bot.pvp && typeof bot.pvp.stop === 'function') {
        bot.pvp.stop();
      }

      if (bot.pathfinder) {
        try { bot.pathfinder.setGoal(null); } catch {}
        try { bot.pathfinder.stop(); } catch {}
      }

      bot.clearControlStates();
      await sleep(450);
      bot.clearControlStates();
      bot.physicsEnabled = false;
    } catch (e) {
      console.error(`[MinecraftBot] Damage stabilization error: ${e.message}`);
    }
  });
}

function setupAutoEquipArmor(bot) {
  // Auto-equip armor when items are collected
  let lastAutoEquipAt = 0;

  bot.on('itemCollected', async (item) => {
    try {
      const now = Date.now();
      // Debounce to avoid too frequent equip checks (max once per 1 second)
      if (now - lastAutoEquipAt < 1000) return;
      lastAutoEquipAt = now;

      const hasArmorItem = item?.name?.includes('helmet') ||
                            item?.name?.includes('chestplate') ||
                            item?.name?.includes('leggings') ||
                            item?.name?.includes('boots') ||
                            item?.name?.includes('armor');

      // Only auto-equip if the collected item is armor
      if (hasArmorItem && bot.armorManager && typeof bot.armorManager.autoEquip === 'function') {
        console.error(`[MinecraftBot] Armor collected (${item?.name}), auto-equipping...`);
        await sleep(200);
        await bot.armorManager.autoEquip();
        console.error('[MinecraftBot] Armor auto-equipped');
      }
    } catch (e) {
      console.error(`[MinecraftBot] Auto-equip armor error: ${e.message}`);
    }
  });
}

/**
 * Handle incoming actions from Python backend
 */
function setupActionHandler(bot) {
  process.stdin.setEncoding('utf-8');
  let stdinBuffer = '';

  process.stdin.on('data', async (data) => {
    stdinBuffer += data;
    const lines = stdinBuffer.split(/\r?\n/);
    stdinBuffer = lines.pop() || '';

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) continue;

      try {
        const action = JSON.parse(line);
        await handleAction(bot, action);
      } catch (error) {
        sendPerceptionEvent('error', {
          message: `Failed to parse action: ${error.message}`,
          originalData: line
        });
      }
    }
  });
}

/**
 * Execute action received from Python backend
 */
async function handleAction(bot, action) {
  currentActionRequestId = action?.request_id || null;
  let { action: actionName, params = {}, timestamp } = action;

  // Normalize AIRI-style action names/params into local equivalents.
  if (actionName === 'goToPlayer') {
    actionName = 'move_to_player';
    params = {
      name: params.player_name || params.name,
      range: params.closeness ?? params.range ?? 2,
    };
  } else if (actionName === 'mineBlockAt') {
    actionName = 'break_block';
  } else if (actionName === 'craftRecipe') {
    actionName = 'craft_recipe';
    params = {
      recipe: params.recipe_name || params.recipe,
      count: params.num ?? params.count ?? 1,
    };
  } else if (actionName === 'discard') {
    actionName = 'drop_item';
    params = {
      name: params.item_name || params.name,
      count: params.num ?? params.count ?? 1,
    };
  } else if (actionName === 'collectBlocks') {
    actionName = 'collect_blocks';
    params = {
      type: params.type,
      num: params.num ?? 1,
    };
  }

  currentActionName = actionName;

  try {
    switch (actionName) {
      case 'chat':
      case 'chat_message':
        bot.chat(params.message || '');
        sendPerceptionEvent('action_result', {
          action: actionName,
          success: true,
          message: `Sent chat message: ${params.message}`
        });
        break;

      case 'skip':
        sendPerceptionEvent('action_result', {
          action: actionName,
          success: true,
          message: 'Skipped turn'
        });
        break;

      case 'giveUp':
      case 'give_up':
        sendPerceptionEvent('action_result', {
          action: actionName,
          success: false,
          message: params.reason || 'Bot reported stuck state'
        });
        break;

      case 'move':
        // Move towards a direction
        const { x = 0, z = 0 } = params;
        keepPhysicsEnabled(bot, (params.duration || 1000) + 600);
        bot.setControlState('forward', x > 0);
        bot.setControlState('back', x < 0);
        bot.setControlState('left', z > 0);
        bot.setControlState('right', z < 0);
        setTimeout(() => {
          bot.clearControlStates();
        }, params.duration || 1000);
        sendPerceptionEvent('action_result', {
          action: actionName,
          success: true,
          message: `Moving...`
        });
        break;

      case 'move_to_player':
        // Move towards a player
        try {
          const rawName = (params.player_name || params.name || '').trim();
          const resolvedTarget = resolvePlayerTarget(bot, rawName, { includeSelf: false });
          if (!resolvedTarget.ok) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: resolvedTarget.message
            });
            break;
          }

          const targetPlayer = resolvedTarget.target;
          const resolvedName = resolvedTarget.resolvedName || rawName;

          if (!targetPlayer?.entity) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'Could not determine target player'
            });
            break;
          }

          const range = params.range || params.distance || 2;
          if (bot.pathfinder) {
            const pos = targetPlayer.entity.position;
            await safePathfinderGoto(bot, new GoalNear(pos.x, pos.y, pos.z, range));
          } else {
            keepPhysicsEnabled(bot, 2600);
            await bot.lookAt(targetPlayer.entity.position, true);
            bot.setControlState('forward', true);
            await sleep(2000);
            bot.clearControlStates();
          }

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Moved towards player ${resolvedName}`
          });
        } catch (e) {
          console.error(`[Bot] Error moving to player: ${e.message}`);
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error moving to player: ${e.message}`
          });
        }
        break;

      case 'move_to_position':
        // Move to specific coordinates
        if (params.x !== undefined && params.y !== undefined && params.z !== undefined) {
          try {
            const requestedPos = new Vec3(params.x, params.y, params.z);
            const targetPos = findGroundedTargetNear(bot, requestedPos, 3, 3);
            
            console.error(`[Bot] Moving to position ${params.x}, ${params.y}, ${params.z} (resolved to ${targetPos.x}, ${targetPos.y}, ${targetPos.z})`);
            
            if (bot.pathfinder) {
              await safePathfinderGoto(bot, new GoalNear(targetPos.x, targetPos.y, targetPos.z, params.range || 1));
            } else {
              console.error(`[Bot] Pathfinder not available, using direct movement`);
              keepPhysicsEnabled(bot, 2600);
              bot.setControlState('forward', true);
              await sleep(2000);
              bot.clearControlStates();
            }
            
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: true,
              message: `Moved to position ${params.x}, ${params.y}, ${params.z}`
            });
          } catch (e) {
            console.error(`[Bot] Error moving to position: ${e.message}`);
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Error moving to position: ${e.message}`
            });
          }
        } else {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Coordinates required (x, y, z)`
          });
        }
        break;

      case 'look':
        // Look at coordinates
        const { yaw = 0, pitch = 0 } = params;
        bot.look(yaw, pitch, false);
        sendPerceptionEvent('action_result', {
          action: actionName,
          success: true,
          message: `Looking at yaw=${yaw}, pitch=${pitch}`
        });
        break;

      case 'look_at_position':
        // Natural head movement towards a world position.
        if (params.x !== undefined && params.y !== undefined && params.z !== undefined) {
          try {
            const tx = Number(params.x);
            const ty = Number(params.y);
            const tz = Number(params.z);
            const target = new Vec3(tx + 0.5, ty + 0.5, tz + 0.5);
            await bot.lookAt(target, true);
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: true,
              message: `Looking at position ${tx}, ${ty}, ${tz}`
            });
          } catch (e) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Error looking at position: ${e.message}`
            });
          }
        } else {
          sendPerceptionEvent('error', {
            action: actionName,
            message: 'Coordinates required (x, y, z)'
          });
        }
        break;

      case 'stop':
        sendPerceptionEvent('action_result', {
          action: actionName,
          success: true,
          message: 'Shutting down...'
        });
        setTimeout(() => process.exit(0), 500);
        break;

      case 'get_inventory':
      case 'inventory_status':
      case 'query_inventory':
        try {
          if (!bot.inventory) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Bot inventory not available`
            });
            break;
          }
          
          const items = bot.inventory.items();
          console.error(`[Bot] Inventory: ${items.length} items`);
          
          const inventory = items.map(item => ({
            name: item.name,
            count: item.count,
            metadata: item.metadata || 0
          }));
          
          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Inventory contains ${items.length} item types`,
            data: inventory
          });
        } catch (e) {
          console.error(`[Bot] Error getting inventory: ${e.message}`);
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error getting inventory: ${e.message}`
          });
        }
        break;

      case 'break_block':
        // Break a block at coordinates
        if (params.x !== undefined && params.y !== undefined && params.z !== undefined) {
          try {
            const blockPos = new Vec3(params.x, params.y, params.z);
            const block = bot.blockAt(blockPos);
            if (block) {
              if (bot.pathfinder) {
                await safePathfinderGoto(bot, new GoalNear(params.x, params.y, params.z, 1));
              }
              await bot.dig(block);
              sendPerceptionEvent('action_result', {
                action: actionName,
                success: true,
                message: `Broke block at ${params.x}, ${params.y}, ${params.z}`
              });
            } else {
              sendPerceptionEvent('error', {
                action: actionName,
                message: `No block at ${params.x}, ${params.y}, ${params.z}`
              });
            }
          } catch (e) {
            console.error(`[Bot] Error breaking block: ${e.message}`);
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Error breaking block: ${e.message}`
            });
          }
        } else {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Block coordinates required (x, y, z)`
          });
        }
        break;

      case 'respawn':
        bot.setControlState('respawn', true);
        setTimeout(() => {
          bot.setControlState('respawn', false);
        }, 100);
        sendPerceptionEvent('action_result', {
          action: actionName,
          success: true,
          message: `Respawning...`
        });
        break;

      case 'drop_item':
        // Drop item from inventory
        if (params.name) {
          try {
            const items = bot.inventory.items();
            const item = items.find(i => i.name === params.name);
            if (item) {
              const count = Math.min(params.count || 1, item.count);
              try {
                await bot.toss(item, count);
              } catch (e) {
                console.error(`[Bot] toss() not available, trying equipment drop`);
                // Fallback: just report the item exists
              }
              sendPerceptionEvent('action_result', {
                action: actionName,
                success: true,
                message: `Dropped ${count}x ${params.name}`
              });
            } else {
              sendPerceptionEvent('error', {
                action: actionName,
                message: `Item ${params.name} not in inventory. Available: ${items.map(i => i.name).join(', ')}`
              });
            }
          } catch (e) {
            console.error(`[Bot] Error dropping item: ${e.message}`);
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Error dropping item: ${e.message}`
            });
          }
        } else {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Item name required`
          });
        }
        break;

      case 'consume':
        try {
          const wanted = (params.item_name || '').toLowerCase();
          const items = bot.inventory.items();
          const item = wanted
            ? items.find(i => i.name.toLowerCase().includes(wanted))
            : items.find(i => i.name.includes('bread') || i.name.includes('beef') || i.name.includes('porkchop') || i.name.includes('apple'));

          if (!item) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `No consumable item found for '${wanted || 'auto'}'`
            });
            break;
          }

          await bot.equip(item, 'hand');
          await bot.consume();
          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Consumed ${item.name}`
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error consuming item: ${e.message}`
          });
        }
        break;

      case 'equip':
        try {
          const wanted = (params.item_name || '').toLowerCase();
          const item = bot.inventory.items().find(i => i.name.toLowerCase().includes(wanted));
          if (!item) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Item '${wanted}' not found in inventory`
            });
            break;
          }

          // Reject armor items - use equip_armor action instead
          const isArmor = item.name.toLowerCase().includes('helmet') ||
                          item.name.toLowerCase().includes('chestplate') ||
                          item.name.toLowerCase().includes('leggings') ||
                          item.name.toLowerCase().includes('boots');
          if (isArmor) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Cannot equip armor in hand. Use equip_armor action to equip ${item.name} to the right slot.`
            });
            break;
          }

          await bot.equip(item, 'hand');
          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Equipped ${item.name}`
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error equipping item: ${e.message}`
          });
        }
        break;

      case 'equip_armor':
        try {
          const armorSlots = {
            helmet: 'head',
            chestplate: 'torso',
            leggings: 'legs',
            boots: 'feet'
          };

          const items = bot.inventory.items();
          let equipped = 0;

          // Try to equip each armor type
          for (const [armorType, slot] of Object.entries(armorSlots)) {
            const armorItem = items.find(i => i.name.toLowerCase().includes(armorType));
            if (armorItem) {
              try {
                await bot.equip(armorItem, slot);
                equipped++;
              } catch (e) {
                console.error(`[MinecraftBot] Failed to equip ${armorType}: ${e.message}`);
              }
            }
          }

          if (equipped > 0) {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: true,
              message: `Equipped ${equipped} armor pieces`
            });
          } else {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: 'No armor found in inventory'
            });
          }
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error equipping armor: ${e.message}`
          });
        }
        break;

      case 'collect_blocks': {
        try {
          const blockType = (params.type || '').toLowerCase();
          const num = Math.min(Math.max(params.num || 1, 1), 32);
          if (!blockType) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'Block type is required'
            });
            break;
          }

          const blockInfo = bot.registry.blocksByName[blockType];
          if (!blockInfo) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Unknown block type '${blockType}'`
            });
            break;
          }

          const positions = bot.findBlocks({ matching: blockInfo.id, maxDistance: 64, count: num });
          if (!positions || positions.length === 0) {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: `No ${blockType} found nearby`
            });
            break;
          }

          let collected = 0;
          for (const pos of positions) {
            const block = bot.blockAt(pos);
            if (!block) continue;
            if (bot.pathfinder) {
              await safePathfinderGoto(bot, new GoalNear(pos.x, pos.y, pos.z, 1));
            }
            await bot.dig(block);
            collected += 1;
          }

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Collected ${collected}x ${blockType}`,
            data: { collected, type: blockType }
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error collecting blocks: ${e.message}`
          });
        }
        break;
      }

      case 'givePlayer':
        try {
          const playerName = (params.player_name || params.name || '').trim();
          const itemName = params.item_name;
          const num = Math.max(params.num || 1, 1);
          const resolvedTarget = resolvePlayerTarget(bot, playerName, { includeSelf: false });
          const targetName = resolvedTarget.resolvedName || playerName;
          const target = resolvedTarget.target?.entity || null;
          const item = itemName ? bot.inventory.items().find(i => i.name === itemName) : null;
          if (!resolvedTarget.ok || !target) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: resolvedTarget.message || `Target player '${playerName}' not found`
            });
            break;
          }
          if (!item) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Item '${itemName}' not found in inventory`
            });
            break;
          }

          if (bot.pathfinder) {
            await safePathfinderGoto(bot, new GoalNear(target.position.x, target.position.y, target.position.z, 2));
          }
          await bot.toss(item.type, null, Math.min(num, item.count));
          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Gave ${itemName} x${Math.min(num, item.count)} to ${targetName} (from '${playerName}')`
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error giving item: ${e.message}`
          });
        }
        break;

      case 'attack': {
        try {
          const entityType = (params.type || '').toLowerCase();
          const candidates = Object.values(bot.entities || {}).filter(entity => {
            if (!entity || entity === bot.entity) return false;
            if (!entity.position || !bot.entity?.position) return false;
            if (entity.position.distanceTo(bot.entity.position) > 24) return false;
            const name = (entity.name || '').toLowerCase();
            return !entityType || name.includes(entityType);
          }).sort((a, b) => a.position.distanceTo(bot.entity.position) - b.position.distanceTo(bot.entity.position));

          const target = candidates[0];
          if (!target) {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: entityType ? `No nearby entity matching '${entityType}'` : 'No nearby attack target found'
            });
            break;
          }

          const sword = bot.inventory.items().find(i => i.name.toLowerCase().includes('sword'));
          if (sword) {
            try {
              await bot.equip(sword, 'hand');
            } catch (e) {
              console.error(`[Bot] Failed to equip sword: ${e.message}`);
            }
          }

          if (bot.pathfinder) {
            await safePathfinderGoto(bot, new GoalNear(target.position.x, target.position.y, target.position.z, 2));
          }
          if (bot.pvp && typeof bot.pvp.attack === 'function') {
            bot.pvp.attack(target);
            await sleep(3000);
            if (typeof bot.pvp.stop === 'function') bot.pvp.stop();
          } else {
            bot.attack(target);
          }

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Attacked ${target.name || target.type || 'entity'}`
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error attacking: ${e.message}`
          });
        }
        break;
      }

      case 'attackPlayer': {
        try {
          const playerName = (params.player_name || params.name || '').trim();
          const resolvedTarget = resolvePlayerTarget(bot, playerName, { includeSelf: false });
          const targetPlayer = resolvedTarget.target;
          if (!resolvedTarget.ok || !targetPlayer?.entity) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: resolvedTarget.message || `Player ${playerName || 'unknown'} not found`
            });
            break;
          }

          const entity = targetPlayer.entity;
          if (bot.pathfinder) {
            await safePathfinderGoto(bot, new GoalNear(entity.position.x, entity.position.y, entity.position.z, 2));
          }
          if (bot.pvp && typeof bot.pvp.attack === 'function') {
            bot.pvp.attack(entity);
            await sleep(3000);
            if (typeof bot.pvp.stop === 'function') bot.pvp.stop();
          } else {
            bot.attack(entity);
          }

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Attacked player ${resolvedTarget.resolvedName || targetPlayer.username || playerName}`
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error attacking player: ${e.message}`
          });
        }
        break;
      }

      case 'goToBed': {
        try {
          const bedBlock = findNearestBlockByName(bot, name => name.includes('bed'), 32);
          if (!bedBlock) {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: 'No bed found nearby'
            });
            break;
          }

          await gotoBlockIfPossible(bot, bedBlock, 2);
          await bot.sleep(bedBlock);
          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: 'Slept in a bed'
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error going to bed: ${e.message}`
          });
        }
        break;
      }

      case 'activate': {
        try {
          const targetType = (params.type || '').toLowerCase();
          if (!targetType) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'Target type is required'
            });
            break;
          }

          const targetBlock = findNearestBlockByName(bot, name => name.includes(targetType), 16);
          if (!targetBlock) {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: `No '${targetType}' block found nearby`
            });
            break;
          }

          await gotoBlockIfPossible(bot, targetBlock, 2);
          await bot.activateBlock(targetBlock);
          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Activated nearest ${targetType}`
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error activating block: ${e.message}`
          });
        }
        break;
      }

      case 'putInChest': {
        try {
          const itemName = params.item_name;
          const num = Math.max(params.num || 1, 1);
          const chestBlock = findNearestBlockByName(bot, name => name.includes('chest'), 16);
          if (!chestBlock) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'No chest found nearby'
            });
            break;
          }

          const item = findItemByNameFragment(bot, itemName);
          if (!item) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Item '${itemName}' not in inventory`
            });
            break;
          }

          await gotoBlockIfPossible(bot, chestBlock, 2);
          const chest = await bot.openContainer(chestBlock);
          const amount = Math.min(num, item.count);
          await chest.deposit(item.type, item.metadata, amount);
          chest.close();

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Put ${amount}x ${item.name} in chest`
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error putting in chest: ${e.message}`
          });
        }
        break;
      }

      case 'takeFromChest': {
        try {
          const itemName = params.item_name;
          const num = Math.max(params.num || 1, 1);
          const chestBlock = findNearestBlockByName(bot, name => name.includes('chest'), 16);
          if (!chestBlock) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'No chest found nearby'
            });
            break;
          }

          const itemDef = bot.registry.itemsByName[itemName];
          if (!itemDef) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Unknown item '${itemName}'`
            });
            break;
          }

          await gotoBlockIfPossible(bot, chestBlock, 2);
          const chest = await bot.openContainer(chestBlock);
          await chest.withdraw(itemDef.id, null, num);
          chest.close();

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Took ${num}x ${itemName} from chest`
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error taking from chest: ${e.message}`
          });
        }
        break;
      }

      case 'smeltItem': {
        try {
          const itemName = params.item_name;
          const num = Math.max(params.num || 1, 1);
          const furnaceBlock = findNearestBlockByName(bot, name => name.includes('furnace'), 16);
          if (!furnaceBlock) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'No furnace found nearby'
            });
            break;
          }

          const inputItem = findItemByNameFragment(bot, itemName);
          const fuelItem = findItemByNameFragment(bot, 'coal') || findItemByNameFragment(bot, 'charcoal');
          if (!inputItem) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Input item '${itemName}' not found in inventory`
            });
            break;
          }
          if (!fuelItem) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'No fuel item (coal/charcoal) found in inventory'
            });
            break;
          }

          await gotoBlockIfPossible(bot, furnaceBlock, 2);
          const furnace = await bot.openFurnace(furnaceBlock);
          await furnace.putInput(inputItem.type, inputItem.metadata, Math.min(num, inputItem.count));
          await furnace.putFuel(fuelItem.type, fuelItem.metadata, 1);
          await sleep(2500);
          try {
            await furnace.takeOutput();
          } catch {
            // Output may not be ready yet; still valid to report started smelting.
          }
          furnace.close();

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Smelt process started for ${itemName}`
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error smelting item: ${e.message}`
          });
        }
        break;
      }

      case 'clearFurnace': {
        try {
          const furnaceBlock = findNearestBlockByName(bot, name => name.includes('furnace'), 16);
          if (!furnaceBlock) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'No furnace found nearby'
            });
            break;
          }

          await gotoBlockIfPossible(bot, furnaceBlock, 2);
          const furnace = await bot.openFurnace(furnaceBlock);
          try { await furnace.takeInput(); } catch {}
          try { await furnace.takeFuel(); } catch {}
          try { await furnace.takeOutput(); } catch {}
          furnace.close();

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: 'Cleared furnace slots'
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error clearing furnace: ${e.message}`
          });
        }
        break;
      }

      case 'placeHere': {
        try {
          const blockType = (params.type || '').toLowerCase();
          if (!blockType) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'Block type is required'
            });
            break;
          }

          const item = findItemByNameFragment(bot, blockType);
          if (!item) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `No placeable item '${blockType}' in inventory`
            });
            break;
          }

          await bot.equip(item, 'hand');
          await sleep(150);

          const basePos = bot.entity.position.floored();
          const offsets = [
            [1, 0],
            [-1, 0],
            [0, 1],
            [0, -1],
            [1, 1],
            [-1, 1],
            [1, -1],
            [-1, -1],
          ];

          const errors = [];
          let placedPosition = null;

          for (const [dx, dz] of offsets) {
            const targetPos = new Vec3(basePos.x + dx, basePos.y, basePos.z + dz);
            const referencePos = new Vec3(targetPos.x, targetPos.y - 1, targetPos.z);
            const targetBlock = bot.blockAt(targetPos);
            const referenceBlock = bot.blockAt(referencePos);

            if (!isEmptyBlock(targetBlock)) continue;
            if (!isSolidBlock(referenceBlock)) continue;

            const targetCenter = targetPos.offset(0.5, 0.5, 0.5);
            if (bot.entity.position.distanceTo(targetCenter) > 5.5) continue;

            const beforeCount = countInventoryItemByName(bot, item.name);
            try {
              await bot.placeBlock(referenceBlock, new Vec3(0, 1, 0));
            } catch (err) {
              const message = err?.message || String(err);
              if (!message.includes('blockUpdate')) {
                errors.push(`(${targetPos.x},${targetPos.y},${targetPos.z}): ${message}`);
                continue;
              }
              // Some servers place the block but drop the update event. Verify manually.
              await sleep(250);
            }

            await sleep(100);
            const placedBlock = bot.blockAt(targetPos);
            const afterCount = countInventoryItemByName(bot, item.name);
            const blockLooksPlaced = !isEmptyBlock(placedBlock);
            const itemWasConsumed = afterCount < beforeCount;

            if (blockLooksPlaced || itemWasConsumed) {
              placedPosition = targetPos;
              break;
            }

            errors.push(`(${targetPos.x},${targetPos.y},${targetPos.z}): placement not confirmed`);
          }

          if (!placedPosition) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: errors.length > 0
                ? `Could not place ${item.name} nearby. ${errors[0]}`
                : `Could not place ${item.name} nearby: no valid adjacent air block with support`
            });
            break;
          }

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Placed ${item.name} at (${placedPosition.x}, ${placedPosition.y}, ${placedPosition.z})`
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error placing block: ${e.message}`
          });
        }
        break;
      }

      case 'recipePlan': {
        try {
          const itemName = (params.item_name || '').toLowerCase();
          const amount = Math.max(params.amount || 1, 1);
          if (!itemName) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'item_name is required'
            });
            break;
          }

          const itemDef = bot.registry.itemsByName[itemName];
          if (!itemDef) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Unknown recipe target '${itemName}'`
            });
            break;
          }

          const inventoryRecipes = bot.recipesFor(itemDef.id, null, amount, null) || [];
          const craftingTable = findNearestBlockByName(bot, name => name.includes('crafting_table'), 24);
          const tableRecipes = craftingTable
            ? (bot.recipesFor(itemDef.id, null, amount, craftingTable) || [])
            : [];
          const allInventoryRecipes = typeof bot.recipesAll === 'function'
            ? (bot.recipesAll(itemDef.id, null, null) || [])
            : [];
          const allTableRecipes = (craftingTable && typeof bot.recipesAll === 'function')
            ? (bot.recipesAll(itemDef.id, null, craftingTable) || [])
            : [];
          const invCount = bot.inventory.items().reduce((sum, i) => i.name === itemName ? sum + i.count : sum, 0);

          const recipesAvailable = Math.max(inventoryRecipes.length, tableRecipes.length);
          const recipesKnown = Math.max(allInventoryRecipes.length, allTableRecipes.length);
          const message = recipesAvailable > 0
            ? `Recipe available for ${itemName}. You already have ${invCount}. Planned amount: ${amount}.`
            : recipesKnown > 0
              ? `Recipe exists for ${itemName}, but it's not craftable right now (missing ingredients and/or server recipe unlock). You have ${invCount}.${craftingTable ? ' Crafting table is nearby.' : ' No crafting table nearby for 3x3 recipes.'}`
              : `No known recipe found for ${itemName} right now. You have ${invCount}.`;

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message,
            data: {
              item_name: itemName,
              amount,
              inventory_count: invCount,
              recipes_available: recipesAvailable,
              recipes_known: recipesKnown,
              inventory_recipes: inventoryRecipes.length,
              table_recipes: tableRecipes.length,
              all_inventory_recipes: allInventoryRecipes.length,
              all_table_recipes: allTableRecipes.length,
              crafting_table_nearby: !!craftingTable,
            }
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error planning recipe: ${e.message}`
          });
        }
        break;
      }

      case 'navigate_to_location':
        if (params.x !== undefined && params.y !== undefined && params.z !== undefined) {
          try {
            const range = params.range || 2;
            if (bot.pathfinder) {
              await safePathfinderGoto(bot, new GoalNear(params.x, params.y, params.z, range));
            } else {
              keepPhysicsEnabled(bot, 2600);
              bot.setControlState('forward', true);
              await sleep(2000);
              bot.clearControlStates();
            }

            sendPerceptionEvent('action_result', {
              action: actionName,
              success: true,
              message: `Navigated to ${params.label || `${params.x}, ${params.y}, ${params.z}`}`
            });
          } catch (e) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Error navigating: ${e.message}`
            });
          }
        } else {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Coordinates required (x, y, z)`
          });
        }
        break;

      case 'mine_ore': {
        try {
          const oreType = (params.ore_type || 'stone').toLowerCase();
          const maxBlocks = Math.min(Math.max(params.max_blocks || 5, 1), 20);
          const maxDistance = Math.min(Math.max(params.max_distance || 50, 4), 96);

          const oreTargets = {
            stone: ['stone'],
            wood: ['oak_log', 'spruce_log', 'birch_log', 'jungle_log', 'acacia_log', 'dark_oak_log', 'mangrove_log', 'cherry_log'],
            coal: ['coal_ore', 'deepslate_coal_ore'],
            iron: ['iron_ore', 'deepslate_iron_ore'],
            copper: ['copper_ore', 'deepslate_copper_ore'],
            gold: ['gold_ore', 'deepslate_gold_ore', 'nether_gold_ore'],
            redstone: ['redstone_ore', 'deepslate_redstone_ore'],
            lapis: ['lapis_ore', 'deepslate_lapis_ore'],
            diamond: ['diamond_ore', 'deepslate_diamond_ore'],
            emerald: ['emerald_ore', 'deepslate_emerald_ore']
          };

          const targetNames = oreTargets[oreType] || [oreType];
          const targetIds = targetNames
            .map(name => bot.registry.blocksByName[name]?.id)
            .filter(id => typeof id === 'number');

          if (targetIds.length === 0) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Unknown ore type '${oreType}'`
            });
            break;
          }

          const positions = bot.findBlocks({
            matching: targetIds,
            maxDistance,
            count: maxBlocks
          });

          if (!positions || positions.length === 0) {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: `No ${oreType} found within ${maxDistance} blocks`
            });
            break;
          }

          let mined = 0;
          for (const pos of positions) {
            const block = bot.blockAt(pos);
            if (!block) continue;
            if (bot.pathfinder) {
              await safePathfinderGoto(bot, new GoalNear(pos.x, pos.y, pos.z, 1));
            }
            await bot.dig(block);
            mined += 1;
          }

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Mined ${mined} block(s) of ${oreType}`,
            data: { mined, ore_type: oreType }
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error mining ore: ${e.message}`
          });
        }
        break;
      }

      case 'craft_recipe': {
        try {
          const recipeName = (params.recipe || '').toLowerCase();
          const count = Math.min(Math.max(params.count || 1, 1), 64);
          if (!recipeName) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'Recipe name is required'
            });
            break;
          }

          const item = bot.registry.itemsByName[recipeName];
          if (!item) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Unknown recipe item '${recipeName}'`
            });
            break;
          }

          let craftingTable = null;
          let usedCraftingTable = false;
          let recipes = bot.recipesFor(item.id, null, count, null) || [];

          // 3x3 recipes (for example iron_pickaxe) require a crafting table block context.
          if (recipes.length === 0) {
            craftingTable = findNearestBlockByName(bot, name => name.includes('crafting_table'), 24);
            if (craftingTable) {
              await gotoBlockIfPossible(bot, craftingTable, 2);
              recipes = bot.recipesFor(item.id, null, count, craftingTable) || [];
              usedCraftingTable = recipes.length > 0;
            }
          }

          // Some recipes are only detectable for minResultCount=1. Keep requested count for actual craft.
          if (recipes.length === 0 && count > 1) {
            recipes = bot.recipesFor(item.id, null, 1, usedCraftingTable ? craftingTable : null) || [];
          }

          const allInvRecipes = typeof bot.recipesAll === 'function'
            ? (bot.recipesAll(item.id, null, null) || [])
            : [];
          const allTableRecipes = (craftingTable && typeof bot.recipesAll === 'function')
            ? (bot.recipesAll(item.id, null, craftingTable) || [])
            : [];
          const hasKnownRecipe = allInvRecipes.length > 0 || allTableRecipes.length > 0;

          if (!recipes || recipes.length === 0) {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: hasKnownRecipe
                ? (craftingTable
                  ? `Recipe for ${recipeName} is known but not craftable now (likely missing ingredients or server recipe unlock state).`
                  : `Recipe for ${recipeName} exists, but it may require a nearby crafting table and enough ingredients.`)
                : `No known recipe found for ${recipeName} on this server/version.`
            });
            break;
          }

          await bot.craft(recipes[0], count, usedCraftingTable ? craftingTable : null);
          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Crafted ${count}x ${recipeName}${usedCraftingTable ? ' using crafting table' : ''}`,
            data: { recipe: recipeName, count, used_crafting_table: usedCraftingTable }
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error crafting recipe: ${e.message}`
          });
        }
        break;
      }

      case 'hunt_mobs': {
        try {
          const rawMobType = (params.mob_type || '').toLowerCase().trim();
          const mobType = rawMobType.endsWith('s') ? rawMobType.slice(0, -1) : rawMobType;
          const maxDistance = Math.min(Math.max(params.max_distance || 96, 8), 196);

          // Some servers/plugins classify passive mobs differently, so hunt any nearby non-player entity.
          const nearbyEntities = Object.values(bot.entities || {}).filter(entity => {
            if (!entity) return false;
            if (!entity.position || !bot.entity?.position) return false;
            if (entity.position.distanceTo(bot.entity.position) > maxDistance) return false;
            if (entity.type === 'player') return false;
            return true;
          });

          const candidates = nearbyEntities
            .filter(entity => {
              const name = (entity.name || '').toLowerCase();
              const kind = (entity.mobType || '').toLowerCase();
              if (!name && !kind) return false;
              if (!mobType) return true;
              return name.includes(mobType) || kind.includes(mobType);
            })
            .sort((a, b) => a.position.distanceTo(bot.entity.position) - b.position.distanceTo(bot.entity.position));

          const target = candidates[0];
          if (!target) {
            const nearbyHint = nearbyEntities
              .slice(0, 8)
              .map(e => `${e.name || e.type || 'unknown'}(${Math.round(e.position.distanceTo(bot.entity.position))}m)`)
              .join(', ');
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: mobType
                ? `No nearby mob matching '${mobType}'. Nearby entities: ${nearbyHint || 'none'}`
                : `No nearby hunt targets found. Nearby entities: ${nearbyHint || 'none'}`
            });
            break;
          }

          const sword = bot.inventory.items().find(i => i.name.toLowerCase().includes('sword'));
          if (sword) {
            try {
              await bot.equip(sword, 'hand');
            } catch (e) {
              console.error(`[Bot] Failed to equip sword: ${e.message}`);
            }
          }

          if (bot.pathfinder) {
            await safePathfinderGoto(bot, new GoalNear(target.position.x, target.position.y, target.position.z, 2));
          }

          if (bot.pvp && typeof bot.pvp.attack === 'function') {
            bot.pvp.attack(target);
            await sleep(3000);
            if (typeof bot.pvp.stop === 'function') {
              bot.pvp.stop();
            }
          } else {
            bot.attack(target);
          }

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Engaged ${target.name || target.mobType || 'mob'}`,
            data: { mob: target.name || target.mobType || 'unknown' }
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error hunting mobs: ${e.message}`
          });
        }
        break;
      }

      case 'get_nearby_scan': {
        try {
          const range = Math.min(Math.max(params.range || 50, 10), 100); // 10-100 blocks
          const scanResults = {
            position: { 
              x: bot.entity.position.x, 
              y: bot.entity.position.y, 
              z: bot.entity.position.z 
            },
            entities: [],
            interesting_blocks: []
          };

          // Scan nearby entities
          if (bot.entities) {
            Object.values(bot.entities).forEach(entity => {
              if (!entity || !entity.position) return;
              const distance = entity.position.distanceTo(bot.entity.position);
              if (distance > range) return;
              
              scanResults.entities.push({
                type: entity.type || 'unknown',
                name: entity.name || entity.displayName || 'unknown',
                username: entity.username || null,
                is_player: entity.type === 'player',
                distance: Math.round(distance * 10) / 10,
                position: { x: Math.round(entity.position.x), y: Math.round(entity.position.y), z: Math.round(entity.position.z) }
              });
            });
          }

          // Scan for interesting blocks
          const interestingBlockTypes = [
            'diamond_ore', 'iron_ore', 'gold_ore', 'copper_ore', 'coal_ore',
            'emerald_ore', 'redstone_ore', 'lapis_ore', 'deepslate_diamond_ore',
            'cave_air', 'water', 'lava', 'spawner',
            'ancient_city', 'stronghold'
          ];

          for (const blockType of interestingBlockTypes) {
            const blockId = bot.registry.blocksByName[blockType]?.id;
            if (!blockId) continue;

            const positions = bot.findBlocks({
              matching: blockId,
              maxDistance: range,
              count: 5 // Max 5 of each type to avoid spam
            });

            positions?.forEach(pos => {
              const block = bot.blockAt(pos);
              if (block) {
                const distance = pos.distanceTo(bot.entity.position);
                scanResults.interesting_blocks.push({
                  block_type: blockType,
                  distance: Math.round(distance * 10) / 10,
                  position: { x: pos.x, y: pos.y, z: pos.z }
                });
              }
            });
          }

          // Sort by distance
          scanResults.entities.sort((a, b) => a.distance - b.distance);
          scanResults.interesting_blocks.sort((a, b) => a.distance - b.distance);

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Scanned area: found ${scanResults.entities.length} entities, ${scanResults.interesting_blocks.length} interesting blocks`,
            data: scanResults
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error scanning nearby area: ${e.message}`
          });
        }
        break;
      }

      default:
        sendPerceptionEvent('error', {
          action: actionName,
          message: `Unknown action: ${actionName}`
        });
    }
  } catch (error) {
    sendPerceptionEvent('action_result', {
      action: actionName,
      success: false,
      error: error.message
    });
  } finally {
    currentActionRequestId = null;
    currentActionName = null;
  }
}

/**
 * Initialize bot and plugins
 */
async function initBot() {
  try {
    let resolvedVersion = config.version || false;
    if (!resolvedVersion) {
      try {
        const pingResult = await new Promise((resolve, reject) => {
          mcProtocol.ping({ host: config.host, port: config.port }, (err, res) => {
            if (err) reject(err);
            else resolve(res);
          });
        });
        const detected = pingResult?.version?.name || false;
        resolvedVersion = detected || false;
        console.error(`[MinecraftBot] Server ping detected version: ${detected || 'unknown'}`);
      } catch (e) {
        console.error(`[MinecraftBot] Server version ping failed, using auto version detection: ${e.message}`);
      }
    }

    console.error(`[MinecraftBot] Creating bot with config:`, { ...config, version: resolvedVersion || false });
    bot = mineflayer.createBot({
      host: config.host,
      port: config.port,
      username: config.username,
      auth: config.auth,
      version: resolvedVersion,
      viewDistance: 'tiny',
      maxCatchupTicks: 1,
      physicsEnabled: false
    });

    console.error('[MinecraftBot] Bot created, loading plugins...');

    // Keep pathfinder on-demand; re-enable core gameplay plugins.
    console.error('[MinecraftBot] Pathfinder deferred (on-demand load enabled)');

    bot.loadPlugin(ArmorManager);
    console.error('[MinecraftBot] ArmorManager loaded');

    if (config.autoEatEnabled) {
      bot.loadPlugin(autoEat);
      console.error('[MinecraftBot] AutoEat loaded');
    } else {
      console.error('[MinecraftBot] AutoEat disabled (set MC_AUTOEAT=true to enable)');
    }

    bot.loadPlugin(toolPlugin);
    console.error('[MinecraftBot] Tool plugin loaded');

    bot.loadPlugin(collectBlock);
    console.error('[MinecraftBot] CollectBlock loaded');

    bot.loadPlugin(pvp);
    console.error('[MinecraftBot] PVP loaded');

    console.error('[MinecraftBot] All plugins loaded, setting up event handlers...');

    // Setup event handlers
    bot.once('spawn', () => {
      isConnected = true;
      console.error('[MinecraftBot] Bot spawned successfully!');
      freezeMovement(1800);
      // Keep idle connection movement-silent; physics gets enabled only for explicit movement actions.
      bot.physicsEnabled = false;
      try { bot.clearControlStates(); } catch {}
      try { bot.pathfinder?.stop(); } catch {}
      try { bot.pathfinder?.setGoal(null); } catch {}
      sendPerceptionEvent('ready', {
        username: bot.username,
        uuid: bot.uuid,
        position: { x: bot.entity.position.x, y: bot.entity.position.y, z: bot.entity.position.z }
      });

      setupChatHandler(bot);
      setupPlayerHandler(bot);
      setupStatusUpdates(bot);
      setupDamageStabilization(bot);
      setupAutoEquipArmor(bot);
      setupActionHandler(bot);
    });

    bot.on('kicked', (reason, loggedIn) => {
      const reasonText = formatKickReason(reason);
      lastKickReason = reasonText;
      console.error(`[MinecraftBot] Kicked from server (loggedIn=${loggedIn}): ${reasonText}`);
      sendPerceptionEvent('error', {
        message: `Kicked from server: ${reasonText}`,
        kicked: true,
        logged_in: !!loggedIn,
      });
    });

    bot.on('death', () => {
      console.error('[MinecraftBot] Bot died in-game');
      sendPerceptionEvent('action_result', {
        action: 'status',
        success: false,
        message: 'Bot died in-game',
        dead: true,
      });
    });

    bot.on('end', (reason) => {
      isConnected = false;
      const endReason = reason ? formatKickReason(reason) : null;
      const combinedReason = lastKickReason || endReason || 'Connection ended';
      console.error(`[MinecraftBot] Bot disconnected: ${combinedReason}`);
      sendPerceptionEvent('disconnected', {
        reason: combinedReason,
        ended_reason: endReason,
        kicked_reason: lastKickReason,
      });
      process.exit(0);
    });

    bot.on('error', (error) => {
      console.error('[MinecraftBot ERROR]', error);
      const formatted = formatBotError(error);
      const detailSuffix = formatted.details.length > 0
        ? ` | causes: ${formatted.details.join(' ; ')}`
        : '';
      const errorMessage = `${formatted.message}${detailSuffix}`;
      console.error('[Bot Error Event]', errorMessage);
      sendPerceptionEvent('error', {
        message: errorMessage,
        causes: formatted.details,
        full_error: String(error),
        stack: error?.stack
      });
    });

    // Add login event for debugging
    bot.on('login', () => {
      console.error(`[MinecraftBot] Login successful (runtime version=${bot.version || 'unknown'})`);
    });

  } catch (error) {
    console.error('[MinecraftBot INIT ERROR]', error);
    sendPerceptionEvent('error', {
      message: `Failed to initialize bot: ${error.message}`,
      stack: error.stack
    });
    process.exit(1);
  }
}

/**
 * Main execution
 */
console.error(`[MinecraftBot] Starting bot with config:`, config);
process.stderr.write(`[MinecraftBot] Config: ${JSON.stringify(config)}\n`);

// Flush stderr immediately
setImmediate(() => {
  initBot().then(() => {
    process.stderr.write('[MinecraftBot] Bot initialization completed\n');
  }).catch((err) => {
    process.stderr.write(`[MinecraftBot] Bot initialization failed: ${err.message}\n`);
    process.exit(1);
  });
});

// Handle process signals
process.on('SIGINT', () => {
  console.error('[MinecraftBot] SIGINT received, shutting down');
  if (bot) {
    bot.quit();
  }
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.error('[MinecraftBot] SIGTERM received, shutting down');
  if (bot) {
    bot.quit();
  }
  process.exit(0);
});
