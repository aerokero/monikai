/**
 * RailNav Component
 * Responsive navigation rail for panel selection
 * Adapts between left-vertical (desktop), top-horizontal (tablet), bottom-horizontal (portrait)
 */

import React, { useState } from 'react';
import { useMonika } from '../../contexts/MonikaContext';
import { useSettings } from '../../contexts/SettingsContext';
import { useAudioVideo } from '../../contexts/AudioVideoContext';
import { useLanguage } from '../../contexts/LanguageContext';
import useLayoutMode from '../../hooks/useLayoutMode';
import { getAllPanels } from '../../config/panelRegistry';
import * as Icons from 'lucide-react';

const RailNav = () => {
  const { activeContext, setActiveContext } = useMonika();
  const { openSettings } = useSettings();
  const { isMuted, toggleMute, isVideoOn, toggleVideo, visionMode, toggleScreenCapture, isConnected, togglePower, onLogout, onMonikaTemporaryMood } = useAudioVideo();
  const { layoutMode } = useLayoutMode();
  const { t } = useLanguage();
  
  // Quit button floating state
  const [quitHoverOffset, setQuitHoverOffset] = useState({ x: 0, y: 0 });
  const [isQuitHovered, setIsQuitHovered] = useState(false);
  
  // Handle quit button hover - make it float away and Monika angry
  const handleQuitMouseEnter = (e) => {
    setIsQuitHovered(true);
    // Make Monika angry when hovering near quit button
    if (onMonikaTemporaryMood) {
      onMonikaTemporaryMood('angry');
    }
    // Generate random floating position - reduced range to make it still clickable
    const randomX = (Math.random() - 0.5) * 60;
    const randomY = (Math.random() - 0.5) * 60;
    setQuitHoverOffset({ x: randomX, y: randomY });
  };
  
  const handleQuitMouseMove = (e) => {
    if (!isQuitHovered) return;
    // Re-randomize position on every move - smaller range so user can still catch it
    const randomX = (Math.random() - 0.5) * 70;
    const randomY = (Math.random() - 0.5) * 70;
    setQuitHoverOffset({ x: randomX, y: randomY });
  };
  
  const handleQuitMouseLeave = () => {
    setIsQuitHovered(false);
    setQuitHoverOffset({ x: 0, y: 0 });
    // Restore Monika to neutral mood when mouse leaves
    if (onMonikaTemporaryMood) {
      onMonikaTemporaryMood('neutral');
    }
  };
  
  const panels = getAllPanels().filter((panel) => !panel.hiddenInRail);

  // Determine rail className based on layout mode
  const railClassName = {
    'desktop-wide': 'monika-rail--left-vertical',
    'desktop': 'monika-rail--left-vertical',
    'tablet': 'monika-rail--top-horizontal',
    'portrait': 'monika-rail--bottom-horizontal',
    'landscape-phone': 'monika-rail--bottom-horizontal'
  }[layoutMode] || 'monika-rail--left-vertical';

  return (
    <nav className={`monika-rail ${railClassName}`} role="navigation" aria-label="Panel navigation">
      <div className="rail-buttons">
        {panels.map((panel) => {
          const IconComponent = Icons[panel.icon] || Icons.Zap;
          const isActive = activeContext === panel.id;

          return (
            <button
              key={panel.id}
              onClick={() => setActiveContext(panel.id)}
              className={`
                rail-button
                flex items-center justify-center
                p-3 rounded-lg
                transition-all duration-200
                group relative
                
                ${isActive
                  ? 'bg-monika-accent-primary/20 text-monika-accent-primary border border-monika-accent-primary/50'
                  : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80 border border-transparent'
                }
              `}
              aria-label={panel.ariaLabel}
              title={t('panels.' + panel.id)}
              aria-current={isActive ? 'page' : undefined}
            >
              <IconComponent size={20} />
              
              {/* Tooltip label (shows on hover, desktop) */}
              {['desktop', 'desktop-wide'].includes(layoutMode) && (
                <div className="
                  absolute left-full ml-2 px-2 py-1 rounded
                  bg-black/80 text-white/90 text-xs font-medium
                  whitespace-nowrap pointer-events-none
                  opacity-0 group-hover:opacity-100 transition-opacity
                  z-50
                ">
                  {t('panels.' + panel.id)}
                </div>
              )}
            </button>
          );
        })}
        
        {/* Spacer to push audio/video and settings to bottom */}
        <div className="flex-grow"></div>
        
        {/* AI Power Button */}
        <button
          onClick={togglePower}
          className={`
            rail-button
            flex items-center justify-center
            p-3 rounded-lg
            transition-all duration-200
            group relative
            ${isConnected
              ? 'bg-green-500/20 text-green-400 border border-green-500/50'
              : 'bg-red-500/20 text-red-400 border border-red-500/50'
            }
          `}
          aria-label="AI Power"
          title={isConnected ? t('tools.ai_on') : t('tools.ai_off')}
        >
          <Icons.Power size={20} />
          
          {['desktop', 'desktop-wide'].includes(layoutMode) && (
            <div className="
              absolute left-full ml-2 px-2 py-1 rounded
              bg-black/80 text-white/90 text-xs font-medium
              whitespace-nowrap pointer-events-none
              opacity-0 group-hover:opacity-100 transition-opacity
              z-50
            ">
              {isConnected ? t('tools.ai_on') : t('tools.ai_off')}
            </div>
          )}
        </button>
        
        {/* Microphone Button */}
        <button
          onClick={toggleMute}
          className={`
            rail-button
            flex items-center justify-center
            p-3 rounded-lg
            transition-all duration-200
            group relative
            ${isMuted
              ? 'bg-red-500/20 text-red-400 border border-red-500/50'
              : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80 border border-transparent'
            }
          `}
          aria-label="Microphone"
          title={isMuted ? t('tools.microphone_off') : t('tools.microphone_on')}
        >
          <Icons.Mic size={20} />
          
          {['desktop', 'desktop-wide'].includes(layoutMode) && (
            <div className="
              absolute left-full ml-2 px-2 py-1 rounded
              bg-black/80 text-white/90 text-xs font-medium
              whitespace-nowrap pointer-events-none
              opacity-0 group-hover:opacity-100 transition-opacity
              z-50
            ">
              {isMuted ? t('tools.microphone_off') : t('tools.microphone_on')}
            </div>
          )}
        </button>
        
        {/* Camera Button */}
        <button
          onClick={toggleVideo}
          className={`
            rail-button
            flex items-center justify-center
            p-3 rounded-lg
            transition-all duration-200
            group relative
            ${isVideoOn
              ? 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80 border border-transparent'
              : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80 border border-transparent'
            }
          `}
          aria-label="Camera"
          title={isVideoOn ? t('tools.camera_on') : t('tools.camera_off')}
        >
          <Icons.Video size={20} />
          
          {['desktop', 'desktop-wide'].includes(layoutMode) && (
            <div className="
              absolute left-full ml-2 px-2 py-1 rounded
              bg-black/80 text-white/90 text-xs font-medium
              whitespace-nowrap pointer-events-none
              opacity-0 group-hover:opacity-100 transition-opacity
              z-50
            ">
              {isVideoOn ? t('tools.camera_on') : t('tools.camera_off')}
            </div>
          )}
        </button>
        
        {/* Screen Share Button */}
        <button
          onClick={toggleScreenCapture}
          className={`
            rail-button
            flex items-center justify-center
            p-3 rounded-lg
            transition-all duration-200
            group relative
            ${visionMode === 'screen'
              ? 'bg-green-500/20 text-green-400 border border-green-500/50'
              : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80 border border-transparent'
            }
          `}
          aria-label="Screen Share"
          title={visionMode === 'screen' ? t('tools.share_screen_off') : t('tools.share_screen_on')}
        >
          <Icons.Share2 size={20} />
          
          {['desktop', 'desktop-wide'].includes(layoutMode) && (
            <div className="
              absolute left-full ml-2 px-2 py-1 rounded
              bg-black/80 text-white/90 text-xs font-medium
              whitespace-nowrap pointer-events-none
              opacity-0 group-hover:opacity-100 transition-opacity
              z-50
            ">
              {visionMode === 'screen' ? t('tools.share_screen_off') : t('tools.share_screen_on')}
            </div>
          )}
        </button>
        
        {/* Divider line */}
        <div className="w-8 h-px bg-white/10 my-2"></div>
        
        {/* Settings Button */}
        <button
          onClick={openSettings}
          className={`
            rail-button
            flex items-center justify-center
            p-3 rounded-lg
            transition-all duration-200
            group relative
            mt-auto
            bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80 border border-transparent
          `}
          aria-label="Settings"
          title={t('tools.settings')}
        >
          <Icons.Settings size={20} />
          
          {/* Tooltip label (shows on hover, desktop) */}
          {['desktop', 'desktop-wide'].includes(layoutMode) && (
            <div className="
              absolute left-full ml-2 px-2 py-1 rounded
              bg-black/80 text-white/90 text-xs font-medium
              whitespace-nowrap pointer-events-none
              opacity-0 group-hover:opacity-100 transition-opacity
              z-50
            ">
              {t('tools.settings')}
            </div>
          )}
        </button>

        {/* Quit Button - Floats Away on Hover */}
        <button
          onMouseEnter={handleQuitMouseEnter}
          onMouseMove={handleQuitMouseMove}
          onMouseLeave={handleQuitMouseLeave}
          onClick={onLogout}
          className={`
            rail-button
            flex items-center justify-center
            p-3 rounded-lg
            transition-all duration-100
            group relative
            bg-white/5 text-white/60 hover:bg-red-500/20 hover:text-red-400 border border-transparent
            pointer-events-auto cursor-pointer
          `}
          style={{
            transform: `translate(${quitHoverOffset.x}px, ${quitHoverOffset.y}px)`,
            transitionProperty: 'transform, background-color, color, border-color',
            transitionDuration: '100ms',
            transitionTimingFunction: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
          }}
          aria-label="Logout"
          title={t('tools.logout')}
        >
          <Icons.LogOut size={20} />
          
          {/* Tooltip label (shows on hover, desktop) */}
          {['desktop', 'desktop-wide'].includes(layoutMode) && (
            <div className="
              absolute left-full ml-2 px-2 py-1 rounded
              bg-black/80 text-white/90 text-xs font-medium
              whitespace-nowrap pointer-events-none
              opacity-0 group-hover:opacity-100 transition-opacity
              z-50
            ">
              {isQuitHovered ? t('tools.dont_leave_me') : t('tools.logout')}
            </div>
          )}
        </button>
      </div>
    </nav>
  );
};

export default RailNav;
