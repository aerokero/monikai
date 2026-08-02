/**
 * MonikaContext
 * Tracks which panel/context is currently active (rail nav selection).
 */

import React, { createContext, useState, useCallback } from 'react';
import { PANELS } from '../config/panelRegistry';

export const MonikaContext = createContext(null);

const CONTEXTS = Object.keys(PANELS);

export const MonikaContextProvider = ({ children }) => {
  const [activeContext, setActiveContext] = useState('chat');

  const setActiveContextHandler = useCallback((contextId) => {
    if (CONTEXTS.includes(contextId)) {
      setActiveContext(contextId);
    }
  }, []);

  const value = {
    activeContext,
    setActiveContext: setActiveContextHandler,
  };

  return (
    <MonikaContext.Provider value={value}>
      {children}
    </MonikaContext.Provider>
  );
};

export const useMonika = () => {
  const context = React.useContext(MonikaContext);
  if (!context) {
    throw new Error('useMonika must be used within MonikaContextProvider');
  }
  return context;
};

export default MonikaContextProvider;
