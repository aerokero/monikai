import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useLanguage } from './LanguageContext';

const ProgressionContext = createContext();

export const useProgression = () => {
  const context = useContext(ProgressionContext);
  if (!context) {
    throw new Error('useProgression must be used within ProgressionProvider');
  }
  return context;
};

const API_BASE = 'http://localhost:8000/api/progression';

export const ProgressionProvider = ({ children }) => {
  const { lang } = useLanguage();
  
  const [profile, setProfile] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [quests, setQuests] = useState([]);
  const [achievements, setAchievements] = useState({ unlocked: [], locked: [] });
  const [unlocks, setUnlocks] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch profile
  const fetchProfile = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await fetch(`${API_BASE}/profile`);
      const data = await res.json();
      setProfile(data);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch profile:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch metrics
  const fetchMetrics = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/metrics`);
      const data = await res.json();
      setMetrics(data);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch metrics:', err);
      setError(err.message);
    }
  }, []);

  // Fetch today's quests
  const fetchQuests = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/quests/today`);
      const data = await res.json();
      setQuests(data.quests || []);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch quests:', err);
      setError(err.message);
    }
  }, []);

  // Fetch achievements
  const fetchAchievements = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/achievements`);
      const data = await res.json();
      setAchievements({
        unlocked: data.unlocked || [],
        locked: data.locked || [],
      });
      setError(null);
    } catch (err) {
      console.error('Failed to fetch achievements:', err);
      setError(err.message);
    }
  }, []);

  // Fetch unlocks
  const fetchUnlocks = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/unlocks`);
      const data = await res.json();
      setUnlocks(data.active_unlocks || []);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch unlocks:', err);
      setError(err.message);
    }
  }, []);

  // Fetch notifications
  const fetchNotifications = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/notifications`);
      const data = await res.json();
      setNotifications(data.notifications || []);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch notifications:', err);
    }
  }, []);

  // Fetch all data
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
      console.error('Failed to fetch progression data:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [fetchProfile, fetchMetrics, fetchQuests, fetchAchievements, fetchUnlocks, fetchNotifications]);

  // Auto-fetch on mount and every 10 seconds
  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 10000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const value = {
    profile,
    metrics,
    quests,
    achievements,
    unlocks,
    notifications,
    isLoading,
    error,
    fetchProfile,
    fetchMetrics,
    fetchQuests,
    fetchAchievements,
    fetchUnlocks,
    fetchNotifications,
    fetchAll,
  };

  return (
    <ProgressionContext.Provider value={value}>
      {children}
    </ProgressionContext.Provider>
  );
};
