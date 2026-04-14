const parseBooleanFlag = (value, fallback = false) => {
  if (typeof value !== 'string') return fallback;
  const normalized = value.trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off'].includes(normalized)) return false;
  return fallback;
};

const readLocalFlag = (key) => {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

export const isMonikaShellEnabled = () => {
  const localOverride = readLocalFlag('monikai.ui.monika_shell');
  if (localOverride !== null) {
    return parseBooleanFlag(localOverride, true); // Default to true for new installs
  }

  const envFlag = import.meta.env.VITE_ENABLE_MONIKA_SHELL;
  return parseBooleanFlag(envFlag, true); // Default to true for testing
};

/**
 * Set Monika Shell enabled state
 * @param {boolean} enabled
 */
export const setMonikaShellEnabled = (enabled) => {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem('monikai.ui.monika_shell', enabled ? 'true' : 'false');
  } catch {
    // ignore storage errors
  }
};
