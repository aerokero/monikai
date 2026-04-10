/**
 * MonikaContext
 * Global context for Monika-First Adaptive UI state
 * Manages: activeContext, monikaState, panel registry, viewport info
 */

import React, { createContext, useState, useCallback } from 'react';

export const MonikaContext = createContext(null);

const CONTEXTS = ['chat', 'study', 'notes', 'daily_briefing', 'companion', 'goals'];

/**
 * MonikaContextProvider
 * Wraps app with Monika UI state management
 */
export const MonikaContextProvider = ({ children }) => {
  // Active context determines which panel/sprite is shown
  const [activeContext, setActiveContext] = useState('chat');

  // Panel registry: { panelId: { name, icon, contextKey, dock, visible, ... } }
  const [panelRegistry, setPanelRegistry] = useState({});

  // Panel visibility state: { panelId: boolean }
  const [panelVisibility, setPanelVisibilityState] = useState({
    chat: true,
    study: false,
    notes: false,
    daily_briefing: false,
    companion: false,
    goals: false
  });

  // Monika visual state (derived from activeContext + backend personality)
  const [monikaState, setMonikaState] = useState({
    spritePath: 'default',
    expression: 'neutral',
    mood: 'neutral',
    outfit: 'day',
    scale: 1.0,
    animationIdle: 'breathing'
  });

  /**
   * Set active context (which panel/sprite to show)
   */
  const setActiveContextHandler = useCallback((contextId) => {
    if (CONTEXTS.includes(contextId)) {
      setActiveContext(contextId);
      // Update visibility: show active, hide others
      setPanelVisibilityState(prev => ({
        ...prev,
        [contextId]: true,
        ...Object.fromEntries(CONTEXTS.map(c => [c, c === contextId]))
      }));
    }
  }, []);

  /**
   * Register a panel with metadata
   */
  const registerPanel = useCallback((panelId, metadata) => {
    setPanelRegistry(prev => ({
      ...prev,
      [panelId]: {
        id: panelId,
        name: metadata.name || panelId,
        icon: metadata.icon,
        contextKey: metadata.contextKey || panelId,
        dock: metadata.dock || 'side-panel',
        visible: metadata.visible !== false,
        priority: metadata.priority || 5,
        component: metadata.component,
        ariaLabel: metadata.ariaLabel || panelId,
        ...metadata
      }
    }));
  }, []);

  /**
   * Unregister a panel
   */
  const unregisterPanel = useCallback((panelId) => {
    setPanelRegistry(prev => {
      const next = { ...prev };
      delete next[panelId];
      return next;
    });
  }, []);

  /**
   * Update panel metadata
   */
  const updatePanel = useCallback((panelId, updates) => {
    setPanelRegistry(prev => ({
      ...prev,
      [panelId]: {
        ...prev[panelId],
        ...updates
      }
    }));
  }, []);

  /**
   * Set panel visibility
   */
  const setPanelVisibility = useCallback((panelId, isVisible) => {
    setPanelVisibilityState(prev => ({
      ...prev,
      [panelId]: isVisible
    }));
  }, []);

  /**
   * Toggle panel visibility
   */
  const togglePanelVisibility = useCallback((panelId) => {
    setPanelVisibilityState(prev => ({
      ...prev,
      [panelId]: !prev[panelId]
    }));
  }, []);

  /**
   * Update Monika visual state
   */
  const updateMonikaState = useCallback((state) => {
    setMonikaState(prev => ({
      ...prev,
      ...state
    }));
  }, []);

  const value = {
    // State
    activeContext,
    monikaState,
    panelRegistry,
    panelVisibility,

    // Setters
    setActiveContext: setActiveContextHandler,
    registerPanel,
    unregisterPanel,
    updatePanel,
    setPanelVisibility,
    togglePanelVisibility,
    updateMonikaState,

    // Utils
    getActivePanel: () => panelRegistry[activeContext],
    getAllPanels: () => Object.values(panelRegistry),
    isPanelVisible: (panelId) => panelVisibility[panelId] || false
  };

  return (
    <MonikaContext.Provider value={value}>
      {children}
    </MonikaContext.Provider>
  );
};

/**
 * Hook to use MonikaContext
 */
export const useMonika = () => {
  const context = React.useContext(MonikaContext);
  if (!context) {
    throw new Error('useMonika must be used within MonikaContextProvider');
  }
  return context;
};

export default MonikaContextProvider;
