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

export const isAdaptiveShellEnabled = () => {
  const localOverride = readLocalFlag('monikai.ui.adaptive_shell');
  if (localOverride !== null) {
    return parseBooleanFlag(localOverride, false);
  }

  const envFlag = import.meta.env.VITE_ENABLE_ADAPTIVE_SHELL;
  return parseBooleanFlag(envFlag, false);
};

export { parseBooleanFlag };
