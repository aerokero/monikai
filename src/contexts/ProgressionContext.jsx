import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { useLanguage } from './LanguageContext';
import {
  formatMetrics,
  formatQuestsBySlot,
  formatAchievements,
  formatUnlocks,
} from '../utils/progressionTransformers';
import {
  registerProgressionSocketHandlers,
  unregisterProgressionSocketHandlers,
  emitQuestCompletion,
  emitProfileUpdate,
} from '../utils/progressionSocket';

const ProgressionContext = createContext();

export const useProgression = () => {
  const context = useContext(ProgressionContext);
  if (!context) {
    throw new Error('useProgression must be used within ProgressionProvider');
  }
  return context;
};

const API_BASE = 'http://localhost:8000/api/progression';

export const ProgressionProvider = ({ children, socket, pushToast }) => {
  const { lang } = useLanguage();
  
  // State for progression data
  const [profile, setProfileState] = useState(null);
  const [metrics, setMetricsState] = useState(null);
  const [quests, setQuestsState] = useState({ morning: [], afternoon: [], evening: [] });
  const [achievements, setAchievementsState] = useState({ unlocked: [], locked: [] });
  const [unlocks, setUnlocksState] = useState({ byCategory: {} });
  const [notifications, setNotificationsState] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // Refs to track initialization
  const hasInitialized = useRef(false);
  const socketRegisteredRef = useRef(false);

  // =====================================================================
  // Fetch Functions (on-demand, for initial load)
  // =====================================================================

  const fetchProfile = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/profile`);
      if (!res.ok) throw new Error('Failed to fetch profile');
      const data = await res.json();
      setProfileState(data);
      setError(null);
      return data;
    } catch (err) {
      console.error('[Progression] Failed to fetch profile:', err);
      setError(err.message);
    }
  }, []);

  const fetchMetrics = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/metrics`);
      if (!res.ok) throw new Error('Failed to fetch metrics');
      const data = await res.json();
      const formatted = formatMetrics(data);
      setMetricsState(formatted);
      setError(null);
      return formatted;
    } catch (err) {
      console.error('[Progression] Failed to fetch metrics:', err);
      setError(err.message);
    }
  }, []);

  const fetchQuests = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/quests/today`);
      if (!res.ok) throw new Error('Failed to fetch quests');
      const data = await res.json();
      const formatted = formatQuestsBySlot(data.quests || []);
      setQuestsState(formatted);
      setError(null);
      return formatted;
    } catch (err) {
      console.error('[Progression] Failed to fetch quests:', err);
      setError(err.message);
    }
  }, []);

  const fetchAchievements = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/achievements`);
      if (!res.ok) throw new Error('Failed to fetch achievements');
      const data = await res.json();
      const formatted = formatAchievements(data);
      setAchievementsState(formatted);
      setError(null);
      return formatted;
    } catch (err) {
      console.error('[Progression] Failed to fetch achievements:', err);
      setError(err.message);
    }
  }, []);

  const fetchUnlocks = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/unlocks`);
      if (!res.ok) throw new Error('Failed to fetch unlocks');
      const data = await res.json();
      const formatted = formatUnlocks(data);
      setUnlocksState(formatted);
      setError(null);
      return formatted;
    } catch (err) {
      console.error('[Progression] Failed to fetch unlocks:', err);
      setError(err.message);
    }
  }, []);

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/notifications`);
      if (!res.ok) throw new Error('Failed to fetch notifications');
      const data = await res.json();
      setNotificationsState(data.notifications || []);
      setError(null);
      return data.notifications;
    } catch (err) {
      console.error('[Progression] Failed to fetch notifications:', err);
      // Don't set error for non-critical notifications
    }
  }, []);

  const fetchAll = useCallback(async () => {
    setIsLoading(true);
    try {
      await Promise.all([
        fetchProfile(),
        fetchMetrics(),
        fetchQuests(),
        fetchAchievements(),
        fetchUnlocks(),
        fetchNotifications(),
      ]);
      setError(null);
    } catch (err) {
      console.error('[Progression] Failed to fetch progression data:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [fetchProfile, fetchMetrics, fetchQuests, fetchAchievements, fetchUnlocks, fetchNotifications]);

  // =====================================================================
  // Socket.io Integration
  // =====================================================================

  useEffect(() => {
    // Initial data fetch on mount (hydration)
    if (!hasInitialized.current) {
      fetchAll();
      hasInitialized.current = true;
    }

    // Register Socket.io handlers only once
    if (socket && !socketRegisteredRef.current) {
      const contextActions = {
        setMetrics: (data) => {
          if (data.metrics) {
            setMetricsState(data);
          }
        },
        setQuests: (data) => {
          if (data && typeof data === 'object') {
            setQuestsState(data);
          }
        },
        setAchievements: (data) => {
          if (data && (data.unlocked || data.locked)) {
            setAchievementsState(data);
          }
        },
        setUnlocks: (data) => {
          if (data && data.byCategory) {
            setUnlocksState(data);
          }
        },
        setNotifications: (data) => {
          setNotificationsState(Array.isArray(data) ? data : []);
        },
        pushToast,
      };

      registerProgressionSocketHandlers(socket, contextActions);
      socketRegisteredRef.current = true;
    }

    // Cleanup on unmount
    return () => {
      // Don't unregister handlers, keep listening for updates
      // Only unregister if component is truly unmounting (rare)
    };
  }, [socket, fetchAll, pushToast]);

  // =====================================================================
  // Action Methods
  // =====================================================================

  const completeQuest = useCallback((questId) => {
    if (socket) {
      emitQuestCompletion(socket, questId);
    }
  }, [socket]);

  const updateProfile = useCallback((profileFields) => {
    if (socket) {
      emitProfileUpdate(socket, profileFields);
    }
  }, [socket]);

  const clearNotifications = useCallback(() => {
    setNotificationsState([]);
  }, []);

  const removeNotification = useCallback((notificationId) => {
    setNotificationsState(prev => prev.filter(n => n.id !== notificationId));
  }, []);

  // =====================================================================
  // Context Value
  // =====================================================================

  const value = {
    // State
    profile,
    metrics,
    quests,
    achievements,
    unlocks,
    notifications,
    isLoading,
    error,

    // Fetch methods (on-demand)
    fetchProfile,
    fetchMetrics,
    fetchQuests,
    fetchAchievements,
    fetchUnlocks,
    fetchNotifications,
    fetchAll,

    // Action methods
    completeQuest,
    updateProfile,
    clearNotifications,
    removeNotification,
  };

  return (
    <ProgressionContext.Provider value={value}>
      {children}
    </ProgressionContext.Provider>
  );
};
