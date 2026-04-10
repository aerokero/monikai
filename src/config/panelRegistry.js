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
    keyboardShortcut: 'Alt+2'
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
  daily_briefing: {
    id: 'daily_briefing',
    name: 'Daily Briefing',
    displayName: 'Briefing',
    description: 'Curated updates and weather',
    icon: 'Newspaper',
    contextKey: 'daily_briefing',
    component: 'DailyBriefingWindow',
    order: 4,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'Daily briefing',
    keyboardShortcut: 'Alt+4'
  },
  companion: {
    id: 'companion',
    name: 'Companion',
    displayName: 'Companion',
    description: 'Activities and session controls',
    icon: 'Heart',
    contextKey: 'companion',
    component: 'CompanionWindow',
    order: 5,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'Companion actions',
    keyboardShortcut: 'Alt+5'
  },
  goals: {
    id: 'goals',
    name: 'Goals',
    displayName: 'Goals',
    description: 'Relationship progress and quests',
    icon: 'Trophy',
    contextKey: 'goals',
    component: 'GoalsWindow',
    order: 6,
    draggable: false,
    collapsible: true,
    dockPreference: {
      desktop: 'main-panel',
      tablet: 'drawer',
      portrait: 'drawer'
    },
    ariaLabel: 'Goals and progress',
    keyboardShortcut: 'Alt+6'
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
  return Object.values(PANELS).sort((a, b) => a.order - b.order);
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
