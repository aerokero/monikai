import React from 'react';
import { useProgression } from '../../contexts/ProgressionContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { getMetricColor, getMetricIcon } from '../../utils/progressionTransformers';

/**
 * MetricsTab Component
 * 
 * Displays 4 relationship metrics:
 * - Affection (❤️)
 * - Comfort (🛡️)
 * - Synergy (✨)
 * - Intimacy (💫)
 * 
 * Shows: current value, next threshold, progress bar, streak days
 */
const MetricsTab = () => {
  const { metrics } = useProgression();
  const { t } = useLanguage();

  if (!metrics || !metrics.metrics || metrics.metrics.length === 0) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-white/50 text-center">
          <p>{t('common.loading') || 'Loading metrics...'}</p>
        </div>
      </div>
    );
  }

  const MetricCard = ({ metric }) => {
    if (!metric) return null;

    const progressPercent = (metric.progress || 0) * 100;
    const displayName = metric.name.charAt(0).toUpperCase() + metric.name.slice(1);

    return (
      <div className="group p-4 rounded-lg border border-white/10 hover:border-white/20 transition-all hover:bg-white/5 cursor-default">
        {/* Header with icon and name */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-2xl">{getMetricIcon(metric.name)}</span>
            <h3 className="text-sm font-bold text-white">{displayName}</h3>
          </div>
          <div className="text-xs px-2 py-1 rounded bg-white/10 text-white/70">
            Streak: {metric.streakDays}d
          </div>
        </div>

        {/* Current Value Display */}
        <div className="mb-3 text-center">
          <div className="text-3xl font-bold text-white">{Math.round(metric.value)}</div>
          <div className="text-xs text-white/50">
            → {metric.nextThreshold} (threshold)
          </div>
        </div>

        {/* Progress Bar */}
        <div className="space-y-1 mb-3">
          <div className="h-3 bg-white/10 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 bg-gradient-to-r ${getMetricColor(metric.name)}`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <p className="text-xs text-white/50">
            {Math.round(metric.value)} / {metric.nextThreshold}
          </p>
        </div>

        {/* Threshold Info */}
        {metric.achievementsAtThreshold && metric.achievementsAtThreshold.length > 0 && (
          <div className="text-xs text-white/40 space-y-1 border-t border-white/10 pt-3">
            <p className="font-semibold text-white/60">Next Achievements:</p>
            {metric.achievementsAtThreshold.slice(0, 3).map((ach, idx) => (
              <p key={idx} className="truncate">
                • {ach.title || `Achievement at ${ach.value}`}
              </p>
            ))}
          </div>
        )}

        {/* Last Interaction */}
        {metric.lastInteraction && (
          <div className="mt-3 text-xs text-white/30">
            Last interaction: {new Date(metric.lastInteraction).toLocaleDateString()}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Info Banner */}
      <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 rounded text-xs text-white/70">
        <p>
          💭 {t('progression.metrics_info') || 'Metrics grow through conversations, interactions, and completing daily quests. See how well you\'re bonding!'}
        </p>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {metrics.metrics.map((metric) => (
          <MetricCard key={metric.name} metric={metric} />
        ))}
      </div>

      {/* Thresholds Reference */}
      <div className="mt-6 p-4 rounded-lg bg-white/5 border border-white/10">
        <h4 className="text-xs font-semibold text-white/70 mb-3">Achievement Thresholds</h4>
        <div className="grid grid-cols-2 gap-4 text-xs text-white/50">
          {metrics.nextThresholds && Object.entries(metrics.nextThresholds).map(([name, thresholds]) => (
            <div key={name}>
              <p className="font-semibold text-white/60 capitalize mb-1">{name}:</p>
              <p className="text-xs">{thresholds.join(', ')}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Metric Calculation Info */}
      <div className="text-xs text-white/30 italic space-y-1">
        <p>ℹ️ Metrics are updated in real-time as you interact with Monika</p>
        <p>ℹ️ Streaks track consecutive days of interaction</p>
        <p>ℹ️ Reaching thresholds unlocks achievements and new features</p>
      </div>
    </div>
  );
};

export default MetricsTab;
