/**
 * Monika Personality System - Character Expression
 * Manages personality traits, dialogue, and emotional responses
 */

export class MonikaPersonality {
  constructor(sendPerceptionEvent) {
    this.sendPerceptionEvent = sendPerceptionEvent;
    
    // Personality traits
    this.traits = {
      courage: 0.6,      // How brave (0-1)
      curiosity: 0.8,    // How explorative (0-1)
      caution: 0.5,      // How careful (0-1)
      helpfulness: 0.9,  // How willing to help (0-1)
      sociability: 0.7,  // How talkative (0-1)
    };
    
    // Emotional state
    this.mood = 'neutral'; // neutral, happy, scared, curious, confident
    this.moodScore = 0;
    
    // Relationship tracking
    this.relationships = new Map(); // player -> affection score
    this.memories = [];
  }

  /**
   * Express personality through actions and dialogue
   */
  expressPersonality(situation, context) {
    let message = '';
    
    // React based on mood and situation
    switch (situation) {
      case 'threat_detected':
        if (this.traits.courage < 0.4) {
          message = `[Monika] Eek! I sensed danger... distance: ${context.distance}m`;
          this.setMood('scared', -0.5);
        } else {
          message = `[Monika] Threat detected! I'll keep watch.`;
          this.setMood('confident', 0.3);
        }
        break;
        
      case 'resource_found':
        if (this.traits.curiosity > 0.7) {
          message = `[Monika] Oh! I found ${context.resource}! Should we collect it?`;
          this.setMood('happy', 0.2);
        }
        break;
        
      case 'player_nearby':
        if (this.traits.sociability > 0.6) {
          const affection = this.relationships.get(context.player) || 0;
          if (affection > 5) {
            message = `[Monika] ${context.player}! Great to see you!`;
          } else {
            message = `[Monika] Hello, ${context.player}!`;
          }
          this.setMood('happy', 0.2);
        }
        break;
        
      case 'damage_taken':
        if (context.damageStreak > 3) {
          message = `[Monika] Ow! This is bad... I need to get away!`;
          this.setMood('scared', -0.8);
        } else {
          message = `[Monika] That hurt!`;
          this.setMood('scared', -0.3);
        }
        break;
        
      case 'task_completed':
        message = `[Monika] Done! I feel productive today.`;
        this.setMood('happy', 0.5);
        break;
        
      case 'exploration_start':
        if (this.traits.curiosity > 0.7) {
          message = `[Monika] I wonder what's out there... let's explore!`;
          this.setMood('curious', 0.3);
        }
        break;
    }
    
    if (message) {
      this.sendPerceptionEvent('personality_expression', {
        message: message,
        mood: this.mood,
        situation: situation,
      });
    }
  }

  /**
   * Set mood with decay
   */
  setMood(newMood, moodDelta = 0) {
    this.mood = newMood;
    this.moodScore = Math.max(-1, Math.min(1, this.moodScore + moodDelta));
  }

  /**
   * Update relationship with a player
   */
  updateRelationship(playerName, delta) {
    const current = this.relationships.get(playerName) || 0;
    this.relationships.set(playerName, current + delta);
    
    // Record memory
    this.memories.push({
      type: 'interaction',
      player: playerName,
      timestamp: Date.now(),
      delta: delta,
    });
  }

  /**
   * Express mood-based behavior
   */
  getMoodExpression() {
    const expressions = {
      'neutral': 'I\'m doing fine.',
      'happy': 'I\'m feeling great!',
      'scared': 'I\'m frightened...',
      'curious': 'I\'m wondering about things.',
      'confident': 'I feel strong today.',
    };
    return expressions[this.mood] || expressions['neutral'];
  }

  /**
   * Get decision bias based on personality
   */
  getDecisionBias() {
    return {
      willingnessToExplore: this.traits.curiosity * this.traits.courage,
      riskTolerance: this.traits.courage - this.traits.caution,
      willingnessToHelp: this.traits.helpfulness,
      socialEngagement: this.traits.sociability,
    };
  }

  /**
   * React to success or failure
   */
  reactToOutcome(success, context) {
    if (success) {
      this.expressPersonality('task_completed', { task: context?.task });
      this.setMood('happy', 0.3);
    } else {
      this.setMood('scared', -0.2);
    }
  }

  /**
   * Get personality state for Python
   */
  getState() {
    return {
      mood: this.mood,
      moodScore: this.moodScore,
      traits: this.traits,
      relationships: Object.fromEntries(this.relationships),
      memoryCount: this.memories.length,
      expression: this.getMoodExpression(),
    };
  }
}

export default MonikaPersonality;
