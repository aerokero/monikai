/**
 * Panel Registry Configuration
 * Defines the migrated MonikaShell panel surfaces for the first adaptive pass.
 */

export const PANELS = {
  chat: {
    id: 'chat',
    name: 'Chat',
    displayName: 'Chat',
    description: 'Talk with Monika',
    icon: 'MessageSquare',
    contextKey: 'chat',
    component: 'ChatPanel',
    order: 1,
    draggable: false,
    collapsible: false,
    dockPreference: {
      desktop: 'main-panel',      // Right side of desktop
      tablet: 'drawer',           // Bottom drawer on tablet
      portrait: 'drawer'          // Full-width below Monika
    },
    ariaLabel: 'Chat with companion',
    keyboardShortcut: 'Alt+1'
  },
  conversations: {
    id: 'conversations',
    name: 'Conversations',
    displayName: 'Conversations',
    description: 'Browse past conversations',
    icon: 'Clock',
    contextKey: 'conversations',
    component: 'ConversationsShellPanel',
    order: 2,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'Conversation history',
    keyboardShortcut: 'Alt+2'
  },
  worlds: {
    id: 'worlds',
    name: 'Worlds',
    displayName: 'Worlds',
    description: 'Manage lorebooks and active worlds',
    icon: 'Globe',
    contextKey: 'worlds',
    component: 'WorldsShellPanel',
    order: 3,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'Lorebooks and active worlds',
    keyboardShortcut: 'Alt+3'
  },
  study: {
    id: 'study',
    name: 'Study',
    displayName: 'Study',
    description: 'Learn and practice',
    icon: 'BookOpen',
    contextKey: 'study',
    component: 'StudyPanel',
    order: 2,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'Study and learning',
    keyboardShortcut: 'Alt+2',
    hiddenInRail: true
  },
  notes: {
    id: 'notes',
    name: 'Notes',
    displayName: 'Notes',
    description: 'Write and organize notes',
    icon: 'FileText',
    contextKey: 'notes',
    component: 'NotesWindow',
    order: 3,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'Notes workspace',
    keyboardShortcut: 'Alt+3'
  },
  companion: {
    id: 'companion',
    name: 'Activities',
    displayName: 'Activities',
    description: 'Activities and session controls',
    icon: 'Zap',
    contextKey: 'companion',
    component: 'CompanionWindow',
    order: 4,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'Activities and companion actions',
    keyboardShortcut: 'Alt+4'
  },
  calendar: {
    id: 'calendar',
    name: 'Calendar',
    displayName: 'Calendar',
    description: 'Events and reminders',
    icon: 'Calendar',
    contextKey: 'calendar',
    component: 'CalendarWindow',
    order: 5,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'Calendar and events',
    keyboardShortcut: 'Alt+5'
  },
  profile: {
    id: 'profile',
    name: 'Profile',
    displayName: 'Profile',
    description: 'Manage user profile and preferences',
    icon: 'User',
    contextKey: 'profile',
    component: 'ProfileWindow',
    order: 6,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'User profile settings',
    keyboardShortcut: 'Alt+6'
  },
  settings: {
    id: 'settings',
    name: 'Settings',
    displayName: 'Settings',
    description: 'Nasze ustawienia',
    icon: 'Settings',
    contextKey: 'settings',
    component: 'SettingsPanel',
    order: 7,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'System settings',
    keyboardShortcut: 'Alt+7',
    hiddenInRail: true
  }
};

/**
 * Get panel by ID
 */
export const getPanelById = (panelId) => {
  return PANELS[panelId];
};

/**
 * Get all panels sorted by order
 */
export const getAllPanels = () => {
  const panelList = Object.values(PANELS).sort((a, b) => a.order - b.order);
  return panelList;
};

/**
 * Get panels suited for a specific layout mode
 */
export const getPanelsForLayout = (layoutMode) => {
  return getAllPanels().map(panel => ({
    ...panel,
    dock: panel.dockPreference[layoutMode] || panel.dockPreference.desktop
  }));
};

export default {
  PANELS,
  getPanelById,
  getAllPanels,
  getPanelsForLayout
};
