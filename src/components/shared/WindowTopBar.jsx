import React, { useEffect, useMemo, useState } from 'react';
import { Minus, X } from '../icons';
import { useLanguage } from '../../contexts/LanguageContext';

const WindowTopBar = () => {
  const { t } = useLanguage();
  const ipcRenderer = useMemo(() => {
    try {
      if (typeof window !== 'undefined' && typeof window.require === 'function') {
        const electron = window.require('electron');
        return electron?.ipcRenderer || null;
      }
    } catch {
      return null;
    }
    return null;
  }, []);

  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    if (!ipcRenderer) return undefined;

    let mounted = true;

    ipcRenderer.invoke('window-is-maximized')
      .then((maximized) => {
        if (mounted) setIsMaximized(Boolean(maximized));
      })
      .catch(() => {});

    const onMaximizedChanged = (_event, maximized) => {
      setIsMaximized(Boolean(maximized));
    };

    ipcRenderer.on('window-maximized-changed', onMaximizedChanged);

    return () => {
      mounted = false;
      ipcRenderer.removeListener('window-maximized-changed', onMaximizedChanged);
    };
  }, [ipcRenderer]);

  if (!ipcRenderer) return null;

  return (
    <header className="window-topbar" aria-label={t('window_topbar.controls_label')}>
      <div
        className="window-topbar__drag"
        onDoubleClick={() => ipcRenderer.send('window-maximize')}
      />

      <div className="window-topbar__controls">
        <button
          type="button"
          className="window-topbar__btn"
          onClick={() => ipcRenderer.send('window-minimize')}
          aria-label={t('window_topbar.minimize')}
          title={t('window_topbar.minimize')}
        >
          <Minus size={14} />
        </button>

        <button
          type="button"
          className="window-topbar__btn"
          onClick={() => ipcRenderer.send('window-maximize')}
          aria-label={isMaximized ? t('window_topbar.restore') : t('window_topbar.maximize')}
          title={isMaximized ? t('window_topbar.restore') : t('window_topbar.maximize')}
        >
          <span className="window-topbar__square" />
        </button>

        <button
          type="button"
          className="window-topbar__btn window-topbar__btn--close"
          onClick={() => ipcRenderer.send('window-close')}
          aria-label={t('window_topbar.close')}
          title={t('window_topbar.close')}
        >
          <X size={14} />
        </button>
      </div>
    </header>
  );
};

export default WindowTopBar;
