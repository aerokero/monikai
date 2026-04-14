/**
 * Progression Data Transformers
 * 
 * Converts backend API responses into component-friendly formats.
 * Handles formatting, grouping, and calculation of progression data.
 */

/**
 * Format a single metric into display-ready format
 * @param {Object} metric - backend metric object {metric, value, xp, streak_days, last_interaction, total_xp_earned}
 * @param {number} nextThreshold - next XP threshold for this metric
 * @returns {Object} formatted metric
 */
export const formatMetric = (metric, nextThreshold = null) => {
  if (!metric) return null;
  
  return {
    name: metric.metric, // 'affection', 'comfort', 'synergy', 'intimacy'
    value: Math.round(metric.value || 0),
    currentXP: Math.round(metric.xp || 0),
    nextThreshold: nextThreshold || 100,
    progress: Math.min((metric.value || 0) / (nextThreshold || 100), 1),
    streakDays: metric.streak_days || 0,
    lastInteraction: metric.last_interaction,
    totalXPEarned: metric.total_xp_earned || {},
    // For visual reference
    color: getMetricColor(metric.metric),
    icon: getMetricIcon(metric.metric),
  };
};

/**
 * Format all metrics into display-ready array with next thresholds
 * @param {Object} metricsResponse - backend response from /api/progression/metrics
 * @returns {Object} { metrics: Array, nextThresholds: Object }
 */
export const formatMetrics = (metricsResponse) => {
  if (!metricsResponse) return { metrics: [], nextThresholds: {} };
  
  const { metrics = [], progress = {} } = metricsResponse;
  
  // Thresholds per metric (from backend achievement definitions)
  const THRESHOLDS = {
    affection: [25, 50, 75, 100, 150, 200, 300],
    comfort: [25, 50, 75, 100, 150, 200],
    synergy: [25, 50, 75, 100, 150],
    intimacy: [25, 50, 75, 100, 150],
  };
  
  const formatMetricList = metrics.map(m => {
    const thresholds = THRESHOLDS[m.metric] || [];
    const nextThreshold = thresholds.find(t => t > m.value) || (Math.max(...thresholds) + 100);
    const prevThreshold = thresholds.filter(t => t <= m.value).pop() || 0;
    
    return {
      ...formatMetric(m, nextThreshold),
      prevThreshold,
      achievementsAtThreshold: progress[m.metric] || [],
    };
  });

  return {
    metrics: formatMetricList,
    nextThresholds: {
      affection: THRESHOLDS.affection,
      comfort: THRESHOLDS.comfort,
      synergy: THRESHOLDS.synergy,
      intimacy: THRESHOLDS.intimacy,
    },
  };
};

/**
 * Format quests list, grouped by time slot
 * @param {Array} questsArray - backend quests array
 * @returns {Object} { morning: [], afternoon: [], evening: [] }
 */
export const formatQuestsBySlot = (questsArray) => {
  if (!questsArray || !Array.isArray(questsArray)) {
    return { morning: [], afternoon: [], evening: [] };
  }
  
  const grouped = {
    morning: [],
    afternoon: [],
    evening: [],
  };
  
  questsArray.forEach(quest => {
    const slot = quest.slot || 'afternoon';
    if (grouped[slot]) {
      grouped[slot].push({
        id: quest.id,
        templateId: quest.template_id,
        title: quest.title,
        description: quest.description,
        type: quest.type,
        status: quest.status, // 'active', 'completed', 'expired', 'skipped'
        progress: quest.progress || 0,
        target: quest.target || 1,
        rewardMetric: quest.reward_metric,
        rewardXP: quest.reward_xp,
        createdAt: quest.created_at,
        completedAt: quest.completed_at,
        expiresAt: quest.expires_at,
        requiredBondLevel: quest.required_bond_level || 0,
        icon: getQuestSlotIcon(slot),
        slot,
      });
    }
  });
  
  // Sort by status (active first, then completed)
  Object.keys(grouped).forEach(slot => {
    grouped[slot].sort((a, b) => {
      const statusOrder = { active: 0, completed: 1, expired: 2, skipped: 3 };
      return (statusOrder[a.status] || 4) - (statusOrder[b.status] || 4);
    });
  });
  
  return grouped;
};

