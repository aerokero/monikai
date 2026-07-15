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
import * as Icons from '../icons';

const RailNav = () => {
  const { activeContext, setActiveContext } = useMonika();
  const { openSettings } = useSettings();
  const { isMuted, toggleMute, isVideoOn, toggleVideo, visionMode, toggleScreenCapture, isConnected, togglePower, onLogout, onMonikaTemporaryMood } = useAudioVideo();
  const { layoutMode } = useLayoutMode();
  const { t } = useLanguage();
  const canExpandRail = ['desktop', 'desktop-wide'].includes(layoutMode);
  const [isRailExpanded, setIsRailExpanded] = useState(false);
  const isExpanded = canExpandRail && isRailExpanded;
  
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
  const railPanelLabels = {
    chat: t('navigation.talk'),
    conversations: t('navigation.conversations'),
    notes: t('navigation.journal'),
    calendar: t('navigation.calendar'),
    profile: t('navigation.her_profile'),
  };
  const railButtonBase = `
    rail-button
    flex items-center justify-center
    transition-all duration-200
    group relative
    border
  `;
  const railButtonIdle = `
    bg-[rgba(255,238,212,0.035)]
    text-[rgba(255,240,218,0.62)]
    hover:bg-[rgba(232,178,102,0.08)]
    hover:text-[rgba(255,246,233,0.86)]
    border-[rgba(232,178,102,0.12)]
    hover:border-[rgba(232,178,102,0.24)]
  `;
  const railButtonActive = `
    bg-[linear-gradient(180deg,rgba(242,186,100,0.98),rgba(222,157,80,0.94))]
    text-[#20160f]
    border-[rgba(255,225,175,0.66)]
    shadow-[0_8px_22px_rgba(232,178,102,0.28)]
  `;
  const railButtonOn = `
    bg-[rgba(88,118,73,0.14)]
    text-[#9fbd8f]
    border-[rgba(146,174,126,0.38)]
    hover:bg-[rgba(88,118,73,0.22)]
    hover:text-[#c0d4ad]
  `;
  const railButtonWarn = `
    bg-[rgba(166,72,58,0.14)]
    text-[#df8978]
    border-[rgba(202,104,85,0.34)]
    hover:bg-[rgba(166,72,58,0.22)]
    hover:text-[#f0ad9d]
  `;
  const tooltipClassName = `
    rail-tooltip
    absolute left-full ml-2 px-2 py-1 rounded-md
    text-xs font-medium
    whitespace-nowrap pointer-events-none
    opacity-0 group-hover:opacity-100 transition-opacity
    z-50
  `;
  const renderLabel = (label, extraClassName = '') => {
    if (!canExpandRail) return null;
    return (
      <span className={`rail-button-label ${extraClassName}`}>
        {label}
      </span>
    );
  };
  const renderTooltip = (label) => (
    canExpandRail && !isExpanded ? (
      <div className={tooltipClassName}>
        {label}
      </div>
    ) : null
  );

  // Determine rail className based on layout mode
  const railClassName = {
    'desktop-wide': 'monika-rail--left-vertical',
    'desktop': 'monika-rail--left-vertical',
    'tablet': 'monika-rail--top-horizontal',
    'portrait': 'monika-rail--bottom-horizontal',
    'landscape-phone': 'monika-rail--bottom-horizontal'
  }[layoutMode] || 'monika-rail--left-vertical';

  return (
    <nav className={`monika-rail ${railClassName} ${isExpanded ? 'monika-rail--expanded' : ''}`} role="navigation" aria-label="Panel navigation">
      <div className="rail-buttons">
        {canExpandRail && (
          <button
            onClick={() => setIsRailExpanded((current) => !current)}
            className={`${railButtonBase} ${railButtonIdle} rail-toggle-button`}
            aria-label={isExpanded ? t('navigation.collapse') : t('navigation.expand')}
            aria-expanded={isExpanded}
            title={isExpanded ? t('navigation.collapse') : t('navigation.expand')}
          >
            <Icons.Maximize2 size={20} />
            <span className="rail-toggle-copy">
              <span className="rail-toggle-title">{t('navigation.title')}</span>
              <span className="rail-toggle-subtitle">{t('navigation.collapse_to_icons')}</span>
            </span>
            {renderTooltip(t('navigation.expand'))}
          </button>
        )}

        {panels.map((panel) => {
          const IconComponent = Icons[panel.icon] || Icons.Zap;
          const isActive = activeContext === panel.id;
          const label = railPanelLabels[panel.id] || t('panels.' + panel.id);

          return (
            <button
              key={panel.id}
              onClick={() => setActiveContext(panel.id)}
              className={`${railButtonBase} ${isActive ? railButtonActive : railButtonIdle}`}
              aria-label={panel.ariaLabel}
              title={t('panels.' + panel.id)}
              aria-current={isActive ? 'page' : undefined}
            >
              <IconComponent size={20} />
              {renderLabel(label)}
              
              {/* Tooltip label (shows on hover, desktop) */}
              {renderTooltip(label)}
            </button>
          );
        })}
        
        {/* Spacer to push audio/video and settings to bottom */}
        <div className="flex-grow"></div>
        
        {/* AI Power Button */}
        <button
          onClick={togglePower}
          className={`${railButtonBase} ${isConnected ? railButtonOn : railButtonWarn}`}
          aria-label="AI Power"
          title={isConnected ? t('tools.ai_on') : t('tools.ai_off')}
        >
          <Icons.Power size={20} />
          {renderLabel(isConnected ? t('navigation.connected') : t('navigation.disconnected'))}
          
          {renderTooltip(isConnected ? t('tools.ai_on') : t('tools.ai_off'))}
        </button>
        
        {/* Microphone Button */}
        <button
          onClick={toggleMute}
          className={`${railButtonBase} ${isMuted ? railButtonWarn : railButtonOn}`}
          aria-label="Microphone"
          title={isMuted ? t('tools.microphone_off') : t('tools.microphone_on')}
        >
          <Icons.Mic size={20} />
          {renderLabel(isMuted ? t('navigation.mic_muted') : t('navigation.mic'))}
          
          {renderTooltip(isMuted ? t('tools.microphone_off') : t('tools.microphone_on'))}
        </button>
        
        {/* Camera Button */}
        <button
          onClick={toggleVideo}
          className={`${railButtonBase} ${isVideoOn ? railButtonOn : railButtonIdle}`}
          aria-label="Camera"
          title={isVideoOn ? t('tools.camera_on') : t('tools.camera_off')}
        >
          <Icons.Video size={20} />
          {renderLabel(t('navigation.camera'))}
          
          {renderTooltip(isVideoOn ? t('tools.camera_on') : t('tools.camera_off'))}
        </button>
        
        {/* Screen Share Button */}
        <button
          onClick={toggleScreenCapture}
          className={`${railButtonBase} ${visionMode === 'screen' ? railButtonOn : railButtonIdle}`}
          aria-label="Screen Share"
          title={visionMode === 'screen' ? t('tools.share_screen_off') : t('tools.share_screen_on')}
        >
          <Icons.Share2 size={20} />
          {renderLabel(t('navigation.share'))}
          
          {renderTooltip(visionMode === 'screen' ? t('tools.share_screen_off') : t('tools.share_screen_on'))}
        </button>
        
        {/* Divider line */}
        <div className="rail-divider"></div>
        
        {/* Settings Button */}
        <button
          onClick={() => setActiveContext('settings')}
          className={`${railButtonBase} ${activeContext === 'settings' ? railButtonActive : railButtonIdle} mt-auto`}
          aria-label="Settings"
          title={t('tools.settings')}
        >
          <Icons.Settings size={20} />
          {renderLabel(t('tools.settings'))}
          
          {/* Tooltip label (shows on hover, desktop) */}
          {renderTooltip(t('tools.settings'))}
        </button>

        {/* Quit Button - Floats Away on Hover */}
        <button
          onMouseEnter={handleQuitMouseEnter}
          onMouseMove={handleQuitMouseMove}
          onMouseLeave={handleQuitMouseLeave}
          onClick={onLogout}
          className={`${railButtonBase} ${railButtonIdle} transition-all duration-100 pointer-events-auto cursor-pointer hover:bg-[rgba(166,72,58,0.18)] hover:text-[#f0ad9d]`}
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
          {renderLabel(t('tools.logout'))}
          
          {/* Tooltip label (shows on hover, desktop) */}
          {renderTooltip(isQuitHovered ? t('tools.dont_leave_me') : t('tools.logout'))}
        </button>
      </div>
    </nav>
  );
};

export default RailNav;
