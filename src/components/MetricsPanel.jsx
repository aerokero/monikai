import React from 'react';
import { Heart, Shield, Sparkles, Flame } from 'lucide-react';
import { useProgression } from '../contexts/ProgressionContext';

const MetricBar = ({ label, icon: Icon, value = 0, nextThreshold = 0, color = 'from-pink-500 to-rose-400' }) => {
  const percentage = nextThreshold > 0 ? (value / nextThreshold) * 100 : 0;
  const displayValue = Math.floor(value);
  const displayThreshold = Math.floor(nextThreshold);

  return (
    <div className="mb-4 rounded-lg border border-white/10 bg-black/30 p-4">
      <div className="flex items-center gap-3 mb-2">
        <Icon size={18} className="text-white/70" />
        <span className="text-sm font-semibold text-white">{label}</span>
        <span className="ml-auto text-xs text-white/50">
          {displayValue} / {displayThreshold}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10 ring-1 ring-white/10">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${color} transition-all duration-500`}
          style={{ width: `${Math.min(100, percentage)}%` }}
        />
      </div>
      <div className="mt-2 text-xs text-white/40">
        {Math.floor(percentage)}% do następnego osiągnięcia
      </div>
    </div>
  );
};

export const MetricsPanel = () => {
  const { metrics, isLoading } = useProgression();

  if (isLoading) {
    return <div className="text-white/50">Ładowanie metryk...</div>;
  }

  if (!metrics) {
    return <div className="text-white/50">Nie ma dostępnych danych metryk</div>;
  }

  const metricsData = metrics.metrics || {};
  const progress = metrics.progress || {};

  return (
    <div className="space-y-4">
      <div className="text-lg font-semibold text-white mb-6">Relacja z Moniką</div>
      
      <MetricBar
        label="Affection (Czułość)"
        icon={Heart}
        value={metricsData.affection || 0}
        nextThreshold={progress.affection_next || 25}
        color="from-pink-500 to-rose-400"
      />

      <MetricBar
        label="Comfort (Zaufanie)"
        icon={Shield}
        value={metricsData.comfort || 0}
        nextThreshold={progress.comfort_next || 25}
        color="from-blue-500 to-cyan-400"
      />

      <MetricBar
        label="Synergy (Harmonia)"
        icon={Sparkles}
        value={metricsData.synergy || 0}
        nextThreshold={progress.synergy_next || 25}
        color="from-purple-500 to-violet-400"
      />

      <MetricBar
        label="Intimacy (Bliskość)"
        icon={Flame}
        value={metricsData.intimacy || 0}
        nextThreshold={progress.intimacy_next || 25}
        color="from-orange-500 to-amber-400"
      />

      <div className="mt-6 rounded-lg border border-white/10 bg-black/30 p-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-white/70">Seria dni:</span>
          <span className="text-lg font-semibold text-white">
            {metricsData.streak_days || 0} dni
          </span>
        </div>
        <div className="flex items-center justify-between text-sm mt-3">
          <span className="text-white/70">Razem XP:</span>
          <span className="text-lg font-semibold text-white">
            {Math.floor(metricsData.total_xp_earned || 0)}
          </span>
        </div>
      </div>
    </div>
  );
};
