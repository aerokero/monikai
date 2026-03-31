/**
 * Monika State Machine - Behavioral FSM
 * Manages behavior state transitions based on threats, goals, and environment
 */

export class MonikaStateMachine {
  constructor(bot) {
    this.bot = bot;
    this.currentState = 'idle';
    this.previousState = null;
    this.stateStartTime = Date.now();
    this.stateTimeout = 0;
    
    // State definitions
    this.states = {
      'idle': { onEnter: this.onEnterIdle, onUpdate: this.onUpdateIdle },
      'gathering': { onEnter: this.onEnterGathering, onUpdate: this.onUpdateGathering },
      'hunting': { onEnter: this.onEnterHunting, onUpdate: this.onUpdateHunting },
      'fleeing': { onEnter: this.onEnterFleeing, onUpdate: this.onUpdateFleeing },
      'crafting': { onEnter: this.onEnterCrafting, onUpdate: this.onUpdateCrafting },
      'defending': { onEnter: this.onEnterDefending, onUpdate: this.onUpdateDefending },
      'exploring': { onEnter: this.onEnterExploring, onUpdate: this.onUpdateExploring },
    };
    
    // State context
    this.context = {
      targetEntity: null,
      targetBlock: null,
      threatLevel: 0, // 0 = none, 1 = warning, 2 = danger, 3 = critical
      nearbyThreats: [],
      goal: null,
      taskQueue: [],
    };
  }

  /**
   * Update state machine each tick
   */
  update() {
    const desiredState = this.evaluateState();
    
    if (desiredState !== this.currentState) {
      this.transitionTo(desiredState);
    }
    
    // Call state update
    const stateHandler = this.states[this.currentState];
    if (stateHandler?.onUpdate) {
      stateHandler.onUpdate.call(this);
    }
  }

  /**
   * Evaluate which state we should be in
   */
  evaluateState() {
    // Priority-based state evaluation
    
    // 1. CRITICAL THREATS - Always flee
    if (this.context.threatLevel >= 3) {
      return 'fleeing';
    }
    
    // 2. ACTIVE THREATS - Defend or flee
    if (this.context.threatLevel >= 2) {
      const hostiles = this.context.nearbyThreats.filter(e => e.type === 'mob' && e.mobType?.includes('creeper'));
      if (hostiles.length > 0) return 'fleeing';
      return 'defending';
    }
    
    // 3. ACTIVE TASK
    if (this.context.taskQueue?.length > 0) {
      const currentTask = this.context.taskQueue[0];
      if (currentTask?.type === 'gather') return 'gathering';
      if (currentTask?.type === 'hunt') return 'hunting';
      if (currentTask?.type === 'craft') return 'crafting';
      if (currentTask?.type === 'explore') return 'exploring';
    }
    
    // 4. DEFAULT
    return 'idle';
  }

  /**
   * Transition to new state
   */
  transitionTo(newState) {
    if (newState === this.currentState) return;
    
    this.previousState = this.currentState;
    this.currentState = newState;
    this.stateStartTime = Date.now();
    
    console.error(`[StateMachine] Transition: ${this.previousState} → ${newState}`);
    
    const handler = this.states[newState];
    if (handler?.onEnter) {
      handler.onEnter.call(this);
    }
  }

  // STATE HANDLERS
  
  onEnterIdle() {
    console.error(`[Monika] I'm idling, waiting for tasks...`);
  }

  onUpdateIdle() {
    // Maybe look around occasionally
    if (Math.random() < 0.01) {
      const randomYaw = Math.random() * Math.PI * 2;
      this.bot.look(randomYaw, 0);
    }
  }

  onEnterGathering() {
    console.error(`[Monika] Starting gathering task: ${this.context.targetBlock?.name || 'resources'}`);
  }

  onUpdateGathering() {
    // Actively gathering - handled by python task system
  }

  onEnterHunting() {
    console.error(`[Monika] Hunting mode activated`);
  }

  onUpdateHunting() {
    // Track and attack mobs
  }

  onEnterFleeing() {
    console.error(`[Monika] FLEEING! Threat level: ${this.context.threatLevel}`);
    // Anti-cheat safe: avoid forcing raw movement flags from the state machine.
    // Higher-level actions (pathfinder/tasks) should decide movement strategy.
    this.bot.clearControlStates();

    if (this.bot.pathfinder) {
      this.bot.pathfinder.setGoal(null);
    }
  }

  onUpdateFleeing() {
    // Keep this state lightweight; avoid direct movement packet pressure.
    if (this.context.threatLevel < 1) {
      this.transitionTo('idle');
    }
  }

  onEnterCrafting() {
    console.error(`[Monika] Crafting...`);
  }

  onUpdateCrafting() {
    // Crafting in progress
  }

  onEnterDefending() {
    console.error(`[Monika] Defending against threats!`);
  }

  onUpdateDefending() {
    // Look at threats and fight back
    if (this.context.targetEntity) {
      this.bot.lookAt(this.context.targetEntity.position);
    }
  }

  onEnterExploring() {
    console.error(`[Monika] Exploring the world...`);
  }

  onUpdateExploring() {
    // Autonomous exploration
  }

  /**
   * Update threat level from perception data
   */
  updateThreatLevel(entities, health) {
    const hostiles = entities.filter(e => 
      e.type === 'mob' && ['creeper', 'zombie', 'skeleton', 'spider', 'enderman'].some(m => e.mobType?.includes(m))
    );
    
    this.context.nearbyThreats = hostiles;
    
    // Priority: Creepers are most dangerous
    const creepers = hostiles.filter(e => e.mobType?.includes('creeper'));
    if (creepers.length > 0) {
      const closest = creepers[0];
      const dist = this.bot.entity.position.distanceTo(closest.position);
      if (dist < 5) {
        this.context.threatLevel = 3; // CRITICAL
      } else if (dist < 16) {
        this.context.threatLevel = 2; // DANGER
      }
    }
    
    // Health check - below 25% is danger
    if (health < this.bot.health) {
      this.context.threatLevel = Math.max(this.context.threatLevel, 2);
    }
    
    // Decay threat over time
    if (hostiles.length === 0) {
      this.context.threatLevel = Math.max(0, this.context.threatLevel - 0.1);
    }
  }

  /**
   * Add task to queue
   */
  addTask(task) {
    this.context.taskQueue = this.context.taskQueue || [];
    this.context.taskQueue.push(task);
    console.error(`[Monika] Task added: ${task.type}. Queue length: ${this.context.taskQueue.length}`);
  }

  /**
   * Complete current task
   */
  completeTask() {
    if (this.context.taskQueue?.length > 0) {
      const completed = this.context.taskQueue.shift();
      console.error(`[Monika] Task completed: ${completed.type}`);
    }
  }

  getState() {
    return {
      currentState: this.currentState,
      previousState: this.previousState,
      threatLevel: this.context.threatLevel,
      taskCount: this.context.taskQueue?.length || 0,
      stateUptime: Date.now() - this.stateStartTime,
    };
  }
}

export default MonikaStateMachine;
