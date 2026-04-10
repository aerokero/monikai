import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

const ModeContext = createContext(null);

const MODE_PRIORITY = {
  study: 3,
  forcedScene: 2,
  ambient: 1,
};

export const ModeProvider = ({ children }) => {
  const [studyMode, setStudyMode] = useState(false);
  const [forcedScene, setForcedScene] = useState({ scene: null, until: 0 });
  const [ambientScene, setAmbientScene] = useState('room');

  const setForcedSceneTTL = useCallback((scene, ttlMs) => {
    const duration = Math.max(0, Number(ttlMs || 0));
    setForcedScene({ scene, until: Date.now() + duration });
  }, []);

  const clearForcedScene = useCallback(() => {
    setForcedScene({ scene: null, until: 0 });
  }, []);

  const value = useMemo(() => {
    const now = Date.now();
    const hasForcedScene = !!forcedScene.scene && forcedScene.until > now;

    let resolvedScene = ambientScene;
    let resolvedSource = 'ambient';

    if (hasForcedScene) {
      resolvedScene = forcedScene.scene;
      resolvedSource = 'forcedScene';
    }

    if (studyMode) {
      resolvedScene = 'school';
      resolvedSource = 'study';
    }

    return {
      studyMode,
      setStudyMode,
      ambientScene,
      setAmbientScene,
      forcedScene,
      setForcedSceneTTL,
      clearForcedScene,
      resolvedScene,
      resolvedSource,
      hasForcedScene,
      modePriority: MODE_PRIORITY,
    };
  }, [studyMode, ambientScene, forcedScene, setForcedSceneTTL, clearForcedScene]);

  return <ModeContext.Provider value={value}>{children}</ModeContext.Provider>;
};

export const useMode = () => {
  const ctx = useContext(ModeContext);
  if (!ctx) {
    throw new Error('useMode must be used inside ModeProvider');
  }
  return ctx;
};
