/**
 * Progression Socket.io Handlers
 * 
 * Registers Socket.io event listeners for progression system updates.
 * Called from App.jsx to enable real-time progression updates.
 */

import { formatMetrics, formatQuestsBySlot, formatAchievements, formatUnlocks } from './progressionTransformers';

/**
 * Register all progression Socket.io event handlers
 * @param {SocketIO.Socket} socket - Socket.io client instance
 * @param {Object} contextActions - ProgressionContext dispatch actions
 *        {
 *          setMetrics,
 *          setQuests,
 *          setAchievements,
 *          setUnlocks,
 *          setNotifications,
 *          pushToast (optional) - function to show toast
 *        }
 */
export const registerProgressionSocketHandlers = (socket, contextActions) => {
  if (!socket || !contextActions) {
    console.warn('[Progression Socket] Missing socket or context actions');
    return;
  }

  const {
    setMetrics,
    setQuests,
    setAchievements,
    setUnlocks,
    setNotifications,
    pushToast,
  } = contextActions;

  /**
   * Handle metrics update event
   * Emitted by backend when message is processed and metrics change
   */
  socket.on('metrics_updated', (data) => {
    console.log('[Progression Socket] metrics_updated:', data);
    
    if (data && data.metrics) {
      // Format metrics with thresholds
      const formatted = formatMetrics({
        metrics: Array.isArray(data.metrics) ? data.metrics : [data.metrics],
        progress: data.progress || {},
      });
      
      setMetrics(formatted);
      
      // Show toast for each metric updated
      if (Array.isArray(data.metrics)) {
        data.metrics.forEach(m => {
          if (m.xp_gain) {
            const xpAmount = Math.round(m.xp_gain);
            if (pushToast) {
              pushToast(
                `+${xpAmount} ${m.metric} XP`,
                'success',
                2000
              );
            }
          }
        });
      }
    }
  });

  /**
   * Handle quest completion event
   * Emitted by backend when quest is completed
   */
  socket.on('quest_completed', (data) => {
    console.log('[Progression Socket] quest_completed:', data);
    
    if (data && data.quest) {
      // Update the quest in list to mark as completed
      // In practice, we'd re-fetch quests, but for immediate UX we can update locally
      if (pushToast) {
        pushToast(
          `Quest Complete! +${Math.round(data.quest.reward_xp || 0)} ${data.quest.reward_metric} XP`,
          'success',
          3000
        );
      }
      
      // Emit event to re-fetch quests (easier than local state updates)
      socket.emit('request_quest_update');
    }
  });

  /**
   * Handle achievement unlocked event
   * Emitted by backend when achievement condition is met
   */
  socket.on('achievement_unlocked', (data) => {
    console.log('[Progression Socket] achievement_unlocked:', data);
    
    if (data && data.achievement) {
      if (pushToast) {
        pushToast(
          `🏆 Achievement Unlocked: ${data.achievement.title}`,
          'achievement',
          4000
        );
      }
      
      // Re-fetch achievements to update UI immediately
      socket.emit('request_achievement_update');
    }
  });

  /**
   * Handle unlock triggered event
   * Emitted by backend when feature unlock condition is met
   */
  socket.on('unlock_triggered', (data) => {
    console.log('[Progression Socket] unlock_triggered:', data);
    
    if (data && data.unlock) {
      if (pushToast) {
        pushToast(
          `⭐ New Feature Unlocked: ${data.unlock.label}`,
          'unlock',
          4000
        );
      }
      
      // Re-fetch unlocks
      socket.emit('request_unlock_update');
    }
  });

  /**
   * Handle story triggered event
   * Emitted by backend when story condition is met
   */
  socket.on('story_triggered', (data) => {
    console.log('[Progression Socket] story_triggered:', data);
    
    if (data && data.story) {
      if (pushToast) {
        pushToast(
          `📖 New Story: ${data.story.title || 'A new chapter'}`,
          'info',
          3000
        );
      }
    }
  });

  /**
   * Handle notification event
   * Emitted by backend to send notifications to frontend
   */
  socket.on('progression_notification', (data) => {
    console.log('[Progression Socket] progression_notification:', data);
    
    if (data && data.notification) {
      const notification = data.notification;
      
      // Add to notification queue
      setNotifications(prev => [
        ...(Array.isArray(prev) ? prev : []),
        {
          id: notification.id || Date.now(),
          type: notification.type || 'info',
          content: notification.content,
          timestamp: new Date().toISOString(),
        }
      ]);
      
      // Show toast if it's important
      if (notification.type === 'achievement' || notification.type === 'unlock') {
        if (pushToast) {
          pushToast(notification.content, notification.type, 3000);
        }
      }
    }
  });

  /**
   * Handle profile updated event
   * Emitted by backend when user profile is modified
   */
  socket.on('profile_updated', (data) => {
    console.log('[Progression Socket] profile_updated:', data);
    
    if (data && data.profile) {
      // Profile will be re-fetched when ProfileTab needs it
      if (pushToast) {
        pushToast('Profile updated', 'info', 2000);
      }
    }
  });

  /**
   * Handle batch progression update (for efficiency)
   * Emitted by backend with multiple progression updates at once
   */
  socket.on('progression_update_batch', (data) => {
    console.log('[Progression Socket] progression_update_batch:', data);
    
    const {
      metrics,
      quests,
      achievements,
      unlocks,
      notifications: notifs,
    } = data;
    
    // Update all state at once
    if (metrics) {
      const formatted = formatMetrics(metrics);
      setMetrics(formatted);
    }
    
    if (quests) {
      const formatted = formatQuestsBySlot(quests);
      setQuests(formatted);
    }
    
    if (achievements) {
      const formatted = formatAchievements(achievements);
      setAchievements(formatted);
    }
    
    if (unlocks) {
      const formatted = formatUnlocks(unlocks);
      setUnlocks(formatted);
    }
    
    if (notifs && Array.isArray(notifs)) {
      setNotifications(notifs.map(n => ({
        id: n.id || Date.now(),
        type: n.type || 'info',
        content: n.content,
        timestamp: new Date().toISOString(),
      })));
    }
  });

  /**
   * Error handler for progression events
   */
  socket.on('progression_error', (data) => {
    console.error('[Progression Socket] Error:', data);
    if (pushToast) {
      pushToast(
        `Progression error: ${data?.message || 'Unknown error'}`,
        'error',
        3000
      );
    }
  });

  console.log('[Progression Socket] Handlers registered successfully');
};

