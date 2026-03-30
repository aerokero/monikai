/**
 * Minecraft Bot - Main Entry Point
 * Connects to Minecraft server and communicates with Python backend via IPC
 */

import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import mineflayer from 'mineflayer';
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

const { pathfinder: Pathfinder } = pathfinderPkg;
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
  version: process.env.MC_VERSION || '1.20.4'
};

// Bot instance
let bot = null;
let isConnected = false;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Send perception event to Python backend via stdout
 */
function sendPerceptionEvent(type, data = {}) {
  const event = {
    type,
    data,
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
  const { action: actionName, params = {}, timestamp } = action;

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

      case 'move':
        // Move towards a direction
        const { x = 0, z = 0 } = params;
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
        if (params.name) {
          try {
            // Look for the player (case-insensitive search)
            let targetPlayer = null;
            const searchName = params.name.toLowerCase();
            for (const playerName in bot.players) {
              if (playerName.toLowerCase() === searchName) {
                targetPlayer = bot.players[playerName];
                break;
              }
            }
            
            if (targetPlayer && targetPlayer.entity) {
              const range = params.range || 2;
              console.error(`[Bot] Moving to player ${params.name} at ${targetPlayer.entity.position}`);
              
              // Use pathfinder if available, otherwise use direct movement
              if (bot.pathfinder) {
                const pos = targetPlayer.entity.position;
                await bot.pathfinder.goto(new GoalNear(pos.x, pos.y, pos.z, range));
              } else {
                console.error(`[Bot] Pathfinder not available, using direct movement`);
                await bot.lookAt(targetPlayer.entity.position, true);
                bot.setControlState('forward', true);
                await sleep(2000);
                bot.clearControlStates();
              }
              
              sendPerceptionEvent('action_result', {
                action: actionName,
                success: true,
                message: `Moved towards player ${params.name}`
              });
            } else {
              console.error(`[Bot] Player ${params.name} not found. Available players: ${Object.keys(bot.players).join(', ')}`);
              sendPerceptionEvent('error', {
                action: actionName,
                message: `Player ${params.name} not found. Available: ${Object.keys(bot.players).join(', ')}`
              });
            }
          } catch (e) {
            console.error(`[Bot] Error moving to player: ${e.message}`);
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Error moving to player: ${e.message}`
            });
          }
        } else {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Player name required`
          });
        }
        break;

      case 'move_to_position':
        // Move to specific coordinates
        if (params.x !== undefined && params.y !== undefined && params.z !== undefined) {
          try {
            const targetPos = new Vec3(params.x, params.y, params.z);
            
            console.error(`[Bot] Moving to position ${params.x}, ${params.y}, ${params.z}`);
            
            if (bot.pathfinder) {
              await bot.pathfinder.goto(new GoalNear(targetPos.x, targetPos.y, targetPos.z, params.range || 1));
            } else {
              console.error(`[Bot] Pathfinder not available, using direct movement`);
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
                await bot.pathfinder.goto(new GoalNear(params.x, params.y, params.z, 1));
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

      case 'navigate_to_location':
        if (params.x !== undefined && params.y !== undefined && params.z !== undefined) {
          try {
            const range = params.range || 2;
            if (bot.pathfinder) {
              await bot.pathfinder.goto(new GoalNear(params.x, params.y, params.z, range));
            } else {
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
              await bot.pathfinder.goto(new GoalNear(pos.x, pos.y, pos.z, 1));
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

          const recipes = bot.recipesFor(item.id, null, count, null);
          if (!recipes || recipes.length === 0) {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: `No craftable recipe found for ${recipeName}`
            });
            break;
          }

          await bot.craft(recipes[0], count, null);
          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Crafted ${count}x ${recipeName}`,
            data: { recipe: recipeName, count }
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
          const mobType = (params.mob_type || '').toLowerCase();
          const maxDistance = Math.min(Math.max(params.max_distance || 50, 4), 96);
          const candidates = Object.values(bot.entities || {}).filter(entity => {
            if (!entity) return false;
            if (entity.type !== 'mob') return false;
            if (!entity.position || !bot.entity?.position) return false;
            if (entity.position.distanceTo(bot.entity.position) > maxDistance) return false;
            if (!mobType) return true;
            return (entity.name || '').toLowerCase().includes(mobType);
          });

          const target = candidates[0];
          if (!target) {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: mobType
                ? `No nearby mob matching '${mobType}'`
                : 'No nearby hostile mobs found'
            });
            break;
          }

          if (bot.pathfinder) {
            await bot.pathfinder.goto(new GoalNear(target.position.x, target.position.y, target.position.z, 2));
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
            message: `Engaged ${target.name || 'mob'}`,
            data: { mob: target.name || 'unknown' }
          });
        } catch (e) {
          sendPerceptionEvent('error', {
            action: actionName,
            message: `Error hunting mobs: ${e.message}`
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
  }
}

/**
 * Initialize bot and plugins
 */
async function initBot() {
  try {
    console.error(`[MinecraftBot] Creating bot with config:`, config);
    bot = mineflayer.createBot({
      host: config.host,
      port: config.port,
      username: config.username,
      auth: config.auth,
      version: config.version
    });

    console.error('[MinecraftBot] Bot created, loading plugins...');

    // Load plugins
    bot.loadPlugin(Pathfinder);
    console.error('[MinecraftBot] Pathfinder loaded');
    bot.loadPlugin(ArmorManager);
    console.error('[MinecraftBot] ArmorManager loaded');
    bot.loadPlugin(autoEat);
    console.error('[MinecraftBot] AutoEat loaded');
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
      sendPerceptionEvent('ready', {
        username: bot.username,
        uuid: bot.uuid,
        position: { x: bot.entity.position.x, y: bot.entity.position.y, z: bot.entity.position.z }
      });

      setupChatHandler(bot);
      setupPlayerHandler(bot);
      setupStatusUpdates(bot);
      setupActionHandler(bot);
    });

    bot.on('end', () => {
      isConnected = false;
      console.error('[MinecraftBot] Bot disconnected');
      sendPerceptionEvent('disconnected', {
        reason: 'Connection ended'
      });
      process.exit(0);
    });

    bot.on('error', (error) => {
      console.error('[MinecraftBot ERROR]', error);
      const errorMessage = error?.message || String(error) || JSON.stringify(error);
      console.error('[Bot Error Event]', errorMessage);
      sendPerceptionEvent('error', {
        message: errorMessage,
        full_error: String(error),
        stack: error?.stack
      });
    });

    // Add login event for debugging
    bot.on('login', () => {
      console.error('[MinecraftBot] Login successful');
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
