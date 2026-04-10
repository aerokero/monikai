/**
 * Layout Configuration
 * Defines responsive layout modes, breakpoints, and positioning math for Monika-First Adaptive UI
 */

/**
 * Layout Modes: Responsive grid definitions
 */
export const LAYOUT_MODES = {
  DESKTOP_WIDE: 'desktop-wide',   // width >= 1440px (ultrawide monitors)
  DESKTOP: 'desktop',               // 980px <= width < 1440px (standard laptop/desktop)
  TABLET: 'tablet',                 // 768px <= width < 980px (horizontal - landscape tablet)
  PORTRAIT: 'portrait',             // mobile vertical (height > width, width >= 500px)
  LANDSCAPE_PHONE: 'landscape-phone' // mobile horizontal (width > height, width < 768px)
};

/**
 * Determine layout mode based on viewport dimensions
 * @param {number} width - Viewport width in pixels
 * @param {number} height - Viewport height in pixels
 * @returns {string} Layout mode key
 */
export const getLayoutMode = (width, height) => {
  const isPortrait = height > width;
  const aspectRatio = width / height;

  // Portrait check
  if (isPortrait) {
    if (width >= 500) return LAYOUT_MODES.PORTRAIT;
    return LAYOUT_MODES.LANDSCAPE_PHONE; // Very narrow portrait
  }

  // Landscape/Square
  if (width >= 1440) return LAYOUT_MODES.DESKTOP_WIDE;
  if (width >= 980) return LAYOUT_MODES.DESKTOP;
  if (width >= 768) return LAYOUT_MODES.TABLET;
  return LAYOUT_MODES.LANDSCAPE_PHONE;
};

/**
 * Monika positioning and scaling per layout mode
 */
export const getMonikaConfig = (layoutMode, viewportWidth, viewportHeight) => {
  const configs = {
    [LAYOUT_MODES.DESKTOP_WIDE]: {
      scale: 1.0,                    // Large, prominent
      maxWidth: viewportWidth * 0.4, // Takes up ~40% of width
      maxHeight: viewportHeight * 0.8,
      horizontalPosition: 'center-right', // Positioned right of center
      verticalPosition: 'center',
      spaceAllocation: 'dominant',   // Large space for character
      backgroundFadeOpacity: 0.15,   // Subtle fade behind
      safeAreaPadding: { top: 20, bottom: 20, left: 20, right: 20 }
    },
    [LAYOUT_MODES.DESKTOP]: {
      scale: 0.95,
      maxWidth: viewportWidth * 0.35,
      maxHeight: viewportHeight * 0.75,
      horizontalPosition: 'center-right',
      verticalPosition: 'center',
      spaceAllocation: 'dominant',
      backgroundFadeOpacity: 0.12,
      safeAreaPadding: { top: 16, bottom: 16, left: 16, right: 16 }
    },
    [LAYOUT_MODES.TABLET]: {
      scale: 0.85,
      maxWidth: viewportWidth * 0.5,
      maxHeight: viewportHeight * 0.4,
      horizontalPosition: 'center',
      verticalPosition: 'top',
      spaceAllocation: 'accent',    // Medium space
      backgroundFadeOpacity: 0.1,
      safeAreaPadding: { top: 12, bottom: 12, left: 12, right: 12 }
    },
    [LAYOUT_MODES.PORTRAIT]: {
      scale: 0.8,
      maxWidth: viewportWidth * 0.9,
      maxHeight: viewportHeight * 0.45,
      horizontalPosition: 'center',
      verticalPosition: 'center',
      spaceAllocation: 'accent',
      backgroundFadeOpacity: 0.08,
      safeAreaPadding: { top: 10, bottom: 10, left: 8, right: 8 }
    },
    [LAYOUT_MODES.LANDSCAPE_PHONE]: {
      scale: 0.7,
      maxWidth: viewportWidth * 0.25,
      maxHeight: viewportHeight * 0.7,
      horizontalPosition: 'center',
      verticalPosition: 'center',
      spaceAllocation: 'minimal',   // Small space
      backgroundFadeOpacity: 0.06,
      safeAreaPadding: { top: 8, bottom: 8, left: 6, right: 6 }
    }
  };

  return configs[layoutMode] || configs[LAYOUT_MODES.DESKTOP];
};

