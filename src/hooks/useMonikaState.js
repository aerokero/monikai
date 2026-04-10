/**
 * useMonikaState Hook
 * State machine for Monika's visual appearance
 * Coordinates context, personality, time, and animations
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useMonika } from '../contexts/MonikaContext';
import { getMonikaStateForContext, getSpritePath, IDLE_ANIMATIONS } from '../config/monikaStates';

/**
 * Hook managing Monika's complete visual state machine
 * @param {Object} personalityState - Backend personality data (mood, affection, energy)
 * @returns {Object} Current Monika visual state + UI info
 */
export const useMonikaState = (personalityState = {}) => {
  const { activeContext } = useMonika();

  // Track which context we're rendering for (to detect changes)
  const prevContextRef = useRef(activeContext);

  // Current sprite state
  const [spriteUrl, setSpriteUrl] = useState(() => 
    getSpritePath(activeContext)
  );

  // Animation state
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [idleAnimation, setIdleAnimation] = useState('idle');

  // Compute full Monika state (derived from context + personality + time)
  const monikaState = useMemo(() => {
    return getMonikaStateForContext(activeContext, personalityState);
  }, [activeContext, personalityState]);

  // Update sprite when context changes
  useEffect(() => {
    const contextChanged = prevContextRef.current !== activeContext;
    
    if (contextChanged) {
      // Fade out current sprite
      setIsTransitioning(true);

      // After fade duration, switch sprite
      const transitionTimeout = setTimeout(() => {
        setSpriteUrl(getSpritePath(activeContext));
        setIsTransitioning(false);
      }, 200); // Match CSS fade duration

      prevContextRef.current = activeContext;

      return () => clearTimeout(transitionTimeout);
    }
  }, [activeContext]);

  // Cycle idle animations
  useEffect(() => {
    const idleAnims = Object.keys(IDLE_ANIMATIONS);
    if (!idleAnims.length) return;

    // Rotate through animations every 3-5 seconds
    const animInterval = setInterval(() => {
      setIdleAnimation(prev => {
        const currentIndex = idleAnims.indexOf(prev);
        const nextIndex = (currentIndex + 1) % idleAnims.length;
        return idleAnims[nextIndex];
      });
    }, 3500);

    return () => clearInterval(animInterval);
  }, []);

  // Current animation config
  const animationConfig = useMemo(() => {
    return IDLE_ANIMATIONS[idleAnimation] || IDLE_ANIMATIONS.breathing;
  }, [idleAnimation]);

  return {
    // Sprite info
    spriteUrl,
    monikaState,
    activeContext,
    
    // Animation state
    isTransitioning,
    idleAnimation,
    animationConfig,
    
    // Style props
    transitionClass: isTransitioning ? 'monika-sprite--transitioning' : '',
    animationClass: `monika-sprite--${idleAnimation}`
  };
};

export default useMonikaState;
