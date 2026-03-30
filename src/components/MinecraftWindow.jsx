import React, { useState } from 'react';
import { X } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const MinecraftWindow = ({ socket, onClose, position, onMouseDown, activeDragElement, zIndex }) => {
  const { t } = useLanguage();
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState('25565');
  const [isConnecting, setIsConnecting] = useState(false);

  const parsedPort = Number.parseInt(port, 10);
  const isPortValid = Number.isInteger(parsedPort) && parsedPort >= 1 && parsedPort <= 65535;

  const handleConnect = async () => {
    const trimmedHost = host.trim();
    if (!trimmedHost) {
      return;
    }

    if (!isPortValid) {
      return;
    }

    setIsConnecting(true);

    try {
      socket.emit('minecraft_connect_to_server', {
        host: trimmedHost,
        port: parsedPort
      }, () => {
        setIsConnecting(false);
      });
    } catch (err) {
      setIsConnecting(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleConnect();
    }
  };

  const handlePortChange = (e) => {
    const digitsOnly = e.target.value.replace(/\D/g, '').slice(0, 5);

    if (!digitsOnly) {
      setPort('');
      return;
    }

    const numericValue = Number.parseInt(digitsOnly, 10);
    if (Number.isNaN(numericValue)) {
      setPort('');
      return;
    }

    if (numericValue > 65535) {
      setPort('65535');
      return;
    }

    setPort(String(numericValue));
  };

  return (
    <div
      id="minecraft-window"
      onMouseDown={onMouseDown}
      className={`absolute flex flex-col overflow-hidden rounded-xl border border-white/[0.14] bg-black/50 backdrop-blur-2xl shadow-2xl transition-[box-shadow,border-color] duration-200 ${
        activeDragElement === 'minecraft' ? 'ring-1 ring-white/50 border-white/30' : ''
      }`}
      style={{
        left: Math.round(position.x),
        top: Math.round(position.y),
        transform: 'translate(-50%, -50%)',
        width: '360px',
        pointerEvents: 'auto',
        zIndex: zIndex,
      }}
    >
      <div
        className="relative border-b border-white/10 bg-white/5 px-4 py-4 handle cursor-grab active:cursor-grabbing"
        data-drag-handle
      >
        <div className="absolute top-1.5 left-1/2 h-1 w-10 -translate-x-1/2 rounded-full bg-white/15" />
        <div className="flex items-center justify-between gap-4">
          <div className="text-sm font-medium tracking-wider text-white/90 uppercase">
            {t('tools.minecraft') || 'Minecraft Server'}
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-white/50 transition-colors hover:bg-red-500/20 hover:text-red-400">
            <X size={15} />
          </button>
        </div>
      </div>

      <div className="space-y-4 p-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-white/65">
            IP
          </label>
          <input
            type="text"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="localhost"
            disabled={isConnecting}
            className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder-white/30 transition-colors focus:border-white/30 focus:bg-black/40 focus:outline-none disabled:opacity-50"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-white/65">
            Port
          </label>
          <input
            type="number"
            value={port}
            onChange={handlePortChange}
            onKeyDown={handleKeyDown}
            placeholder="25565"
            disabled={isConnecting}
            min="1"
            max="65535"
            inputMode="numeric"
            pattern="[0-9]*"
            className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder-white/30 transition-colors focus:border-white/30 focus:bg-black/40 focus:outline-none disabled:opacity-50"
          />
          {!isPortValid && port !== '' && (
            <p className="mt-1 text-xs text-red-300/90">Port must be between 1 and 65535.</p>
          )}
        </div>

        <button
          onClick={handleConnect}
          disabled={isConnecting || !host.trim() || !isPortValid}
          className={`w-full rounded-lg border px-3 py-2 text-sm font-semibold transition-all duration-200 ${
            isConnecting
              ? 'cursor-wait border-cyan-300/30 bg-cyan-300/10 text-cyan-200'
              : 'border-white/20 bg-white/10 text-white hover:bg-white/20'
          }`}
        >
          {isConnecting ? (t('minecraft.connecting') || 'Connecting...') : (t('minecraft.connect_to_server') || 'Connect to Server')}
        </button>
      </div>
    </div>
  );
};

export default MinecraftWindow;
