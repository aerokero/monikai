import React, { useState } from 'react';
import { useProgression } from '../../contexts/ProgressionContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { metrics as metricsFromContext } from '../../contexts/ProgressionContext';
import { getRarityColor, calculateAchievementProgress, getDaysAgo } from '../../utils/progressionTransformers';

/**
 * AchievementsTab Component
 * 
 * Displays achievements in two sections:
 * - Unlocked: achievements player has earned
 * - Locked: achievements still to unlock with progress info
 * 
 * Shows: rarity, icon, title, description, progress (for locked)
 * Hidden achievements display as "???" until unlocked
 */
const AchievementsTab = () => {
  const { achievements, metrics } = useProgression();
  const { t } = useLanguage();
  const [showLocked, setShowLocked] = useState(false);

  if (!achievements) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-white/50 text-center">
          <p>{t('common.loading') || 'Loading achievements...'}</p>
        </div>
      </div>
    );
  }

  const AchievementCard = ({ achievement, isUnlocked = false }) => {
    if (!achievement) return null;

    const isHidden = !isUnlocked && achievement.hidden;
    const rarityColor = getRarityColor(achievement.rarity);

    // Calculate progress for locked achievements
    let progressInfo = null;
    if (!isUnlocked && achievement.condition) {
      progressInfo = calculateAchievementProgress(achievement, metrics?.metrics || []);
    }

    return (
      <div className={`group p-3 rounded-lg border transition-all ${
        isUnlocked
          ? 'border-white/10 hover:border-white/20 hover:bg-white/5'
          : 'border-white/5 hover:border-white/15 hover:bg-white/3'
      }`}>
        <div className="flex gap-3">
          {/* Icon */}
          <div className={`text-3xl flex-shrink-0 ${isHidden ? 'blur-sm' : ''}`}>
            {isHidden ? '🔒' : achievement.icon || '⭐'}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            {isHidden ? (
              <>
                <h4 className="text-sm font-bold text-white blur-sm">???</h4>
                <p className="text-xs text-white/30 blur-sm">Hidden achievement</p>
              </>
            ) : (
              <>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <h4 className="text-sm font-bold text-white">{achievement.title}</h4>
                    <p className="text-xs text-white/50 mt-1">{achievement.description}</p>
                  </div>
                  <span className={`text-xs font-semibold px-2 py-1 rounded border flex-shrink-0 capitalize ${rarityColor}`}>
                    {achievement.rarity || 'common'}
                  </span>
                </div>

                {/* Progress Info (for locked achievements) */}
                {!isUnlocked && progressInfo && progressInfo.metric && (
                  <div className="mt-3 space-y-1">
                    <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all duration-500"
                        style={{ width: `${progressInfo.progress * 100}%` }}
                      />
                    </div>
                    <p className="text-xs text-white/40">
                      {progressInfo.metric}: {Math.round(progressInfo.currentValue)} / {progressInfo.targetValue}
                    </p>
                  </div>
                )}

                {/* Unlock Date */}
                {isUnlocked && achievement.unlockedAt && (
                  <p className="text-xs text-white/30 mt-2">
                    Unlocked {getDaysAgo(achievement.unlockedAt)} days ago
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    );
  };

  const unlockedList = achievements.unlocked || [];
  const lockedList = achievements.locked || [];

  return (
    <div className="space-y-6">
      {/* Achievement Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/20 text-center">
          <div className="text-lg font-bold text-green-400">{achievements.unlockedCount || 0}</div>
          <div className="text-xs text-white/50">Unlocked</div>
        </div>
        <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-center">
          <div className="text-lg font-bold text-yellow-400">{achievements.lockedCount || 0}</div>
          <div className="text-xs text-white/50">Locked</div>
        </div>
        <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20 text-center">
          <div className="text-lg font-bold text-blue-400">
            {achievements.totalCount && achievements.unlockedCount
              ? Math.round((achievements.unlockedCount / achievements.totalCount) * 100)
              : 0}%
          </div>
          <div className="text-xs text-white/50">Complete</div>
        </div>
      </div>

      {/* Info Banner */}
      <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 rounded text-xs text-white/70">
        <p>
          🏆 Unlock achievements by reaching metric thresholds and completing special challenges. Hidden achievements will surprise you!
        </p>
      </div>

      {/* Unlocked Achievements */}
      {unlockedList.length > 0 && (
        <div>
          <h3 className="text-sm font-bold text-white mb-3">
            ✓ Unlocked ({unlockedList.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-96 overflow-y-auto">
            {unlockedList.map(ach => (
              <AchievementCard key={ach.id} achievement={ach} isUnlocked={true} />
            ))}
          </div>
        </div>
      )}

      {/* Locked Achievements Section */}
      <div>
        <button
          onClick={() => setShowLocked(!showLocked)}
          className="w-full text-sm font-bold text-white hover:text-white/80 transition-colors py-2 px-3 rounded hover:bg-white/5 text-left flex items-center justify-between"
        >
          <span>🔒 Locked Achievements ({lockedList.length})</span>
          <span className="text-xs text-white/50">{showLocked ? '▼' : '▶'}</span>
        </button>

        {showLocked && lockedList.length > 0 && (
          <div className="mt-3 space-y-3 max-h-96 overflow-y-auto">
            {lockedList.map(ach => (
              <AchievementCard key={ach.id} achievement={ach} isUnlocked={false} />
            ))}
          </div>
        )}

        {showLocked && lockedList.length === 0 && (
          <div className="mt-3 p-4 text-center text-white/50 text-sm">
            All achievements unlocked! 🎉
          </div>
        )}
      </div>

      {/* Empty State */}
      {unlockedList.length === 0 && (
        <div className="flex items-center justify-center h-48">
          <div className="text-center text-white/50">
            <p>No achievements yet</p>
            <p className="text-xs mt-2">Interact with Monika to unlock your first achievement!</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default AchievementsTab;
