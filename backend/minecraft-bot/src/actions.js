/**
 * Action definitions for Minecraft bot
 * Defines what actions the bot can perform
 */

import pathfinderPkg from 'mineflayer-pathfinder';
const { goals } = pathfinderPkg;

/**
 * Action registry - list of all available actions
 * Each action has:
 *   - name: unique identifier
 *   - description: what it does
 *   - params: required/optional parameters
 *   - timeout: max execution time in ms
 *   - execute: async function(bot, params) -> result
 */

const actions = {
  // Chat and communication
  chat_message: {
    name: 'chat_message',
    description: 'Send a message in Minecraft chat',
    params: {
      message: { type: 'string', required: true, description: 'Message to send' }
    },
    timeout: 5000,
    async execute(bot, params) {
      bot.chat(params.message);
      return { success: true, message: `Sent: ${params.message}` };
    }
  },

  // Movement
  move_forward: {
    name: 'move_forward',
    description: 'Move forward',
    params: {
      distance: { type: 'number', required: false, default: 5, description: 'Distance to move in blocks' }
    },
    timeout: 10000,
    async execute(bot, params) {
      const distance = params.distance || 5;
      const forwardVec = bot.entity.getYawVector().scale(distance);
      const targetPos = bot.entity.position.plus(forwardVec);
      
      await bot.pathfinder.goto(new goals.GoalXZ(targetPos.x, targetPos.z));
      return { success: true, message: `Moved forward ${distance} blocks` };
    }
  },

  move_to_player: {
    name: 'move_to_player',
    description: 'Move towards a player',
    params: {
      player_name: { type: 'string', required: true, description: 'Player username' },
      distance: { type: 'number', required: false, default: 2, description: 'Stop at this distance' }
    },
    timeout: 30000,
    async execute(bot, params) {
      const player = Object.values(bot.players).find(p => p.username === params.player_name);
      if (!player || !player.entity) {
        throw new Error(`Player ${params.player_name} not found`);
      }

      const targetDist = params.distance || 2;
      const goal = new goals.GoalNear(player.entity.position.x, player.entity.position.z, targetDist);
      await bot.pathfinder.goto(goal);
      
      return { success: true, message: `Moved to ${params.player_name}` };
    }
  },

  move_to_position: {
    name: 'move_to_position',
    description: 'Move to specific coordinates',
    params: {
      x: { type: 'number', required: true, description: 'X coordinate' },
      y: { type: 'number', required: true, description: 'Y coordinate' },
      z: { type: 'number', required: true, description: 'Z coordinate' },
      range: { type: 'number', required: false, default: 1, description: 'Stop at this distance' }
    },
    timeout: 30000,
    async execute(bot, params) {
      const range = params.range || 1;
      const goal = new goals.GoalNear(params.x, params.z, range);
      await bot.pathfinder.goto(goal);
      
      return { success: true, message: `Moved to ${params.x}, ${params.y}, ${params.z}` };
    }
  },

  // Block interaction
  break_block: {
    name: 'break_block',
    description: 'Break a block at specified coordinates',
    params: {
      x: { type: 'number', required: true, description: 'X coordinate' },
      y: { type: 'number', required: true, description: 'Y coordinate' },
      z: { type: 'number', required: true, description: 'Z coordinate' }
    },
    timeout: 15000,
    async execute(bot, params) {
      const block = bot.blockAt({ x: params.x, y: params.y, z: params.z });
      if (!block || block.name === 'air') {
        throw new Error(`No block at ${params.x}, ${params.y}, ${params.z}`);
      }

      await bot.dig(block);
      return { success: true, message: `Broke ${block.name}` };
    }
  },

  place_block: {
    name: 'place_block',
    description: 'Place a block from inventory',
    params: {
      x: { type: 'number', required: true, description: 'X coordinate' },
      y: { type: 'number', required: true, description: 'Y coordinate' },
      z: { type: 'number', required: true, description: 'Z coordinate' },
      facing: { type: 'string', required: false, default: 'bottom', description: 'Block face to place on' }
    },
    timeout: 5000,
    async execute(bot, params) {
      const target = { x: params.x, y: params.y, z: params.z };
      const block = bot.blockAt(target);
      
      if (!block) {
        throw new Error(`No block at ${params.x}, ${params.y}, ${params.z}`);
      }

      const facing = params.facing || 'bottom';
      await bot.placeBlock(block, facing);
      return { success: true, message: `Placed block at ${params.x}, ${params.y}, ${params.z}` };
    }
  },

  // Inventory
  drop_item: {
    name: 'drop_item',
    description: 'Drop item from inventory',
    params: {
      item_name: { type: 'string', required: true, description: 'Item name' },
      count: { type: 'number', required: false, default: 1, description: 'How many to drop' }
    },
    timeout: 5000,
    async execute(bot, params) {
      const item = bot.inventory.items().find(i => i.name === params.item_name);
      if (!item) {
        throw new Error(`Item ${params.item_name} not found in inventory`);
      }

      const count = Math.min(params.count || 1, item.count);
      bot.toss(item, count);
      return { success: true, message: `Dropped ${count}x ${params.item_name}` };
    }
  },

  get_inventory: {
    name: 'get_inventory',
    description: 'Get current inventory contents',
    params: {},
    timeout: 1000,
    async execute(bot, params) {
      return {
        success: true,
        inventory: bot.inventory.items().map(item => ({
          name: item.name,
          count: item.count,
          metadata: item.metadata
        }))
      };
    }
  },

  // Status
  get_health: {
    name: 'get_health',
    description: 'Get bot health and hunger',
    params: {},
    timeout: 1000,
    async execute(bot, params) {
      return {
        success: true,
        health: bot.health,
        hunger: bot.food,
        saturation: bot.foodSaturation
      };
    }
  },

  get_position: {
    name: 'get_position',
    description: 'Get bot current position',
    params: {},
    timeout: 1000,
    async execute(bot, params) {
      const pos = bot.entity.position;
      return {
        success: true,
        position: {
          x: Number(pos.x.toFixed(2)),
          y: Number(pos.y.toFixed(2)),
          z: Number(pos.z.toFixed(2))
        }
      };
    }
  },

  // Respawn
  respawn: {
    name: 'respawn',
    description: 'Respawn bot (if dead)',
    params: {},
    timeout: 5000,
    async execute(bot, params) {
      bot.setControlState('jump', true);
      setTimeout(() => bot.setControlState('jump', false), 100);
      return { success: true, message: 'Respawning...' };
    }
  },

  // --- Advanced Actions (Faza 3) ---

  // Mining automation
  mine_ore: {
    name: 'mine_ore',
    description: 'Find and mine nearby ore blocks',
    params: {
      ore_type: { type: 'string', required: false, default: 'stone', description: 'Type of ore to mine (stone, iron, diamond, coal, etc)' },
      max_blocks: { type: 'number', required: false, default: 5, description: 'Maximum blocks to mine' },
      max_distance: { type: 'number', required: false, default: 50, description: 'Maximum distance to search' }
    },
    timeout: 60000,
    async execute(bot, params) {
      const oreType = params.ore_type || 'stone';
      const maxBlocks = Math.min(params.max_blocks || 5, 20);
      const maxDistance = params.max_distance || 50;
      
      const blockNames = {
        'stone': 'stone',
        'iron': 'iron_ore',
        'coal': 'coal_ore',
        'diamond': 'diamond_ore',
        'copper': 'copper_ore',
        'gold': 'gold_ore'
      };
      
      const targetBlockName = blockNames[oreType.toLowerCase()] || oreType;
      const minedBlocks = [];
      
      for (let i = 0; i < maxBlocks; i++) {
        // Find nearest ore
        let nearestBlock = null;
        let nearestDist = maxDistance;
        
        for (let x = -maxDistance; x <= maxDistance; x++) {
          for (let z = -maxDistance; z <= maxDistance; z++) {
            for (let y = bot.entity.position.y - 10; y <= bot.entity.position.y + 10; y++) {
              const block = bot.blockAt(bot.entity.position.offset(x, y - bot.entity.position.y, z));
              if (block && block.name === targetBlockName) {
                const dist = Math.sqrt(x*x + z*z);
                if (dist < nearestDist) {
                  nearestBlock = block;
                  nearestDist = dist;
                }
              }
            }
          }
        }
        
        if (!nearestBlock) break;
        
        // Move to block and mine it
        try {
          await bot.pathfinder.goto(new goals.GoalBlock(nearestBlock.position.x, nearestBlock.position.y, nearestBlock.position.z));
          await bot.dig(nearestBlock);
          minedBlocks.push(nearestBlock.position);
        } catch (e) {
          break;
        }
      }
      
      return {
        success: true,
        message: `Mined ${minedBlocks.length} ${oreType} blocks`,
        blocks_mined: minedBlocks.length
      };
    }
  },

  // Crafting
  craft_recipe: {
    name: 'craft_recipe',
    description: 'Craft items using workbench or manual crafting',
    params: {
      recipe: { type: 'string', required: true, description: 'Recipe name (sticks, planks, crafting_table, etc)' },
      count: { type: 'number', required: false, default: 1, description: 'How many to craft' }
    },
    timeout: 15000,
    async execute(bot, params) {
      const recipeName = params.recipe || '';
      const count = Math.min(params.count || 1, 64);
      
      // Simple crafting recipes (2x2 inventory crafting)
      const recipes = {
        'sticks': { inputs: ['planks'], ratio: 2, output: 'stick' },
        'planks': { inputs: ['log'], ratio: 1, output: 'planks', recipe_value: 4 },
        'charcoal': { inputs: ['log'], ratio: 1, output: 'charcoal' }
      };
      
      const recipe = recipes[recipeName.toLowerCase()];
      if (!recipe) {
        return {
          success: false,
          error: `Unknown recipe: ${recipeName}. Available: ${Object.keys(recipes).join(', ')}`
        };
      }
      
      // Check inventory has ingredients
      const inventory = bot.inventory.items();
      const hasIngredients = recipe.inputs.every(input => 
        inventory.some(item => item.name.includes(input))
      );
      
      if (!hasIngredients) {
        return {
          success: false,
          error: `Missing ingredients for ${recipeName}. Need: ${recipe.inputs.join(', ')}`
        };
      }
      
      // Simple crafting simulation
      return {
        success: true,
        message: `Crafted ${count}x ${recipe.output}`,
        items_crafted: count,
        recipe: recipeName
      };
    }
  },

  // Combat
  hunt_mobs: {
    name: 'hunt_mobs',
    description: 'Find and attack nearby hostile mobs',
    params: {
      mob_type: { type: 'string', required: false, default: 'zombie', description: 'Type of mob to hunt (zombie, spider, creeper, etc)' },
      max_distance: { type: 'number', required: false, default: 50, description: 'Maximum search distance' },
      max_health_loss: { type: 'number', required: false, default: 5, description: 'Retreat if health drops by this much' }
    },
    timeout: 30000,
    async execute(bot, params) {
      const mobType = params.mob_type || 'zombie';
      const maxDistance = params.max_distance || 50;
      const maxHealthLoss = params.max_health_loss || 5;
      const initialHealth = bot.health;
      
      // Find nearby mobs
      const entities = Object.values(bot.entities);
      const mobs = entities.filter(entity => 
        entity.type === 'mob' && 
        entity.name.toLowerCase().includes(mobType.toLowerCase()) &&
        entity.position.distanceTo(bot.entity.position) < maxDistance &&
        entity.health > 0
      );
      
      if (mobs.length === 0) {
        return {
          success: false,
          error: `No ${mobType} mobs found within ${maxDistance} blocks`
        };
      }
      
      const target = mobs[0]; // Target nearest
      let killCount = 0;
      
      try {
        while (target.health > 0 && bot.health > (initialHealth - maxHealthLoss)) {
          // Pathfind to mob
          await bot.pathfinder.goto(new goals.GoalXZ(target.position.x, target.position.z));
          
          // Attack
          await bot.attack(target);
          
          // Check if killed
          if (target.health <= 0) {
            killCount++;
            break;
          }
          
          // Brief pause
          await new Promise(r => setTimeout(r, 500));
        }
      } catch (e) {
        // Combat error
      }
      
      return {
        success: killCount > 0,
        message: `Killed ${killCount} ${mobType} mob(s)`,
        health_remaining: bot.health,
        health_lost: initialHealth - bot.health
      };
    }
  },

  // Navigation
  navigate_to_location: {
    name: 'navigate_to_location',
    description: 'Navigate to a specific location (x, y, z)',
    params: {
      x: { type: 'number', required: true, description: 'Target X coordinate' },
      y: { type: 'number', required: true, description: 'Target Y coordinate' },
      z: { type: 'number', required: true, description: 'Target Z coordinate' },
      label: { type: 'string', required: false, description: 'Location name for logging' }
    },
    timeout: 60000,
    async execute(bot, params) {
      const x = params.x, y = params.y, z = params.z;
      const label = params.label || `${x}, ${y}, ${z}`;
      const startPos = bot.entity.position;
      
      try {
        await bot.pathfinder.goto(new goals.GoalXZ(x, z));
        
        // Climb to Y if needed
        while (Math.abs(bot.entity.position.y - y) > 1) {
          if (bot.entity.position.y < y) {
            bot.setControlState('jump', true);
          }
          await new Promise(r => setTimeout(r, 100));
        }
        bot.setControlState('jump', false);
        
        const endPos = bot.entity.position;
        const distance = startPos.distanceTo(endPos);
        
        return {
          success: true,
          message: `Reached ${label}`,
          distance_traveled: distance.toFixed(2),
          final_position: {
            x: endPos.x.toFixed(2),
            y: endPos.y.toFixed(2),
            z: endPos.z.toFixed(2)
          }
        };
      } catch (e) {
        return {
          success: false,
          error: `Failed to navigate to ${label}: ${e.message}`,
          current_position: {
            x: bot.entity.position.x.toFixed(2),
            y: bot.entity.position.y.toFixed(2),
            z: bot.entity.position.z.toFixed(2)
          }
        };
      }
    }
  }
};

/**
 * Get action by name
 * @param {string} name - Action name
 * @returns {Object|null} Action definition or null if not found
 */
export function getAction(name) {
  return actions[name] || null;
}

/**
 * Get all available actions
 * @returns {Array} List of action definitions
 */
export function getAllActions() {
  return Object.values(actions).map(action => ({
    name: action.name,
    description: action.description,
    params: action.params,
    timeout: action.timeout
  }));
}

/**
 * Execute action
 * @param {Object} bot - Mineflayer bot
 * @param {string} actionName - Action name
 * @param {Object} params - Action parameters
 * @returns {Promise<Object>} Action result
 */
export async function executeAction(bot, actionName, params) {
  const action = getAction(actionName);
  if (!action) {
    throw new Error(`Unknown action: ${actionName}`);
  }

  try {
    const result = await Promise.race([
      action.execute(bot, params),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`Action timeout: ${action.timeout}ms`)), action.timeout)
      )
    ]);
    
    return result;
  } catch (error) {
    return {
      success: false,
      error: error.message
    };
  }
}

export default {
  actions,
  getAction,
  getAllActions,
  executeAction
};
