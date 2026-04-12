import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

const LayoutContext = createContext(null);

const getViewport = () => ({
  width: window.innerWidth,
  height: window.innerHeight,
});

export const LayoutProvider = ({ children }) => {
  const [viewport, setViewport] = useState(getViewport);
  const [panelRegistry, setPanelRegistry] = useState({});
  const [panelVisibility, setPanelVisibilityState] = useState({});
  const [activePanelId, setActivePanelId] = useState(null);

  useEffect(() => {
    const onResize = () => {
      setViewport(getViewport());
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const registerPanel = useCallback((panelId, config = {}) => {
    if (!panelId) return;
    setPanelRegistry((prev) => {
      if (prev[panelId]) return prev;
      return {
        ...prev,
        [panelId]: {
          dock: 'sheet',
          collapsed: false,
          priority: 0,
          ...config,
        },
      };
    });
  }, []);

  const updatePanel = useCallback((panelId, patch) => {
    if (!panelId) return;
    setPanelRegistry((prev) => {
      const current = prev[panelId] || { dock: 'sheet', collapsed: false, priority: 0 };
      return {
        ...prev,
        [panelId]: {
          ...current,
          ...(typeof patch === 'function' ? patch(current) : patch),
        },
      };
    });
  }, []);

  const setPanelVisibility = useCallback((panelId, isVisible) => {
    if (!panelId) return;
    setPanelVisibilityState((prev) => {
      if (prev[panelId] === Boolean(isVisible)) return prev;
      return {
        ...prev,
        [panelId]: Boolean(isVisible),
      };
    });
  }, []);

  const togglePanelVisibility = useCallback((panelId) => {
    if (!panelId) return;
    setPanelVisibilityState((prev) => ({
      ...prev,
      [panelId]: !prev[panelId],
    }));
  }, []);

  const value = useMemo(() => {
    const isPortrait = viewport.height >= viewport.width;
    return {
      viewport,
      isPortrait,
      panelRegistry,
      panelVisibility,
      activePanelId,
      setActivePanelId,
      registerPanel,
      updatePanel,
      setPanelVisibility,
      togglePanelVisibility,
    };
  }, [
    viewport,
    panelRegistry,
    panelVisibility,
    activePanelId,
    registerPanel,
    updatePanel,
    setPanelVisibility,
    togglePanelVisibility,
  ]);

  return <LayoutContext.Provider value={value}>{children}</LayoutContext.Provider>;
};

export const useLayout = () => {
  const ctx = useContext(LayoutContext);
  if (!ctx) {
    throw new Error('useLayout must be used inside LayoutProvider');
  }
  return ctx;
};
