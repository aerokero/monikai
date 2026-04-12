/**
 * Monika Perception System - Environmental Awareness
 * Tracks threats, resources, entities, and sends awareness events to Python
 */

export class MonikaPerception {
  constructor(bot, sendPerceptionEvent) {
    this.bot = bot;
    this.sendPerceptionEvent = sendPerceptionEvent;
    
    // Perception state
    this.knownEntities = new Map();
    this.knownResources = new Map();
    this.lastDamageSource = null;
    this.lastDamageTime = 0;
    this.damageStreak = 0;
    
    // Track what we've seen
    this.seenPlayers = new Set();
    this.seenMobs = new Set();
    
    // Throttling to prevent spam
    this.lastEnvironmentUpdateTime = 0;
    this.environmentUpdateInterval = 5000; // Only send every 5 seconds
    this.lastEntityCount = 0;
    this.lastEnvironmentSignature = '';
    this.lastThreatDetection = {};
  }

  /**
   * Update perception each tick
   */
  update() {
    this.updateEntities();
    this.updateResources();
    this.decayThreatMemory();
  }

  /**
   * Track all entities in the world (throttled)
   */
  updateEntities() {
    const entities = Object.values(this.bot.entities || {});
    
    // Classify entities
    const players = [];
    const mobs = [];
    const hostiles = [];
    const friendlies = [];
    
    for (const entity of entities) {
      if (!entity || !entity.position) continue;
      
      const dist = this.bot.entity.position.distanceTo(entity.position);
      
      if (entity.type === 'player') {
        players.push({ ...entity, distance: dist });
        this.seenPlayers.add(entity.name);
      } else if (entity.type === 'mob') {
        mobs.push({ ...entity, distance: dist, mobType: entity.mobType });
        
        // Classify threat level
        const hostile = ['creeper', 'zombie', 'skeleton', 'spider', 'phantom', 'drowned', 'warden', 'enderman'].some(
          m => entity.mobType?.includes(m)
        );
        
        if (hostile) {
          hostiles.push({ ...entity, distance: dist });
          
          // Send threat alert ONCE per mob (not every update)
          const mobKey = `${entity.id}`;
          if (!this.lastThreatDetection[mobKey] || Date.now() - this.lastThreatDetection[mobKey] > 10000) {
            if (dist < 32) {
              this.sendPerceptionEvent('threat_detected', {
                mobType: entity.mobType,
                distance: dist,
                position: { x: entity.position.x, y: entity.position.y, z: entity.position.z },
                dangerLevel: dist < 8 ? 'critical' : (dist < 16 ? 'high' : 'medium'),
              });
              this.lastThreatDetection[mobKey] = Date.now();
            }
          }
        } else {
          friendlies.push({ ...entity, distance: dist });
        }
        
        this.seenMobs.add(entity.mobType);
      }
    }
    
    // Only report environment if: 1) Time threshold passed, OR 2) Entity count changed significantly
    const now = Date.now();
    const entityCount = players.length + hostiles.length;
    const nearestThreat = hostiles.length > 0 ? Number(hostiles[0]?.distance?.toFixed(1)) : null;
    const nearestPlayer = players.length > 0 ? players[0]?.name : null;
    const signature = `${players.length}|${mobs.length}|${hostiles.length}|${nearestThreat}|${nearestPlayer || ''}`;
    const changed = signature !== this.lastEnvironmentSignature;

    if ((players.length > 0 || hostiles.length > 0) && (changed || now - this.lastEnvironmentUpdateTime > this.environmentUpdateInterval)) {
      this.sendPerceptionEvent('environment_update', {
        playersNearby: players.length,
        mobsNearby: mobs.length,
        hostileMobs: hostiles.length,
        nearestThreat,
        nearestPlayer,
      });
      this.lastEnvironmentUpdateTime = now;
      this.lastEnvironmentSignature = signature;
    }

    this.lastEntityCount = entityCount;
  }

  /**
   * Scan for nearby resources
   */
  updateResources() {
    const searchRadius = 32;
    const commonResources = ['stone', 'iron_ore', 'coal_ore', 'copper_ore', 'oak_log', 'spruce_log', 'dirt', 'gravel'];
    
    const found = [];
    for (let dx = -searchRadius; dx <= searchRadius; dx += 4) {
      for (let dz = -searchRadius; dz <= searchRadius; dz += 4) {
        const x = Math.floor(this.bot.entity.position.x) + dx;
        const y = Math.floor(this.bot.entity.position.y);
        const z = Math.floor(this.bot.entity.position.z) + dz;
        
        const block = this.bot.blockAt({x, y, z});
        if (block && commonResources.includes(block.name)) {
          const dist = Math.hypot(dx, dz);
          found.push({ name: block.name, distance: dist, position: {x, y, z} });
        }
      }
    }
    
    // Remember found resources
    if (found.length > 0) {
      for (const resource of found) {
        const key = `${resource.position.x},${resource.position.y},${resource.position.z}`;
        this.knownResources.set(key, resource);
      }
    }
  }

  /**
   * Process damage taken
   */
  processDamage(amount, source) {
    this.lastDamageTime = Date.now();
    this.damageStreak++;
    
    // Log damage details
    let sourceInfo = 'unknown source';
    if (source) {
      if (source.type === 'mob') {
        sourceInfo = `${source.mobType} at distance ${this.bot.entity.position.distanceTo(source.position).toFixed(1)}m`;
        this.lastDamageSource = source;
      } else if (source.type === 'player') {
        sourceInfo = `player ${source.name}`;
      }
    }
    
    this.sendPerceptionEvent('damage_received', {
      amount: amount,
      source: sourceInfo,
      health: this.bot.health,
      damageStreak: this.damageStreak,
      timestamp: this.lastDamageTime,
    });
  }

  /**
   * Decay threat memory over time
   */
  decayThreatMemory() {
    const now = Date.now();
    
    // Reset damage streak if it's been quiet for a while
    if (now - this.lastDamageTime > 10000) {
      this.damageStreak = 0;
    }
    
    // Clean up old resource marks
    for (const [key, resource] of this.knownResources) {
      if (now - resource.foundTime > 60000) {
        this.knownResources.delete(key);
      }
    }
  }

  /**
   * Get nearest resource of type
   */
  getNearestResource(resourceType) {
    let nearest = null;
    let minDist = Infinity;
    
    for (const resource of this.knownResources.values()) {
      if (resource.name === resourceType && resource.distance < minDist) {
        minDist = resource.distance;
        nearest = resource;
      }
    }
    
    return nearest;
  }

  /**
   * Get threat assessment
   */
  getThreatAssessment() {
    const entities = Object.values(this.bot.entities || {});
    const hostiles = entities.filter(e => 
      e?.type === 'mob' && ['creeper', 'zombie', 'skeleton', 'phantom'].some(m => e.mobType?.includes(m))
    );
    
    return {
      threatLevel: hostiles.length > 0 ? (hostiles.length > 2 ? 'high' : 'medium') : 'low',
      nearestThreat: hostiles.length > 0 ? hostiles[0]?.position : null,
      threatCount: hostiles.length,
    };
  }

  getAwareness() {
    return {
      seenPlayers: Array.from(this.seenPlayers),
      seenMobs: Array.from(this.seenMobs),
      knownResourceCount: this.knownResources.size,
      lastDamageSource: this.lastDamageSource?.mobType,
      damageStreak: this.damageStreak,
    };
  }
}

export default MonikaPerception;
