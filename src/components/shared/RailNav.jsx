/**
 * RailNav Component
 * Responsive navigation rail for panel selection
 * Adapts between left-vertical (desktop), top-horizontal (tablet), bottom-horizontal (portrait)
 */

import React, { useState } from 'react';
import { useMonika } from '../../contexts/MonikaContext';
import { useAudioVideo } from '../../contexts/AudioVideoContext';
import { useLanguage } from '../../contexts/LanguageContext';
import useLayoutMode from '../../hooks/useLayoutMode';
import { getAllPanels } from '../../config/panelRegistry';
import * as Icons from '../icons';

const RAIL_BUTTON_BASE = `
  rail-button
  flex items-center justify-center
  transition-colors duration-150
  group relative
`;

// Flat nav-list treatment: no borders/boxes, no hover-lift. Idle items are
// transparent until hovered; active/on/warn carry a persistent soft tint
// instead of a filled button, matching how ChatGPT/Claude highlight the
// current sidebar item.
const RAIL_BUTTON_VARIANTS = {
  idle: `
    text-[rgba(255,240,218,0.58)]
    hover:bg-[rgba(255,238,212,0.06)]
    hover:text-[rgba(255,246,233,0.92)]
  `,
  active: `
    bg-[rgba(232,178,102,0.15)]
    text-[#f2c883]
    hover:bg-[rgba(232,178,102,0.2)]
  `,
  on: `
    bg-[rgba(126,166,104,0.15)]
    text-[#a8c896]
    hover:bg-[rgba(126,166,104,0.2)]
  `,
  warn: `
    bg-[rgba(166,72,58,0.14)]
    text-[#df8978]
    hover:bg-[rgba(166,72,58,0.2)]
  `,
};

const RAIL_TOOLTIP_CLASSNAME = `
  rail-tooltip
  absolute left-full ml-2 px-2 py-1 rounded-md
  text-xs font-medium
  whitespace-nowrap pointer-events-none
  opacity-0 group-hover:opacity-100 transition-opacity
  z-50
`;

/**
 * RailButton
 * One rail entry: icon + optional expanded label + hover tooltip.
 * Shared by panel nav entries, the power/camera/share/settings toggles, and quit.
 */
const RailButton = React.forwardRef(({
  icon: Icon,
  label,
  tooltipLabel = label,
  variant = 'idle',
  canExpandRail,
  isExpanded,
  ariaLabel,
  ariaCurrent,
  className = '',
  style,
  children,
  ...rest
}, ref) => (
  <button
    ref={ref}
    style={style}
    className={`${RAIL_BUTTON_BASE} ${RAIL_BUTTON_VARIANTS[variant]} ${className}`}
    aria-label={ariaLabel}
    title={label}
    aria-current={ariaCurrent}
    {...rest}
  >
    <Icon size={20} />
    {canExpandRail && (children || <span className="rail-button-label">{label}</span>)}
    {canExpandRail && !isExpanded && (
      <div className={RAIL_TOOLTIP_CLASSNAME}>{tooltipLabel}</div>
    )}
  </button>
));

