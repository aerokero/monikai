/**
 * useLayoutMode Hook
 * Detects current responsive layout mode and provides Monika configuration
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { getLayoutMode, getMonikaConfig, getRailConfig, getPanelConfig } from '../config/layoutConfig';

const RESIZE_DEBOUNCE_MS = 100;

/**
 * Hook to detect responsive layout mode and provide layout configuration
 * @returns {Object} Layout configuration object
 */
export const useLayoutMode = () => {
  const [viewport, setViewport] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 1024,
    height: typeof window !== 'undefined' ? window.innerHeight : 768,
    isPortrait: false
  });

  const [layoutMode, setLayoutMode] = useState(() => {
    if (typeof window !== 'undefined') {
      return getLayoutMode(window.innerWidth, window.innerHeight);
    }
    return 'desktop';
  });

  const [isPortrait, setIsPortrait] = useState(() => {
    if (typeof window !== 'undefined') {
      return window.innerHeight > window.innerWidth;
    }
    return false;
  });

  const resizeTimeoutRef = useRef(null);

  const handleResize = useCallback(() => {
    // Clear existing timeout
    if (resizeTimeoutRef.current) {
      clearTimeout(resizeTimeoutRef.current);
    }

    // Debounce resize handler
    resizeTimeoutRef.current = setTimeout(() => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      const newIsPortrait = height > width;
      const newLayoutMode = getLayoutMode(width, height);

      setViewport({
        width,
        height,
        isPortrait: newIsPortrait
      });

      setLayoutMode(newLayoutMode);
      setIsPortrait(newIsPortrait);

      // Dispatch custom event for components listening to layout changes
      window.dispatchEvent(new CustomEvent('layoutModeChanged', {
        detail: {
          layoutMode: newLayoutMode,
          width,
          height,
          isPortrait: newIsPortrait
        }
      }));
    }, RESIZE_DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    window.addEventListener('resize', handleResize);
    window.addEventListener('orientationchange', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('orientationchange', handleResize);
      if (resizeTimeoutRef.current) {
        clearTimeout(resizeTimeoutRef.current);
      }
    };
  }, [handleResize]);

  // Get configuration objects for current layout mode
  const monikaConfig = getMonikaConfig(layoutMode, viewport.width, viewport.height);
  const railConfig = getRailConfig(layoutMode);
  const panelConfig = getPanelConfig(layoutMode);

  return {
    // Viewport dimensions
    viewport,
    width: viewport.width,
    height: viewport.height,
    
    // Layout mode
    layoutMode,
    isPortrait,
    isDesktop: layoutMode === 'desktop' || layoutMode === 'desktop-wide',
    isTablet: layoutMode === 'tablet',
    isPhone: layoutMode === 'portrait' || layoutMode === 'landscape-phone',
    
    // Configuration objects
    monikaConfig,
    railConfig,
    panelConfig,
    
    // Utility functions
    getLayoutMode: () => layoutMode,
    getIsPortrait: () => isPortrait
  };
};

export default useLayoutMode;
