import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Unlock, Lock } from 'lucide-react';
import { useProgression } from '../../contexts/ProgressionContext';
import { useLanguage } from '../../contexts/LanguageContext';

/**
 * UnlocksTab Component
 * 
 * Displays feature/narrative unlocks grouped by category:
 * - Relationship (romantic features, bonding activities)
 * - Activities (games, watching, learning)
 * - Narrative (story unlocks, new content)
 * - Gaming (Minecraft integration, etc.)
 * 
 * Shows: requirements, status, triggers, story flags
 */
const UnlocksTab = () => {
  const { unlocks } = useProgression();
  const { t } = useLanguage();
  const [expandedUnlock, setExpandedUnlock] = useState(null);
  const [expandedCategory, setExpandedCategory] = useState({
    relationship: true,
    activities: true,
    narrative: true,
    gaming: false,
  });

  if (!unlocks || !unlocks.byCategory) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-white/50 text-center">
          <p>{t('common.loading') || 'Loading unlocks...'}</p>
        </div>
      </div>
    );
  }

  const getCategoryIcon = (category) => {
    const icons = {
      relationship: '❤️',
      activities: '🎮',
      narrative: '📖',
      gaming: '🕹️',
    };
    return icons[category] || '✨';
  };

  const getCategoryColor = (category) => {
    const colors = {
      relationship: 'from-pink-500/20 to-rose-500/20',
      activities: 'from-purple-500/20 to-violet-500/20',
      narrative: 'from-blue-500/20 to-cyan-500/20',
      gaming: 'from-yellow-500/20 to-amber-500/20',
    };
    return colors[category] || 'from-gray-500/20 to-slate-500/20';
  };

  const UnlockCard = ({ unlock, isExpanded, onToggle }) => {
    if (!unlock) return null;

    const isActive = unlock.status === 'active';
    const isAvailable = unlock.status === 'available';
    const hasRequirements = unlock.requirements && unlock.requirements.length > 0;

    return (
      <div className="rounded-lg border border-white/10 overflow-hidden hover:border-white/20 transition-all">
        <button
          onClick={onToggle}
          className={`w-full p-3 text-left transition-colors ${
            isActive
              ? 'bg-green-500/10 hover:bg-green-500/15'
              : isAvailable
              ? 'bg-yellow-500/10 hover:bg-yellow-500/15'
              : 'bg-white/5 hover:bg-white/10'
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-3 flex-1">
              <div className="text-2xl flex-shrink-0">{unlock.icon || '✨'}</div>
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-bold text-white">{unlock.label}</h4>
                <p className="text-xs text-white/50 mt-1 line-clamp-2">{unlock.description}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span
                className={`text-xs font-semibold px-2 py-1 rounded border ${
                  isActive
                    ? 'bg-green-500/20 border-green-500/30 text-green-300'
                    : isAvailable
                    ? 'bg-yellow-500/20 border-yellow-500/30 text-yellow-300'
                    : 'bg-white/10 border-white/20 text-white/50'
                }`}
              >
                {isActive ? '✓ Active' : isAvailable ? 'Available' : 'Locked'}
              </span>
              {isExpanded ? (
                <ChevronUp size={18} className="text-white/50" />
              ) : (
                <ChevronDown size={18} className="text-white/50" />
              )}
            </div>
          </div>
        </button>

        {/* Expanded Details */}
        {isExpanded && (
          <div className="border-t border-white/10 p-3 space-y-3 bg-white/3">
            {/* Requirements */}
            {hasRequirements && (
              <div>
                <h5 className="text-xs font-semibold text-white/70 mb-2">Requirements:</h5>
                <div className="space-y-1">
                  {unlock.requirements.map((req, idx) => (
                    <div
                      key={idx}
                      className="text-xs text-white/50 pl-3 py-1 border-l border-white/10"
                    >
                      {req.type === 'achievement' && (
                        <>
                          <Lock size={12} className="inline mr-1" />
                          Achievement: {req.id}
                        </>
                      )}
                      {req.type === 'metric' && (
                        <>
                          <Unlock size={12} className="inline mr-1" />
                          {req.metric} ≥ {req.value}
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Triggers */}
            {unlock.triggersOnUnlock && unlock.triggersOnUnlock.length > 0 && (
              <div>
                <h5 className="text-xs font-semibold text-white/70 mb-2">Triggers:</h5>
                <div className="space-y-1 text-xs text-white/50">
                  {unlock.triggersOnUnlock.map((trigger, idx) => (
                    <div key={idx} className="pl-3 py-1 border-l border-white/10">
                      {trigger.type === 'notification' && '📢 ' + (trigger.content || 'Notification')}
                      {trigger.type === 'story' && '📖 Story: ' + (trigger.story_id || 'New Story')}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Story Flags */}
            {unlock.setsStoryFlags && unlock.setsStoryFlags.length > 0 && (
              <div>
                <h5 className="text-xs font-semibold text-white/70 mb-2">Sets Story Flags:</h5>
                <div className="text-xs text-white/50 flex flex-wrap gap-2">
                  {unlock.setsStoryFlags.map((flag, idx) => (
                    <span key={idx} className="px-2 py-1 bg-white/10 rounded">
                      {flag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Category Badge */}
            <div className="text-xs text-white/40 pt-2 border-t border-white/10">
              Category: <span className="text-white/60 capitalize">{unlock.category}</span>
            </div>
          </div>
        )}
      </div>
    );
  };

  const CATEGORY_LABELS = {
    relationship: t('progression.category.relationship') || 'Relationship',
    activities: t('progression.category.activities') || 'Activities',
    narrative: t('progression.category.narrative') || 'Narrative',
    gaming: t('progression.category.gaming') || 'Gaming',
  };

  const CategorySection = ({ category, unlockList }) => {
    if (!unlockList || unlockList.length === 0) {
      return null;
    }

    const isExpanded = expandedCategory[category];
    const activeCount = unlockList.filter(u => u.status === 'active').length;
    const availableCount = unlockList.filter(u => u.status === 'available').length;

    return (
      <div className="space-y-2">
        <button
          onClick={() =>
            setExpandedCategory(prev => ({
              ...prev,
              [category]: !prev[category],
            }))
          }
          className={`w-full p-3 rounded-lg border transition-all text-left flex items-center justify-between ${
            isExpanded
              ? `bg-gradient-to-r ${getCategoryColor(category)} border-white/20`
              : `bg-white/5 border-white/10 hover:border-white/20`
          }`}
        >
          <div className="flex items-center gap-3">
            <span className="text-2xl">{getCategoryIcon(category)}</span>
            <div>
              <h3 className="text-sm font-bold text-white">{CATEGORY_LABELS[category]}</h3>
              <p className="text-xs text-white/50">
                {activeCount} active • {availableCount} available
              </p>
            </div>
          </div>
          {isExpanded ? (
            <ChevronUp size={20} className="text-white/50" />
          ) : (
            <ChevronDown size={20} className="text-white/50" />
          )}
        </button>

        {isExpanded && (
          <div className="pl-6 space-y-2">
            {unlockList.map(unlock => (
              <UnlockCard
                key={unlock.id}
                unlock={unlock}
                isExpanded={expandedUnlock === unlock.id}
                onToggle={() =>
                  setExpandedUnlock(
                    expandedUnlock === unlock.id ? null : unlock.id
                  )
                }
              />
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Unlock Stats */}
      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/20 text-center">
          <div className="text-lg font-bold text-green-400">{unlocks.activeCount || 0}</div>
          <div className="text-xs text-white/50">Active</div>
        </div>
        <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-center">
          <div className="text-lg font-bold text-yellow-400">{unlocks.totalCount || 0}</div>
          <div className="text-xs text-white/50">Total</div>
        </div>
      </div>

      {/* Info Banner */}
      <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 rounded text-xs text-white/70">
        <p>
          ⭐ Feature unlocks are triggered by achievements and metric thresholds. Each unlock can trigger stories and set narrative flags!
        </p>
      </div>

      {/* Categories */}
      <div className="space-y-4">
        <CategorySection
          category="relationship"
          unlockList={unlocks.byCategory?.relationship || []}
        />
        <CategorySection
          category="activities"
          unlockList={unlocks.byCategory?.activities || []}
        />
        <CategorySection
          category="narrative"
          unlockList={unlocks.byCategory?.narrative || []}
        />
        <CategorySection
          category="gaming"
          unlockList={unlocks.byCategory?.gaming || []}
        />
      </div>

      {/* Empty State */}
      {unlocks.totalCount === 0 && (
        <div className="flex items-center justify-center h-48">
          <div className="text-center text-white/50">
            <p>No unlocks available yet</p>
            <p className="text-xs mt-2">Keep progressing to unlock new features!</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default UnlocksTab;
