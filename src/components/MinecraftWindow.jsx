import React, { useState } from 'react';
import { X, Minus } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const MinecraftWindow = ({ socket, onClose, position, onMouseDown, activeDragElement, zIndex }) => {
  const { t } = useLanguage();
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState(25565);
  const [isConnecting, setIsConnecting] = useState(false);
  const [status, setStatus] = useState('');

  const handleConnect = async () => {
    if (!host) {
      setStatus('Please enter a hostname or IP');
      return;
    }

    setIsConnecting(true);
    setStatus('Connecting...');

    try {
      // Emit minecraft_connect_to_server event to backend
      socket.emit('minecraft_connect_to_server', { 
        host: host.trim(), 
        port: parseInt(port) || 25565 
      }, (response) => {
        if (response?.success) {
          setStatus('Connected! ✓');
          setTimeout(() => {
            setStatus('');
          }, 3000);
        } else {
          setStatus(`Error: ${response?.message || 'Failed to connect'}`);
        }
        setIsConnecting(false);
      });
    } catch (err) {
      setStatus(`Error: ${err.message}`);
      setIsConnecting(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleConnect();
    }
  };

  return (
    <div
      id="minecraft-window"
      onMouseDown={onMouseDown}
      className={`absolute w-96 px-6 py-4 ${
        activeDragElement === 'minecraft' ? 'transition-none' : 'transition-all duration-200'
      } backdrop-blur-2xl bg-gradient-to-br from-slate-900/80 to-slate-800/80 border border-amber-500/30 shadow-2xl rounded-xl`}
      style={{
        left: Math.round(position.x),
        top: Math.round(position.y),
        transform: 'translate(-50%, -50%)',
        pointerEvents: 'auto',
        zIndex: zIndex,
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-amber-500" />
          <h2 className="text-white font-bold text-sm">Minecraft Server</h2>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => {}}
            className="p-1 hover:bg-white/10 rounded transition-colors"
            title="Minimize"
          >
            <Minus size={14} className="text-white/60" />
          </button>
          <button
            onClick={onClose}
            className="p-1 hover:bg-white/10 rounded transition-colors"
            title="Close"
          >
            <X size={14} className="text-white/60" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="space-y-4">
        {/* Host Input */}
        <div>
          <label className="block text-xs text-white/70 mb-1 font-semibold">
            Hostname or IP
          </label>
          <input
            type="text"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="localhost, 192.168.1.1, play.example.com"
            disabled={isConnecting}
            className="w-full px-3 py-2 bg-slate-950/50 border border-amber-500/30 text-white placeholder-white/30 rounded-lg focus:outline-none focus:border-amber-500/60 focus:bg-slate-900/70 text-sm transition-colors disabled:opacity-50"
          />
        </div>

        {/* Port Input */}
        <div>
          <label className="block text-xs text-white/70 mb-1 font-semibold">
            Port <span className="text-white/40 text-xs">(default: 25565)</span>
          </label>
          <input
            type="number"
            value={port}
            onChange={(e) => setPort(parseInt(e.target.value) || 25565)}
            onKeyPress={handleKeyPress}
            placeholder="25565"
            disabled={isConnecting}
            min="1"
            max="65535"
            className="w-full px-3 py-2 bg-slate-950/50 border border-amber-500/30 text-white placeholder-white/30 rounded-lg focus:outline-none focus:border-amber-500/60 focus:bg-slate-900/70 text-sm transition-colors disabled:opacity-50"
          />
        </div>

        {/* Status Message */}
        {status && (
          <div className={`text-xs px-3 py-2 rounded-lg ${
            status.includes('Connected')
              ? 'bg-green-500/20 text-green-300 border border-green-500/30'
              : status.includes('Connecting')
              ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
              : 'bg-red-500/20 text-red-300 border border-red-500/30'
          }`}>
            {status}
          </div>
        )}

        {/* Connect Button */}
        <button
          onClick={handleConnect}
          disabled={isConnecting || !host}
          className={`w-full py-2 px-3 rounded-lg font-semibold text-sm transition-all duration-200 ${
            isConnecting
              ? 'bg-amber-500/30 text-amber-300 cursor-wait'
              : 'bg-gradient-to-r from-amber-600/60 to-amber-500/60 hover:from-amber-600 hover:to-amber-500 text-white shadow-[0_0_15px_rgba(217,119,6,0.3)] hover:shadow-[0_0_25px_rgba(217,119,6,0.5)]'
          }`}
        >
          {isConnecting ? 'Connecting...' : 'Connect to Server'}
        </button>

        {/* Info */}
        <div className="text-xs text-white/40 border-t border-white/10 pt-3 mt-3">
          <p>Once connected, Monika can play Minecraft!</p>
          <p className="mt-1">Supported actions:</p>
          <ul className="list-disc list-inside mt-1 space-y-0.5">
            <li>Chat & communication</li>
            <li>Movement & navigation</li>
            <li>Mining & crafting</li>
            <li>Block placement</li>
            <li>Inventory management</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default MinecraftWindow;