/**
 * Calculate remaining time for quest expiration
 * @param {string} expiresAt - ISO timestamp
 * @returns {Object} { hours, minutes, expired: boolean }
 */
export const calculateQuestExpiration = (expiresAt) => {
  if (!expiresAt) return { hours: 0, minutes: 0, expired: true };
  
  const now = new Date();
  const expTime = new Date(expiresAt);
  const diff = expTime - now;
  
  if (diff <= 0) return { hours: 0, minutes: 0, expired: true };
  
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  
  return { hours, minutes, expired: false };
};

/**
 * Format achievements into locked/unlocked with progress info
 * @param {Object} achievementsResponse - backend response from /api/progression/achievements
 * @returns {Object} { unlocked: [], locked: [], progress: {} }
 */
export const formatAchievements = (achievementsResponse) => {
  if (!achievementsResponse) return { unlocked: [], locked: [], progress: {} };
  
  const { unlocked = [], locked = [], progress = {} } = achievementsResponse;
  
  const formatAchievement = (ach, isUnlocked = false) => ({
    id: ach.id,
    title: ach.title,
    description: ach.description,
    icon: ach.icon,
    rarity: ach.rarity || 'common', // common, uncommon, rare, epic, legendary
    hidden: ach.hidden || false,
    type: ach.type, // 'stat_based', 'milestone', 'event'
    unlockedAt: ach.unlocked_at,
    condition: ach.condition,
    isUnlocked,
    progress: progress[ach.id] || {},
  });
  
  return {
    unlocked: unlocked.map(a => formatAchievement(a, true)),
    locked: locked.map(a => formatAchievement(a, false)),
    progress,
    lockedCount: locked.length,
    unlockedCount: unlocked.length,
    totalCount: unlocked.length + locked.length,
  };
};

/**
 * Get progress towards a locked achievement (e.g., metric threshold)
 * @param {Object} achievement - achievement object with condition
 * @param {Object} metrics - formatted metrics
 * @returns {Object} { currentValue, targetValue, progress: 0-1, metric }
 */
export const calculateAchievementProgress = (achievement, metrics) => {
  if (achievement.isUnlocked || !achievement.condition) {
    return { currentValue: 0, targetValue: 0, progress: 0 };
  }
  
  const cond = achievement.condition;
  
  if (cond.type === 'metric_threshold') {
    const metric = metrics?.find(m => m.name === cond.metric);
    if (!metric) return { currentValue: 0, targetValue: cond.value, progress: 0 };
    
    return {
      metric: cond.metric,
      currentValue: metric.value,
      targetValue: cond.value,
      progress: Math.min(metric.value / cond.value, 1),
      operator: cond.operator,
    };
  }
  
  return { currentValue: 0, targetValue: 0, progress: 0 };
};

/**
 * Format unlocks into categories with cascade info
 * @param {Object} unlocksResponse - backend response from /api/progression/unlocks
 * @param {Object} achievementsData - formatted achievements
 * @returns {Object} { byCategory: {...}, cascadeMap: {...} }
 */
export const formatUnlocks = (unlocksResponse, achievementsData = {}) => {
  if (!unlocksResponse) return { byCategory: {}, cascadeMap: {} };
  
  const { active_unlocks = [], available_unlocks = [], total_active = 0 } = unlocksResponse;
  
  const CATEGORIES = ['relationship', 'activities', 'narrative', 'gaming'];
  const byCategory = {};
  const cascadeMap = {}; // unlock_id -> triggering achievements
  
  CATEGORIES.forEach(cat => {
    byCategory[cat] = [];
  });
  
  // Process active unlocks
  active_unlocks.forEach(unlock => {
    const cat = unlock.category || 'relationship';
    if (byCategory[cat]) {
      byCategory[cat].push({
        id: unlock.id,
        label: unlock.label,
        description: unlock.description,
        category: cat,
        type: unlock.type,
        status: 'active',
        icon: unlock.icon,
        triggersOnUnlock: unlock.triggers_on_unlock || [],
        setsStoryFlags: unlock.sets_story_flags || [],
        order: unlock.order || 0,
      });
    }
  });
  
  // Process available unlocks (locked but requirements met)
  available_unlocks.forEach(unlock => {
    const cat = unlock.category || 'relationship';
    if (byCategory[cat]) {
      byCategory[cat].push({
        id: unlock.id,
        label: unlock.label,
        description: unlock.description,
        category: cat,
        type: unlock.type,
        status: 'available',
        requirements: unlock.requires || [],
        icon: unlock.icon,
        triggersOnUnlock: unlock.triggers_on_unlock || [],
        setsStoryFlags: unlock.sets_story_flags || [],
        order: unlock.order || 0,
      });
    }
  });
  
  // Sort each category by order
  CATEGORIES.forEach(cat => {
    byCategory[cat].sort((a, b) => (a.order || 0) - (b.order || 0));
  });
  
  return {
    byCategory,
    cascadeMap,
    activeCount: total_active,
    totalCount: active_unlocks.length + available_unlocks.length,
  };
};

