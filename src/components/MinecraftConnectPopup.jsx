import React, { useEffect, useMemo, useState } from 'react';
import { Gamepad2, Loader2, Server, X } from './icons';
import { useLanguage } from '../contexts/LanguageContext';

const LAST_HOST_KEY = 'minecraft_last_host';
const LAST_PORT_KEY = 'minecraft_last_port';

const MinecraftConnectPopup = ({ socket, isOpen, onClose, onConnected }) => {
  const { t } = useLanguage();
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState('25565');
  const [isConnecting, setIsConnecting] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [statusType, setStatusType] = useState('idle');

  useEffect(() => {
    if (!isOpen) return;
    try {
      const rememberedHost = (localStorage.getItem(LAST_HOST_KEY) || '').trim();
      const rememberedPort = (localStorage.getItem(LAST_PORT_KEY) || '').trim();
      if (rememberedHost) setHost(rememberedHost);
      if (rememberedPort) setPort(rememberedPort);
    } catch {
      // Ignore storage errors and keep defaults.
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  const parsedPort = Number.parseInt(port, 10);
  const isPortValid = Number.isInteger(parsedPort) && parsedPort >= 1 && parsedPort <= 65535;
  const canConnect = Boolean((host || '').trim()) && isPortValid && !isConnecting && Boolean(socket);

  const statusClass = useMemo(() => {
    if (statusType === 'success') return 'text-emerald-200 border-emerald-300/20 bg-emerald-400/10';
    if (statusType === 'error') return 'text-red-200 border-red-300/20 bg-red-400/10';
    if (statusType === 'pending') return 'text-cyan-100 border-cyan-300/20 bg-cyan-300/10';
    return 'text-white/70 border-white/10 bg-white/5';
  }, [statusType]);

  if (!isOpen) return null;

  const handlePortChange = (event) => {
    const digitsOnly = String(event.target.value || '').replace(/\D/g, '').slice(0, 5);
    if (!digitsOnly) {
      setPort('');
      return;
    }
    const numericValue = Number.parseInt(digitsOnly, 10);
    if (Number.isNaN(numericValue)) {
      setPort('');
      return;
    }
    setPort(String(Math.min(65535, numericValue)));
  };

  const handleConnect = () => {
    if (!canConnect) return;

    const trimmedHost = host.trim();
    setIsConnecting(true);
    setStatusType('pending');
    setStatusText(t('minecraft.connecting') || 'Connecting...');

    socket.emit(
      'minecraft_connect_to_server',
      { host: trimmedHost, port: parsedPort },
      (result) => {
        setIsConnecting(false);
        const ok = Boolean(result && result.success);
        const message = String(result?.message || (ok ? 'Connected.' : 'Connection failed.'));

        if (ok) {
          setStatusType('success');
          setStatusText(message);
          try {
            localStorage.setItem(LAST_HOST_KEY, trimmedHost);
            localStorage.setItem(LAST_PORT_KEY, String(parsedPort));
          } catch {
            // Ignore storage errors.
          }
          if (typeof onConnected === 'function') onConnected({ host: trimmedHost, port: parsedPort, message });
          window.setTimeout(() => onClose(), 500);
          return;
        }

        setStatusType('error');
        setStatusText(message);
      }
    );
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      handleConnect();
    }
  };

  return (
    <div className="fixed inset-0 z-[140] flex items-center justify-center bg-black/45 px-4 backdrop-blur-sm" onMouseDown={onClose}>
      <div
        className="w-full max-w-[460px] overflow-hidden rounded-2xl border border-white/15 bg-[linear-gradient(180deg,rgba(18,20,28,0.92),rgba(14,16,23,0.96))] shadow-[0_28px_65px_rgba(0,0,0,0.45)]"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/10 bg-white/5 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-300/20 bg-emerald-400/15 text-emerald-200">
              <Gamepad2 size={18} />
            </div>
            <div>
              <div className="text-sm font-semibold text-white/95">{t('minecraft.connect_to_server') || 'Connect to Server'}</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-white/50 transition hover:bg-red-500/20 hover:text-red-300"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-5">
          <div className="space-y-1.5">
            <label className="text-xs uppercase tracking-[0.14em] text-white/55">Server</label>
            <div className="relative">
              <Server size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
              <input
                type="text"
                value={host}
                onChange={(event) => setHost(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="localhost"
                disabled={isConnecting}
                className="w-full rounded-xl border border-white/15 bg-black/35 py-2.5 pl-9 pr-3 text-sm text-white placeholder:text-white/30 outline-none transition focus:border-emerald-300/40 focus:bg-black/45 disabled:opacity-60"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs uppercase tracking-[0.14em] text-white/55">Port</label>
            <input
              type="text"
              value={port}
              onChange={handlePortChange}
              onKeyDown={handleKeyDown}
              placeholder="25565"
              inputMode="numeric"
              disabled={isConnecting}
              className="w-full rounded-xl border border-white/15 bg-black/35 px-3 py-2.5 text-sm text-white placeholder:text-white/30 outline-none transition focus:border-emerald-300/40 focus:bg-black/45 disabled:opacity-60"
            />
            {!isPortValid && port !== '' ? (
              <p className="text-xs text-red-300/90">Port must be between 1 and 65535.</p>
            ) : null}
          </div>

          {statusText ? (
            <div className={`min-h-[38px] rounded-xl border px-3 py-2 text-xs ${statusClass}`}>
              {statusText}
            </div>
          ) : null}

          <div className="flex w-full items-center gap-2 pt-1">
            <button
              onClick={onClose}
              disabled={isConnecting}
              className="flex-1 rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-sm text-white/80 transition hover:bg-white/10 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleConnect}
              disabled={!canConnect}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-emerald-300/30 bg-emerald-400/15 px-4 py-2 text-sm font-semibold text-emerald-100 transition hover:bg-emerald-400/22 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {isConnecting ? <Loader2 size={14} className="animate-spin" /> : null}
              {isConnecting ? (t('minecraft.connecting') || 'Connecting...') : (t('minecraft.connect_to_server') || 'Connect to Server')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MinecraftConnectPopup;
