/**
 * MonikaSprite Component
 * Transparent container for Monika sprite space
 * The actual character is rendered by Visualizer in MonikaShell behind the UI layers
 * This component reserves space and provides context awareness to the layout
 */

import React from 'react';
import useMonikaState from '../hooks/useMonikaState';
import '../styles/monika-layout.css';

/**
 * MonikaSprite
 * Transparent container that displays the sprite area
 * The actual character sprite is rendered by the Visualizer component behind MonikaLayout
 * 
 * This component:
 * - Reserves space for the character in the layout
 * - Provides responsive positioning
 * - Integrates context-aware state for potential future enhancements
 * 
 * @component
 * @param {number} scale - Sprite scale multiplier (0.7-1.0)
 * @param {string} className - Additional CSS classes
 * @param {Object} personalityState - Backend personality data (mood, affection, energy, etc)
 * @returns {React.ReactNode}
 */
const MonikaSprite = ({ 
  scale = 1.0,
  className = '',
  personalityState = {}
}) => {
  // Track state for future context-aware enhancements
  const {
    monikaState,
    activeContext,
  } = useMonikaState(personalityState);

  const containerStyle = {
    transform: `scale(${scale})`,
    width: '100%',
    height: '100%',
    transformOrigin: 'center bottom',
    // Transparent - let the Visualizer character show through
    background: 'transparent',
    pointerEvents: 'none'
  };

  return (
    <div 
      className={`monika-sprite-container ${className}`} 
      style={containerStyle}
      data-context={activeContext}
      data-state={monikaState?.outfit}
      role="img"
      aria-label={`Monika in ${activeContext} context`}
    >
      {/* Actual character is rendered by Visualizer behind this layout */}
      {/* This container reserves space and provides responsive positioning */}
    </div>
  );
};

export default React.memo(MonikaSprite);
