import React, { useMemo } from 'react';
import { Trophy, Lock, Star } from 'lucide-react';
import { useProgression } from '../contexts/ProgressionContext';

const AchievementBadge = ({ achievement, locked = false }) => {
  const rarity = achievement.rarity || 'common';
  
  const rarityColors = {
    common: { bg: 'bg-blue-500/20', border: 'border-blue-500/30', text: 'text-blue-300' },
    uncommon: { bg: 'bg-green-500/20', border: 'border-green-500/30', text: 'text-green-300' },
    rare: { bg: 'bg-purple-500/20', border: 'border-purple-500/30', text: 'text-purple-300' },
    epic: { bg: 'bg-pink-500/20', border: 'border-pink-500/30', text: 'text-pink-300' },
    legendary: { bg: 'bg-yellow-500/20', border: 'border-yellow-500/30', text: 'text-yellow-300' },
  };

  const colors = rarityColors[rarity] || rarityColors.common;

  return (
    <div
      className={`relative rounded-lg border p-3 transition-all cursor-pointer hover:scale-105 ${
        locked
          ? 'border-white/10 bg-black/40 opacity-50'
          : `${colors.bg} ${colors.border}`
      }`}
    >
      <div className="flex items-start gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-1">
            {locked ? (
              <Lock size={14} className="text-white/30 flex-shrink-0" />
            ) : (
              <Trophy size={14} className={`${colors.text} flex-shrink-0`} />
            )}
            <div className={`text-xs font-semibold ${locked ? 'text-white/40' : colors.text}`}>
              {achievement.title}
            </div>
          </div>
          <p className={`text-xs mt-1 ${locked ? 'text-white/20' : 'text-white/50'}`}>
            {achievement.description}
          </p>
        </div>

        {!locked && achievement.xp_earned && (
          <div className="flex items-center gap-1 text-xs text-white/60 flex-shrink-0">
            <Star size={12} className="text-yellow-400" />
            {Math.floor(achievement.xp_earned)} XP
          </div>
        )}
      </div>

      {achievement.unlocked_at && !locked && (
        <div className="mt-2 text-xs text-white/30">
          Odblokowano: {new Date(achievement.unlocked_at).toLocaleDateString('pl-PL')}
        </div>
      )}
    </div>
  );
};

export const AchievementsPanel = () => {
  const { achievements, isLoading } = useProgression();

  const stats = useMemo(() => {
    return {
      total: (achievements.unlocked?.length || 0) + (achievements.locked?.length || 0),
      unlocked: achievements.unlocked?.length || 0,
      locked: achievements.locked?.length || 0,
    };
  }, [achievements]);

  if (isLoading) {
    return <div className="text-white/50">Ładowanie osiągnięć...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="text-lg font-semibold text-white mb-4">Osiągnięcia</div>

      <div className="grid grid-cols-3 gap-3 rounded-lg border border-white/10 bg-black/30 p-4">
        <div>
          <div className="text-2xl font-bold text-white">{stats.total}</div>
          <div className="text-xs text-white/50">razem</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-green-400">{stats.unlocked}</div>
          <div className="text-xs text-white/50">odblokowane</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-white/50">{stats.locked}</div>
          <div className="text-xs text-white/50">zablokowane</div>
        </div>
      </div>

      {achievements.unlocked && achievements.unlocked.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-white mb-3">Odblokowane</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {achievements.unlocked.map(ach => (
              <AchievementBadge key={ach.id} achievement={ach} locked={false} />
            ))}
          </div>
        </div>
      )}

      {achievements.locked && achievements.locked.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-white mb-3">Zablokowane</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {achievements.locked.slice(0, 6).map(ach => (
              <AchievementBadge key={ach.id} achievement={ach} locked={true} />
            ))}
            {achievements.locked.length > 6 && (
              <div className="rounded-lg border border-white/10 bg-black/30 p-3 text-center">
                <div className="text-xs text-white/50">
                  i {achievements.locked.length - 6} więcej...
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
