import React, { useState } from 'react';
import { CheckCircle, Clock, Zap } from '../icons';
import { useProgression } from '../../contexts/ProgressionContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { calculateQuestExpiration, getQuestSlotIcon, formatTimestamp } from '../../utils/progressionTransformers';

/**
 * QuestsTab Component
 * 
 * Displays daily quests grouped by time slot:
 * - Morning (☀️) - sleep/mood check quests
 * - Afternoon (⚡) - activity quests
 * - Evening (🌙) - reflection quests
 * 
 * Shows: title, description, progress, reward, status, completion button
 */
const QuestsTab = () => {
  const { quests, completeQuest } = useProgression();
  const { t } = useLanguage();
  const [completingQuestId, setCompletingQuestId] = useState(null);

  if (!quests) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-white/50 text-center">
          <p>{t('common.loading') || 'Loading quests...'}</p>
        </div>
      </div>
    );
  }

  const handleCompleteQuest = async (questId, rewardXP, rewardMetric) => {
    setCompletingQuestId(questId);
    await completeQuest(questId);
    
    setTimeout(() => {
      setCompletingQuestId(null);
    }, 500);
  };

  const QuestCard = ({ quest, slot }) => {
    if (!quest) return null;

    const expiration = calculateQuestExpiration(quest.expiresAt);
    const isCompleted = quest.status === 'completed';
    const isActive = quest.status === 'active' && !expiration.expired;
    const isExpired = expiration.expired || quest.status === 'expired';
    const isSkipped = quest.status === 'skipped';

    const statusColor = isCompleted
      ? 'text-green-400'
      : isActive
      ? 'text-cyan-400'
      : isSkipped
      ? 'text-yellow-400'
      : 'text-red-400';

    const barColor = isCompleted
      ? 'from-green-500 to-emerald-500'
      : isActive
      ? 'from-cyan-500 to-sky-500'
      : isSkipped
      ? 'from-yellow-500 to-amber-500'
      : 'from-red-500 to-rose-500';

    return (
      <div className="p-3 rounded-lg border border-white/10 hover:border-white/20 transition-all hover:bg-white/5">
        {/* Header */}
        <div className="flex items-start justify-between mb-2">
          <div className="flex-1">
            <h4 className="text-sm font-bold text-white">{quest.title}</h4>
            <p className="text-xs text-white/50 mt-1">{quest.description}</p>
          </div>
          <div className={`text-xs font-semibold px-2 py-1 rounded ${statusColor} border border-current/20`}>
            {isCompleted ? '✓ Done' : isActive ? 'Active' : isSkipped ? 'Skipped' : 'Expired'}
          </div>
        </div>

        {/* Progress Bar (if applicable) */}
        {quest.target > 1 && (
          <div className="mb-2">
            <div className="h-2 bg-white/10 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 bg-gradient-to-r ${barColor}`}
                style={{ width: `${(quest.progress / quest.target) * 100}%` }}
              />
            </div>
            <p className="text-xs text-white/40 mt-1">
              Progress: {quest.progress.toFixed(1)} / {quest.target}
            </p>
          </div>
        )}

        {/* Reward Info */}
        <div className="flex items-center justify-between mb-3 text-xs">
          <div className="text-white/60">
            <Zap size={14} className="inline mr-1" />
            {quest.rewardXP} XP to {quest.rewardMetric}
          </div>
          {isActive && !expiration.expired && (
            <div className="text-yellow-400 font-semibold">
              <Clock size={14} className="inline mr-1" />
              {expiration.hours}h {expiration.minutes}m left
            </div>
          )}
        </div>

        {/* Complete Button */}
        {isActive && !expiration.expired && (
          <button
            onClick={() => handleCompleteQuest(quest.id, quest.rewardXP, quest.rewardMetric)}
            disabled={completingQuestId === quest.id}
            className="w-full px-3 py-2 text-sm rounded bg-green-500/20 hover:bg-green-500/30 text-green-300 transition-colors disabled:opacity-50 disabled:cursor-wait flex items-center justify-center gap-2"
          >
            <CheckCircle size={16} />
            {completingQuestId === quest.id ? '✓ Completing...' : 'Complete Quest'}
          </button>
        )}

        {/* Metadata */}
        {isCompleted && quest.completedAt && (
          <div className="text-xs text-white/30 mt-2 italic">
            Completed: {formatTimestamp(quest.completedAt)}
          </div>
        )}
      </div>
    );
  };

  const SlotSection = ({ slot, quests: slotQuests, icon, label }) => {
    if (!slotQuests || slotQuests.length === 0) {
      return null;
    }

    const activeCount = slotQuests.filter(q => q.status === 'active').length;
    const completedCount = slotQuests.filter(q => q.status === 'completed').length;

    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xl">{icon}</span>
          <h3 className="text-sm font-bold text-white">{label}</h3>
          <span className="text-xs text-white/40">
            {activeCount}/{completedCount} completed
          </span>
        </div>

        <div className="space-y-2 pl-6">
          {slotQuests.map(quest => (
            <QuestCard key={quest.id} quest={quest} slot={slot} />
          ))}
        </div>
      </div>
    );
  };

  const totalQuests = (quests.morning?.length || 0) + (quests.afternoon?.length || 0) + (quests.evening?.length || 0);
  const totalCompleted = 
    (quests.morning?.filter(q => q.status === 'completed').length || 0) +
    (quests.afternoon?.filter(q => q.status === 'completed').length || 0) +
    (quests.evening?.filter(q => q.status === 'completed').length || 0);

  return (
    <div className="space-y-6">
      {/* Daily Progress Banner */}
      <div className="p-4 rounded-lg bg-gradient-to-r from-blue-500/10 to-cyan-500/10 border border-white/10">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-white/50 mb-2">Today's Progress</p>
            <p className="text-2xl font-bold text-white">
              {totalCompleted}/{totalQuests} Quests
            </p>
          </div>
          <div className="h-16 w-16 rounded-lg bg-white/10 flex items-center justify-center">
            <div className="text-center">
              <div className="text-xl font-bold text-cyan-400">{Math.round((totalCompleted / totalQuests) * 100)}%</div>
              <div className="text-xs text-white/50">complete</div>
            </div>
          </div>
        </div>
      </div>

      {/* Info Banner */}
      <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 rounded text-xs text-white/70">
        <p>
          🎯 Complete daily quests to grow your relationship metrics and unlock new achievements!
        </p>
      </div>

      {/* Quests by Slot */}
      <div className="space-y-6">
        <SlotSection
          slot="morning"
          quests={quests.morning}
          icon="☀️"
          label={t('progression.morning') || 'Morning'}
        />
        <SlotSection
          slot="afternoon"
          quests={quests.afternoon}
          icon="⚡"
          label={t('progression.afternoon') || 'Afternoon'}
        />
        <SlotSection
          slot="evening"
          quests={quests.evening}
          icon="🌙"
          label={t('progression.evening') || 'Evening'}
        />
      </div>

      {totalQuests === 0 && (
        <div className="flex items-center justify-center h-48">
          <div className="text-center text-white/50">
            <p>No quests available today</p>
            <p className="text-xs mt-2">Come back tomorrow or interact with Monika!</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default QuestsTab;
