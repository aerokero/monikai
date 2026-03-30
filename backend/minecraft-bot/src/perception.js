/**
 * Perception helpers - Functions to read and report game state
 */

/**
 * Get nearby players information
 * @param {Object} bot - Mineflayer bot instance
 * @param {number} [maxDistance=32] - Maximum distance to scan
 * @returns {Array} Array of nearby players
 */
export function getNearbyPlayers(bot, maxDistance = 32) {
  const players = [];
  const botPos = bot.entity.position;

  Object.values(bot.players).forEach(player => {
    if (!player.entity) return;
    const distance = botPos.distanceTo(player.entity.position);
    
    if (distance <= maxDistance) {
      players.push({
        username: player.username,
        uuid: player.uuid,
        distance: Number(distance.toFixed(2)),
        position: {
          x: Number(player.entity.position.x.toFixed(2)),
          y: Number(player.entity.position.y.toFixed(2)),
          z: Number(player.entity.position.z.toFixed(2))
        },
        yaw: player.entity.yaw,
        pitch: player.entity.pitch,
        health: player.entity.metadata[8], // Health value
        heldItem: player.entity.heldItem ? player.entity.heldItem.name : null
      });
    }
  });

  return players;
}

/**
 * Get nearby blocks
 * @param {Object} bot - Mineflayer bot instance
 * @param {number} [radius=16] - Search radius
 * @returns {Array} Array of nearby blocks
 */
export function getNearbyBlocks(bot, radius = 16) {
  const blocks = [];
  const botPos = bot.entity.position;
  const centerX = Math.floor(botPos.x);
  const centerY = Math.floor(botPos.y);
  const centerZ = Math.floor(botPos.z);

  for (let x = centerX - radius; x <= centerX + radius; x++) {
    for (let y = centerY - radius; y <= centerY + radius; y++) {
      for (let z = centerZ - radius; z <= centerZ + radius; z++) {
        const block = bot.blockAt({x, y, z});
        if (block && block.name !== 'air') {
          const distance = botPos.distanceTo({x: x + 0.5, y: y + 0.5, z: z + 0.5});
          blocks.push({
            name: block.name,
            position: { x, y, z },
            distance: Number(distance.toFixed(2))
          });
        }
      }
    }
  }

  return blocks.slice(0, 50); // Limit to 50 closest blocks
}

/**
 * Get entity information (mobs, animals)
 * @param {Object} bot - Mineflayer bot instance
 * @param {number} [maxDistance=32] - Maximum distance to scan
 * @returns {Array} Array of nearby entities
 */
export function getNearbyEntities(bot, maxDistance = 32) {
  const entities = [];
  const botPos = bot.entity.position;

  Object.values(bot.entities).forEach(entity => {
    if (entity.id === bot.entity.id) return; // Skip self
    const distance = botPos.distanceTo(entity.position);
    
    if (distance <= maxDistance) {
      entities.push({
        id: entity.id,
        type: entity.type,
        name: entity.displayName || entity.type,
        distance: Number(distance.toFixed(2)),
        position: {
          x: Number(entity.position.x.toFixed(2)),
          y: Number(entity.position.y.toFixed(2)),
          z: Number(entity.position.z.toFixed(2))
        },
        yaw: entity.yaw,
        pitch: entity.pitch,
        health: entity.metadata[8], // Health for most mobs
        velocity: {
          x: Number((entity.velocity?.x || 0).toFixed(2)),
          y: Number((entity.velocity?.y || 0).toFixed(2)),
          z: Number((entity.velocity?.z || 0).toFixed(2))
        }
      });
    }
  });

  return entities;
}

/**
 * Get full game state snapshot
 * @param {Object} bot - Mineflayer bot instance
 * @returns {Object} Complete game state
 */
export function getGameStateSnapshot(bot) {
  const botPos = bot.entity.position;
  
  return {
    bot: {
      username: bot.username,
      uuid: bot.uuid,
      position: {
        x: Number(botPos.x.toFixed(2)),
        y: Number(botPos.y.toFixed(2)),
        z: Number(botPos.z.toFixed(2))
      },
      yaw: Number(bot.entity.yaw.toFixed(2)),
      pitch: Number(bot.entity.pitch.toFixed(2)),
      health: bot.health,
      hunger: bot.food,
      saturated: bot.foodSaturation,
      dimension: bot.game.dimension,
      difficulty: bot.game.difficulty,
      gameMode: bot.game.gameMode,
      isRaining: bot.isRaining
    },
    nearby: {
      players: getNearbyPlayers(bot, 32),
      entities: getNearbyEntities(bot, 32),
      blocks: getNearbyBlocks(bot, 16)
    },
    inventory: bot.inventory.items().map(item => ({
      slot: item.slot,
      name: item.name,
      count: item.count,
      damage: item.metadata
    }))
  };
}

/**
 * Check if position is safe (no fall damage)
 * @param {Object} bot - Mineflayer bot instance
 * @param {Object} pos - Position {x, y, z}
 * @returns {boolean} True if safe
 */
export function isPositionSafe(bot, pos) {
  const block = bot.blockAt(pos);
  const blockBelow = bot.blockAt({x: pos.x, y: pos.y - 1, z: pos.z});
  
  return block && block.name === 'air' && blockBelow && blockBelow.name !== 'air';
}

export default {
  getNearbyPlayers,
  getNearbyBlocks,
  getNearbyEntities,
  getGameStateSnapshot,
  isPositionSafe
};