const RailNav = () => {
  const { activeContext, setActiveContext } = useMonika();
  const { isVideoOn, toggleVideo, visionMode, toggleScreenCapture, isConnected, togglePower, onLogout, onMonikaTemporaryMood } = useAudioVideo();
  const { layoutMode } = useLayoutMode();
  const { t } = useLanguage();
  const canExpandRail = ['desktop', 'desktop-wide'].includes(layoutMode);
  const [isRailExpanded, setIsRailExpanded] = useState(false);
  const isExpanded = canExpandRail && isRailExpanded;

  // Quit button floating state
  const [quitHoverOffset, setQuitHoverOffset] = useState({ x: 0, y: 0 });
  const [isQuitHovered, setIsQuitHovered] = useState(false);

  // Handle quit button hover - make it float away and Monika angry
  const handleQuitMouseEnter = () => {
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

  const handleQuitMouseMove = () => {
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
    worlds: t('navigation.worlds'),
    notes: t('navigation.journal'),
    companion: t('companion.tabs.activities'),
    calendar: t('navigation.calendar'),
    profile: t('navigation.her_profile'),
  };

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
          <RailButton
            onClick={() => setIsRailExpanded((current) => !current)}
            icon={isExpanded ? Icons.Minimize2 : Icons.Maximize2}
            label={isExpanded ? t('navigation.collapse') : t('navigation.expand')}
            className="rail-toggle-button"
            canExpandRail={canExpandRail}
            isExpanded={isExpanded}
            ariaLabel={isExpanded ? t('navigation.collapse') : t('navigation.expand')}
            aria-expanded={isExpanded}
          >
            <span className="rail-toggle-copy">
              <span className="rail-toggle-title">{t('navigation.title')}</span>
              <span className="rail-toggle-subtitle">{t('navigation.collapse_to_icons')}</span>
            </span>
          </RailButton>
        )}

        {panels.map((panel) => {
          const IconComponent = Icons[panel.icon] || Icons.Zap;
          const isActive = activeContext === panel.id;
          const label = railPanelLabels[panel.id] || t('panels.' + panel.id);

          return (
            <RailButton
              key={panel.id}
              onClick={() => setActiveContext(panel.id)}
              icon={IconComponent}
              label={label}
              variant={isActive ? 'active' : 'idle'}
              canExpandRail={canExpandRail}
              isExpanded={isExpanded}
              ariaLabel={panel.ariaLabel}
              ariaCurrent={isActive ? 'page' : undefined}
            />
          );
        })}

        {/* Spacer to push audio/video and settings to bottom */}
        <div className="flex-grow"></div>

        {/* AI Power Button */}
        <RailButton
          onClick={togglePower}
          icon={Icons.Power}
          label={isConnected ? t('navigation.connected') : t('navigation.disconnected')}
          tooltipLabel={isConnected ? t('tools.ai_on') : t('tools.ai_off')}
          variant={isConnected ? 'on' : 'warn'}
          canExpandRail={canExpandRail}
          isExpanded={isExpanded}
          ariaLabel="AI Power"
        />

        {/* Camera Button */}
        <RailButton
          onClick={toggleVideo}
          icon={Icons.Video}
          label={t('navigation.camera')}
          tooltipLabel={isVideoOn ? t('tools.camera_on') : t('tools.camera_off')}
          variant={isVideoOn ? 'on' : 'idle'}
          canExpandRail={canExpandRail}
          isExpanded={isExpanded}
          ariaLabel="Camera"
        />

        {/* Screen Share Button */}
        <RailButton
          onClick={toggleScreenCapture}
          icon={Icons.Share2}
          label={t('navigation.share')}
          tooltipLabel={visionMode === 'screen' ? t('tools.share_screen_off') : t('tools.share_screen_on')}
          variant={visionMode === 'screen' ? 'on' : 'idle'}
          canExpandRail={canExpandRail}
          isExpanded={isExpanded}
          ariaLabel="Screen Share"
        />

        {/* Divider line */}
        <div className="rail-divider"></div>

        {/* Settings Button */}
        <RailButton
          onClick={() => setActiveContext('settings')}
          icon={Icons.Settings}
          label={t('tools.settings')}
          variant={activeContext === 'settings' ? 'active' : 'idle'}
          canExpandRail={canExpandRail}
          isExpanded={isExpanded}
          ariaLabel="Settings"
          className="mt-auto"
        />

        {/* Quit Button - Floats Away on Hover */}
        <RailButton
          onMouseEnter={handleQuitMouseEnter}
          onMouseMove={handleQuitMouseMove}
          onMouseLeave={handleQuitMouseLeave}
          onClick={onLogout}
          icon={Icons.LogOut}
          label={t('tools.logout')}
          tooltipLabel={isQuitHovered ? t('tools.dont_leave_me') : t('tools.logout')}
          canExpandRail={canExpandRail}
          isExpanded={isExpanded}
          ariaLabel="Logout"
          className="transition-all duration-100 pointer-events-auto cursor-pointer hover:bg-[rgba(166,72,58,0.18)] hover:text-[#f0ad9d]"
          style={{
            transform: `translate(${quitHoverOffset.x}px, ${quitHoverOffset.y}px)`,
            transitionProperty: 'transform, background-color, color, border-color',
            transitionDuration: '100ms',
            transitionTimingFunction: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
          }}
        />
      </div>
    </nav>
  );
};

export default RailNav;
