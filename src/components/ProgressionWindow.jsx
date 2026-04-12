import React, { useState } from 'react';
import { X, TrendingUp, Zap, Trophy, Unlock } from 'lucide-react';
import { MetricsPanel } from './MetricsPanel';
import { QuestsPanel } from './QuestsPanel';
import { AchievementsPanel } from './AchievementsPanel';
import { useProgression } from '../contexts/ProgressionContext';
import { useLayout } from '../contexts/LayoutContext';

const TabButton = ({ icon: Icon, label, isActive, onClick }) => (
  <button
    onClick={onClick}
    className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all text-sm font-medium ${
      isActive
        ? 'bg-white/15 text-white border border-white/20'
        : 'text-white/50 hover:text-white/70 border border-transparent hover:border-white/10'
    }`}
  >
    <Icon size={16} />
    {label}
  </button>
);

export const ProgressionWindow = ({ onClose, isAdaptiveMode = false }) => {
  const [activeTab, setActiveTab] = useState('metrics');
  const { notifications, fetchAll } = useProgression();
  const { activePanelId, setActivePanelId } = useLayout();

  const tabs = [
    { id: 'metrics', label: 'Metryki', icon: TrendingUp },
    { id: 'quests', label: 'Zadania', icon: Zap },
    { id: 'achievements', label: 'Osiągnięcia', icon: Trophy },
  ];

  // Adaptive mode: just content (for panels)
  if (isAdaptiveMode) {
    return (
      <div className="w-full h-full flex flex-col bg-black/40">
        {/* Header */}
        <div className="border-b border-white/10 bg-black/40 px-4 py-3 flex-shrink-0">
          <h3 className="text-sm font-bold text-white">Progresja z Moniką</h3>
        </div>

        {/* Notification Badge */}
        {notifications && notifications.length > 0 && (
          <div className="px-4 py-2 bg-green-500/10 border-b border-green-500/20 flex items-center justify-between flex-shrink-0">
            <div className="text-xs text-green-300">
              +{notifications.length}
            </div>
            <button
              onClick={fetchAll}
              className="text-xs px-2 py-1 rounded bg-green-500/20 hover:bg-green-500/30 text-green-300 transition-colors"
            >
              Odśwież
            </button>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-2 border-b border-white/10 bg-black/20 px-4 py-2 overflow-x-auto flex-shrink-0">
          {tabs.map(tab => (
            <TabButton
              key={tab.id}
              icon={tab.icon}
              label={tab.label}
              isActive={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
            />
          ))}
        </div>

        {/* Content */}
        <div className="overflow-y-auto flex-1 px-4 py-3">
          {activeTab === 'metrics' && <MetricsPanel />}
          {activeTab === 'quests' && <QuestsPanel />}
          {activeTab === 'achievements' && <AchievementsPanel />}
        </div>

        {/* Footer */}
        <div className="border-t border-white/10 bg-black/40 px-4 py-2 flex-shrink-0 text-xs text-white/50">
          Odśwież co 10s
        </div>
      </div>
    );
  }

  // Modal mode (standalone, for non-adaptive UI)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Window */}
      <div className="relative z-10 max-h-[90vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-black/80 via-black/90 to-black/80 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 bg-black/40 px-6 py-4">
          <div>
            <h2 className="text-xl font-bold text-white">Progresja z Moniką</h2>
            <p className="text-xs text-white/50 mt-1">Śledzenie relacji i rozwoju</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X size={20} className="text-white/70" />
          </button>
        </div>

        {/* Notification Badge */}
        {notifications && notifications.length > 0 && (
          <div className="px-6 py-3 bg-green-500/10 border-b border-green-500/20 flex items-center justify-between">
            <div className="text-sm text-green-300">
              {notifications.length} nowe powiadomienie{notifications.length !== 1 ? 'a' : ''}
            </div>
            <button
              onClick={fetchAll}
              className="text-xs px-2 py-1 rounded bg-green-500/20 hover:bg-green-500/30 text-green-300 transition-colors"
            >
              Odśwież
            </button>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-2 border-b border-white/10 bg-black/20 px-6 py-4">
          {tabs.map(tab => (
            <TabButton
              key={tab.id}
              icon={tab.icon}
              label={tab.label}
              isActive={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
            />
          ))}
        </div>

        {/* Content */}
        <div className="overflow-y-auto max-h-[calc(90vh-200px)] px-6 py-4">
          {activeTab === 'metrics' && <MetricsPanel />}
          {activeTab === 'quests' && <QuestsPanel />}
          {activeTab === 'achievements' && <AchievementsPanel />}
        </div>

        {/* Footer */}
        <div className="border-t border-white/10 bg-black/40 px-6 py-3 flex items-center justify-between text-xs text-white/50">
          <div>Dane odświeżane co 10 sekund</div>
          <button
            onClick={fetchAll}
            className="px-3 py-1.5 rounded bg-white/10 hover:bg-white/15 transition-colors"
          >
            Odśwież teraz
          </button>
        </div>
      </div>
    </div>
  );
};
