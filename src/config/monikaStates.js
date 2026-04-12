/**
 * Monika States Configuration
 * Maps activeContext and personality state to sprite paths, expressions, and animations
 * Sprite source: public/vn/monika/ (served at /vn/monika/ by Vite)
 */

/**
 * Context-to-sprite mappings
 * Each context determines Monika's outfit, pose, expression
 */
export const MONIKA_STATES = {
  chat: {
    outfit: 'day',              // or 'school', 'casual', 'night'
    pose: 'talking',            // Expressive, engaged posture
    expression: 'happy',
    animationIdle: 'fidget',
    spriteFolder: 'vn/monika/day',
    spriteName: 'monika_talk',
    description: 'Chatting with user - playful and engaged'
  },
  study: {
    outfit: 'school',           // School uniform when studying
    pose: 'focused',            // Serious, focused posture
    expression: 'focused',
    animationIdle: 'reading',
    spriteFolder: 'vn/monika/school',
    spriteName: 'monika_study',
    description: 'Studying - focused and attentive'
  },
  notes: {
    outfit: 'day',
    pose: 'thinking',
    expression: 'thoughtful',
    animationIdle: 'reading',
    spriteFolder: 'vn/monika/day',
    spriteName: 'monika_think',
    description: 'Writing notes - reflective and organized'
  },
  daily_briefing: {
    outfit: 'day',
    pose: 'neutral',
    expression: 'focused',
    animationIdle: 'breathing',
    spriteFolder: 'vn/monika/day',
    spriteName: 'monika_neutral',
    description: 'Reviewing the briefing - calm and informed'
  },
  companion: {
    outfit: 'casual',
    pose: 'relaxed',
    expression: 'happy',
    animationIdle: 'fidget',
    spriteFolder: 'vn/monika/casual',
    spriteName: 'monika_relax',
    description: 'Companion activities - warm and playful'
  },
  goals: {
    outfit: 'day',
    pose: 'thinking',
    expression: 'thoughtful',
    animationIdle: 'weight_shift',
    spriteFolder: 'vn/monika/day',
    spriteName: 'monika_think',
    description: 'Checking progress - proud and attentive'
  },
  idle: {
    outfit: 'day',
    pose: 'idle',
    expression: 'happy',
    animationIdle: 'breathing',
    spriteFolder: 'vn/monika/day',
    spriteName: 'monika_idle',
    description: 'Idle state - calm and peaceful'
  }
};

/**
 * Time-of-day outfit mappings
 * Monika's outfit changes throughout the day
 */
export const TIME_OF_DAY_OUTFITS = {
  morning: {    // 6am - 11am
    outfit: 'casual_morning',
    mood: 'sleepy',
    expression: 'sleepy'
  },
  noon: {       // 11am - 4pm
    outfit: 'school',
    mood: 'energetic',
    expression: 'happy'
  },
  evening: {    // 4pm - 8pm
    outfit: 'casual',
    mood: 'reflective',
    expression: 'thoughtful'
  },
  night: {      // 8pm - 6am
    outfit: 'pajamas',
    mood: 'tired',
    expression: 'tired'
  }
};

/**
 * Mood-based expression overrides
 * Backend personality state can override expression
 */
export const MOOD_EXPRESSIONS = {
  happy: 'happy',
  sad: 'sad',
  angry: 'angry',
  neutral: 'neutral',
  playful: 'playful',
  thoughtful: 'thoughtful',
  loving: 'loving',
  confused: 'confused',
  tired: 'tired',
  focused: 'focused',
  listening: 'listening'
};

/**
 * Animation idle states
 * Loop animations while Monika is visible
 */
export const IDLE_ANIMATIONS = {
  breathing: {
    duration: 4000,  // ms
    keyframes: 'breathing'
  },
  fidget: {
    duration: 5000,
    keyframes: 'fidget'
  },
  reading: {
    duration: 6000,
    keyframes: 'reading'
  },
  weight_shift: {
    duration: 5000,
    keyframes: 'weight_shift'
  }
};

/**
 * Get current time-of-day period
 * @returns {string} 'morning' | 'noon' | 'evening' | 'night'
 */
const getTimeOfDay = () => {
  const now = new Date();
  const hour = now.getHours();
  
  if (hour >= 6 && hour < 11) return 'morning';      // 6am - 10:59am
  if (hour >= 11 && hour < 16) return 'noon';        // 11am - 3:59pm
  if (hour >= 16 && hour < 20) return 'evening';     // 4pm - 7:59pm
  return 'night';                                     // 8pm - 5:59am
};

/**
 * Get Monika state for a given context
 * Intelligently combines: context → base emotion → personality state → time of day
 * @param {string} contextId - Active context (chat, study, tasks, etc)
 * @param {Object} personalityState - From backend (mood, affection, energy, etc)
 * @returns {Object} Monika visual state (outfit, pose, expression, animation)
 */
export const getMonikaStateForContext = (contextId, personalityState = {}) => {
  const baseState = { ...MONIKA_STATES[contextId] || MONIKA_STATES.idle };
  
  // 1. Apply time-of-day outfit (first priority for outfit change)
  const currentTimeOfDay = personalityState.timeOfDay || getTimeOfDay();
  const timeOutfit = TIME_OF_DAY_OUTFITS[currentTimeOfDay];
  if (timeOutfit) {
    baseState.outfit = timeOutfit.outfit;
    // Time-based mood is secondary (can be overridden by personality)
    if (!personalityState.mood) {
      baseState.mood = timeOutfit.mood;
    }
  }

  // 2. Apply personality mood (overrides base + time mood if present)
  if (personalityState.mood) {
    const moodExpression = MOOD_EXPRESSIONS[personalityState.mood];
    if (moodExpression) {
      baseState.expression = moodExpression;
      baseState.mood = personalityState.mood;
    }
  }

  // 3. Apply affection level to pose/demeanor (optional enhancement)
  if (personalityState.affection !== undefined) {
    // High affection: relaxed poses
    // Low affection: reserved poses
    // This could adjust posture, but for now we keep it simple
  }

  return baseState;
};

/**
 * Get outfit path for given outfit name
 * @param {string} outfit - Outfit name (day, school, casual, etc)
 * @returns {string} Path to outfit folder
 */
export const getOutfitPath = (outfit = 'day') => {
  const outfitMap = {
    'day': 'vn/monika/day',
    'school': 'vn/monika/school',
    'casual': 'vn/monika/casual',
    'casual_morning': 'vn/monika/casual',
    'pajamas': 'vn/monika/pajamas',
    'casual_night': 'vn/monika/casual'
  };
  
  return outfitMap[outfit] || outfitMap['day'];
};

/**
 * Get sprite path for given context and customizations
 * @param {string} contextId - Context ID
 * @param {Object} overrides - Optional sprite overrides
 * @returns {string} Full sprite image path (e.g., /vn/monika/day/monika_talk.png)
 */
export const getSpritePath = (contextId, overrides = {}) => {
  const state = MONIKA_STATES[contextId] || MONIKA_STATES.idle;
  const folder = overrides.spriteFolder || state.spriteFolder;
  const name = overrides.spriteName || state.spriteName;
  
  // Return path to sprite image with .png extension
  // Sprite files are served from public/ by Vite, accessed at root (e.g., /vn/monika/...)
  return `/${folder}/${name}.png`;
};

export default {
  MONIKA_STATES,
  TIME_OF_DAY_OUTFITS,
  MOOD_EXPRESSIONS,
  IDLE_ANIMATIONS,
  getMonikaStateForContext,
  getOutfitPath,
  getSpritePath
};
