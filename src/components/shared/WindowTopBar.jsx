import React, { useEffect, useMemo, useState } from 'react';
import { Minus, X } from 'lucide-react';

const WindowTopBar = () => {
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
    <header className="window-topbar" aria-label="Window controls">
      <div
        className="window-topbar__drag"
        onDoubleClick={() => ipcRenderer.send('window-maximize')}
      />

      <div className="window-topbar__controls">
        <button
          type="button"
          className="window-topbar__btn"
          onClick={() => ipcRenderer.send('window-minimize')}
          aria-label="Minimize"
          title="Minimize"
        >
          <Minus size={14} />
        </button>

        <button
          type="button"
          className="window-topbar__btn"
          onClick={() => ipcRenderer.send('window-maximize')}
          aria-label={isMaximized ? 'Restore' : 'Maximize'}
          title={isMaximized ? 'Restore' : 'Maximize'}
        >
          <span className="window-topbar__square" />
        </button>

        <button
          type="button"
          className="window-topbar__btn window-topbar__btn--close"
          onClick={() => ipcRenderer.send('window-close')}
          aria-label="Close"
          title="Close"
        >
          <X size={14} />
        </button>
      </div>
    </header>
  );
};

export default WindowTopBar;
