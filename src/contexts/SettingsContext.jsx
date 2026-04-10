import React, { createContext, useContext, useState, useCallback } from 'react';

const SettingsContext = createContext();

export const SettingsProvider = ({ children }) => {
  const [showSettings, setShowSettings] = useState(false);

  const openSettings = useCallback(() => setShowSettings(true), []);
  const closeSettings = useCallback(() => setShowSettings(false), []);
  const toggleSettings = useCallback(() => setShowSettings(prev => !prev), []);

  const value = {
    showSettings,
    setShowSettings,
    openSettings,
    closeSettings,
    toggleSettings,
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within SettingsProvider');
  }
  return context;
};

export default SettingsContext;