/**
 * Emit quest completion request to backend
 * @param {SocketIO.Socket} socket - Socket.io client
 * @param {string} questId - quest ID
 */
export const emitQuestCompletion = (socket, questId) => {
  if (!socket) return;
  socket.emit('complete_quest', { quest_id: questId });
};

/**
 * Emit profile update to backend
 * @param {SocketIO.Socket} socket - Socket.io client
 * @param {Object} profileFields - fields to update
 */
export const emitProfileUpdate = (socket, profileFields) => {
  if (!socket) return;
  socket.emit('update_profile', profileFields);
};

/**
 * Request fresh progression data from backend
 * @param {SocketIO.Socket} socket - Socket.io client
 * @param {string} dataType - 'all', 'metrics', 'quests', 'achievements', 'unlocks', 'profile', 'notifications'
 */
export const requestProgressionData = (socket, dataType = 'all') => {
  if (!socket) return;
  socket.emit('request_progression_data', { type: dataType });
};

/**
 * Unregister progression socket handlers
 * Useful for cleanup when component unmounts
 * @param {SocketIO.Socket} socket - Socket.io client
 */
export const unregisterProgressionSocketHandlers = (socket) => {
  if (!socket) return;
  
  const events = [
    'metrics_updated',
    'quest_completed',
    'achievement_unlocked',
    'unlock_triggered',
    'story_triggered',
    'progression_notification',
    'profile_updated',
    'progression_update_batch',
    'progression_error',
  ];
  
  events.forEach(event => socket.off(event));
  console.log('[Progression Socket] Handlers unregistered');
};

export default {
  registerProgressionSocketHandlers,
  emitQuestCompletion,
  emitProfileUpdate,
  requestProgressionData,
  unregisterProgressionSocketHandlers,
};
