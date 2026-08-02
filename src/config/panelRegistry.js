/**
 * Panel Registry Configuration
 * Defines the panels available in the rail nav and their routing metadata.
 */

export const PANELS = {
  chat: {
    id: 'chat',
    name: 'Chat',
    icon: 'MessageSquare',
    order: 1,
    ariaLabel: 'Chat with companion',
    // The chat window is always on screen (see ChatPanel), so it isn't a
    // panel to navigate to — it's the default/closed state every other
    // panel's close button returns to. Keeping the entry (not deleting it)
    // because activeContext still needs a valid fallback id.
    hiddenInRail: true,
  },
  conversations: {
    id: 'conversations',
    name: 'Conversations',
    icon: 'Clock',
    order: 2,
    ariaLabel: 'Conversation history',
  },
  worlds: {
    id: 'worlds',
    name: 'Worlds',
    icon: 'Globe',
    order: 3,
    ariaLabel: 'Lorebooks and active worlds',
  },
  study: {
    id: 'study',
    name: 'Study',
    icon: 'BookOpen',
    order: 2,
    ariaLabel: 'Study and learning',
    hiddenInRail: true,
  },
  notes: {
    id: 'notes',
    name: 'Notes',
    icon: 'FileText',
    order: 3,
    ariaLabel: 'Notes workspace',
  },
  calendar: {
    id: 'calendar',
    name: 'Calendar',
    icon: 'Calendar',
    order: 5,
    ariaLabel: 'Calendar and events',
  },
  profile: {
    id: 'profile',
    name: 'Profile',
    icon: 'User',
    order: 6,
    ariaLabel: 'User profile settings',
  },
  settings: {
    id: 'settings',
    name: 'Settings',
    icon: 'Settings',
    order: 7,
    ariaLabel: 'System settings',
    hiddenInRail: true,
  },
};

/**
 * Get panel by ID
 */
export const getPanelById = (panelId) => PANELS[panelId];

/**
 * Get all panels sorted by order
 */
export const getAllPanels = () => Object.values(PANELS).sort((a, b) => a.order - b.order);

export default {
  PANELS,
  getPanelById,
  getAllPanels,
};
