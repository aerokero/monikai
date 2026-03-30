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

function findItemByNameFragment(bot, wantedName) {
  const wanted = (wantedName || '').toLowerCase();
  if (!wanted) return null;
  return bot.inventory.items().find(i => i.name.toLowerCase().includes(wanted)) || null;
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

async function gotoBlockIfPossible(bot, block, range = 2) {
  if (!block) return;
  if (!bot.pathfinder) return;
  await bot.pathfinder.goto(new GoalNear(block.position.x, block.position.y, block.position.z, range));
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
              await bot.pathfinder.goto(new GoalNear(pos.x, pos.y, pos.z, 1));
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
          const playerName = params.player_name;
          const itemName = params.item_name;
          const num = Math.max(params.num || 1, 1);
          const target = playerName ? bot.players[playerName]?.entity : null;
          const item = itemName ? bot.inventory.items().find(i => i.name === itemName) : null;
          if (!target) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Target player '${playerName}' not found`
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
            await bot.pathfinder.goto(new GoalNear(target.position.x, target.position.y, target.position.z, 2));
          }
          await bot.toss(item.type, null, Math.min(num, item.count));
          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Gave ${itemName} x${Math.min(num, item.count)} to ${playerName}`
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
          });

          const target = candidates[0];
          if (!target) {
            sendPerceptionEvent('action_result', {
              action: actionName,
              success: false,
              message: entityType ? `No nearby entity matching '${entityType}'` : 'No nearby attack target found'
            });
            break;
          }

          if (bot.pathfinder) {
            await bot.pathfinder.goto(new GoalNear(target.position.x, target.position.y, target.position.z, 2));
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
          const playerName = (params.player_name || '').toLowerCase();
          let targetPlayer = null;
          for (const name of Object.keys(bot.players || {})) {
            if (name.toLowerCase() === playerName) {
              targetPlayer = bot.players[name];
              break;
            }
          }
          if (!targetPlayer?.entity) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: `Player ${params.player_name} not found`
            });
            break;
          }

          const entity = targetPlayer.entity;
          if (bot.pathfinder) {
            await bot.pathfinder.goto(new GoalNear(entity.position.x, entity.position.y, entity.position.z, 2));
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
            message: `Attacked player ${targetPlayer.username}`
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
          const basePos = bot.entity.position.floored();
          const reference = bot.blockAt(new Vec3(basePos.x, basePos.y - 1, basePos.z));
          if (!reference) {
            sendPerceptionEvent('error', {
              action: actionName,
              message: 'No reference block under bot to place on'
            });
            break;
          }

          await bot.placeBlock(reference, new Vec3(0, 1, 0));
          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message: `Placed ${item.name} at current position`
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

          const recipes = bot.recipesFor(itemDef.id, null, amount, null) || [];
          const invCount = bot.inventory.items().reduce((sum, i) => i.name === itemName ? sum + i.count : sum, 0);

          const message = recipes.length > 0
            ? `Recipe available for ${itemName}. You already have ${invCount}. Planned amount: ${amount}.`
            : `No direct craftable recipe found for ${itemName} right now. You have ${invCount}.`;

          sendPerceptionEvent('action_result', {
            action: actionName,
            success: true,
            message,
            data: {
              item_name: itemName,
              amount,
              inventory_count: invCount,
              recipes_available: recipes.length,
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