/**
 * Get unlock cascade info (which achievements trigger which unlocks)
 * @param {Array} unlocksArray - all unlocks
 * @param {Array} achievementsArray - all achievements
 * @returns {Object} cascade mapping
 */
export const buildUnlockCascades = (unlocksArray = [], achievementsArray = []) => {
  const cascades = {};
  
  achievementsArray.forEach(ach => {
    cascades[ach.id] = {
      achievement: ach,
      triggersUnlocks: [],
      stories: [],
      flags: [],
    };
  });
  
  unlocksArray.forEach(unlock => {
    if (unlock.requires) {
      unlock.requires.forEach(req => {
        if (req.type === 'achievement' && cascades[req.id]) {
          cascades[req.id].triggersUnlocks.push(unlock);
          if (unlock.triggers_on_unlock) {
            unlock.triggers_on_unlock.forEach(trigger => {
              if (trigger.type === 'story') {
                cascades[req.id].stories.push(trigger);
              }
            });
          }
          if (unlock.sets_story_flags) {
            cascades[req.id].flags.push(...unlock.sets_story_flags);
          }
        }
      });
    }
  });
  
  return cascades;
};

/**
 * Helper: Get color for metric name
 */
export const getMetricColor = (metricName) => {
  const colors = {
    affection: 'from-pink-500 to-rose-400',
    comfort: 'from-cyan-500 to-sky-400',
    synergy: 'from-purple-500 to-violet-400',
    intimacy: 'from-amber-500 to-yellow-400',
  };
  return colors[metricName] || 'from-gray-500 to-slate-400';
};

/**
 * Helper: Get icon name for metric
 */
export const getMetricIcon = (metricName) => {
  const icons = {
    affection: '❤️',
    comfort: '🛡️',
    synergy: '✨',
    intimacy: '💫',
  };
  return icons[metricName] || '📊';
};

/**
 * Helper: Get icon for quest slot
 */
export const getQuestSlotIcon = (slot) => {
  const icons = {
    morning: '☀️',
    afternoon: '⚡',
    evening: '🌙',
  };
  return icons[slot] || '📋';
};

/**
 * Helper: Get rarity badge color
 */
export const getRarityColor = (rarity) => {
  const colors = {
    common: 'text-blue-400 border-blue-400/30 bg-blue-400/10',
    uncommon: 'text-green-400 border-green-400/30 bg-green-400/10',
    rare: 'text-purple-400 border-purple-400/30 bg-purple-400/10',
    epic: 'text-pink-400 border-pink-400/30 bg-pink-400/10',
    legendary: 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10',
  };
  return colors[rarity] || colors.common;
};

/**
 * Helper: Format timestamp to readable date
 */
export const formatTimestamp = (isoString) => {
  if (!isoString) return '';
  const date = new Date(isoString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

/**
 * Helper: Calculate days ago
 */
export const getDaysAgo = (isoString) => {
  if (!isoString) return 0;
  const date = new Date(isoString);
  const now = new Date();
  const diffTime = Math.abs(now - date);
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  return diffDays;
};

export default {
  formatMetric,
  formatMetrics,
  formatQuestsBySlot,
  calculateQuestExpiration,
  formatAchievements,
  calculateAchievementProgress,
  formatUnlocks,
  buildUnlockCascades,
  getMetricColor,
  getMetricIcon,
  getQuestSlotIcon,
  getRarityColor,
  formatTimestamp,
  getDaysAgo,
};