/**
 * Rail (navigation) configuration per layout mode
 */
export const getRailConfig = (layoutMode) => {
  const configs = {
    [LAYOUT_MODES.DESKTOP_WIDE]: {
      position: 'left',
      width: 80,
      height: '100vh',
      displayMode: 'icons-and-labels',
      orientation: 'vertical',
      zIndex: 40
    },
    [LAYOUT_MODES.DESKTOP]: {
      position: 'left',
      width: 70,
      height: '100vh',
      displayMode: 'icons',
      orientation: 'vertical',
      zIndex: 40
    },
    [LAYOUT_MODES.TABLET]: {
      position: 'top',
      height: 56,
      width: '100%',
      displayMode: 'icons-and-labels',
      orientation: 'horizontal',
      zIndex: 40
    },
    [LAYOUT_MODES.PORTRAIT]: {
      position: 'bottom',
      height: 56,
      width: '100%',
      displayMode: 'icons-and-labels-compact',
      orientation: 'horizontal',
      zIndex: 40
    },
    [LAYOUT_MODES.LANDSCAPE_PHONE]: {
      position: 'bottom',
      height: 48,
      width: '100%',
      displayMode: 'icons-only',
      orientation: 'horizontal',
      zIndex: 40
    }
  };

  return configs[layoutMode] || configs[LAYOUT_MODES.DESKTOP];
};

/**
 * Panel container configuration per layout mode
 */
export const getPanelConfig = (layoutMode) => {
  const configs = {
    [LAYOUT_MODES.DESKTOP_WIDE]: {
      position: 'right',
      width: 'calc(100% - 400px - 80px)',  // Full width minus Monika space and rail
      maxWidth: 600,
      height: '100%',
      displayMode: 'side-panel',
      scrollable: true,
      zIndex: 30
    },
    [LAYOUT_MODES.DESKTOP]: {
      position: 'right',
      width: 'calc(100% - 300px - 70px)',
      maxWidth: 500,
      height: '100%',
      displayMode: 'side-panel',
      scrollable: true,
      zIndex: 30
    },
    [LAYOUT_MODES.TABLET]: {
      position: 'bottom',
      width: '100%',
      height: 'calc(100% - 200px - 56px)',  // Below Monika and top rail
      displayMode: 'drawer',
      scrollable: true,
      drawerHeight: '60%',
      zIndex: 30
    },
    [LAYOUT_MODES.PORTRAIT]: {
      position: 'bottom',
      width: '100%',
      height: 'calc(100% - 45% - 56px)',    // Below Monika and bottom rail
      displayMode: 'drawer',
      scrollable: true,
      drawerHeight: '100%',
      zIndex: 30
    },
    [LAYOUT_MODES.LANDSCAPE_PHONE]: {
      position: 'full',
      width: '100%',
      height: '100%',
      displayMode: 'fullscreen-drawer',
      scrollable: true,
      drawerHeight: '90%',
      zIndex: 30
    }
  };

  return configs[layoutMode] || configs[LAYOUT_MODES.DESKTOP];
};

/**
 * Safe area insets for notch/home button support
 */
export const getSafeAreaInsets = () => {
  if (typeof window !== 'undefined' && window.visualViewport) {
    return {
      top: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--safe-area-inset-top')) || 0,
      bottom: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--safe-area-inset-bottom')) || 0,
      left: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--safe-area-inset-left')) || 0,
      right: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--safe-area-inset-right')) || 0
    };
  }
  return { top: 0, bottom: 0, left: 0, right: 0 };
};

/**
 * Breakpoints for CSS and responsive logic
 */
export const BREAKPOINTS = {
  xs: 0,          // Mobile phone
  sm: 500,        // Larger phone
  md: 768,        // Tablet
  lg: 980,        // Laptop
  xl: 1440        // Desktop + Ultrawide
};

/**
 * Z-index stacking context
 */
export const Z_INDEX = {
  monikaSprite: 20,
  panelContent: 30,
  panelBackdrop: 35,
  rail: 40,
  contextBar: 45,
  overlays: 50,
  modals: 60,
  notifications: 70
};

export default {
  LAYOUT_MODES,
  getLayoutMode,
  getMonikaConfig,
  getRailConfig,
  getPanelConfig,
  getSafeAreaInsets,
  BREAKPOINTS,
  Z_INDEX
};
