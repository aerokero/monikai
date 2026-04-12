import React, { useMemo } from 'react';
import { CheckCircle2, Circle, Zap, Sun, Moon } from 'lucide-react';
import { useProgression } from '../contexts/ProgressionContext';

const QuestCard = ({ quest }) => {
  const isCompleted = quest.status === 'COMPLETED';
  const xpDisplay = quest.reward_xp ? Math.floor(quest.reward_xp) : 0;

  const slotIcons = {
    morning: <Sun size={16} className="text-yellow-400" />,
    afternoon: <Zap size={16} className="text-orange-400" />,
    evening: <Moon size={16} className="text-blue-400" />,
  };

  return (
    <div
      className={`rounded-lg border transition-all p-3 ${
        isCompleted
          ? 'border-white/5 bg-black/40 opacity-60'
          : 'border-white/10 bg-black/30 hover:border-white/20'
      }`}
    >
      <div className="flex items-start gap-3">
        {isCompleted ? (
          <CheckCircle2 size={18} className="mt-1 text-green-400 flex-shrink-0" />
        ) : (
          <Circle size={18} className="mt-1 text-white/30 flex-shrink-0" />
        )}

        <div className="flex-1">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className={`font-medium text-sm ${isCompleted ? 'text-white/50 line-through' : 'text-white'}`}>
                {quest.title}
              </div>
              <p className="text-xs text-white/40 mt-1">{quest.description}</p>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {slotIcons[quest.slot]}
              <span className="text-xs font-semibold text-white/70">{xpDisplay} XP</span>
            </div>
          </div>

          {quest.progress < quest.target && (
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-sky-400 transition-all"
                style={{ width: `${(quest.progress / quest.target) * 100}%` }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export const QuestsPanel = () => {
  const { quests, isLoading } = useProgression();

  const questsBySlot = useMemo(() => {
    return {
      morning: quests.filter(q => q.slot === 'morning'),
      afternoon: quests.filter(q => q.slot === 'afternoon'),
      evening: quests.filter(q => q.slot === 'evening'),
    };
  }, [quests]);

  if (isLoading) {
    return <div className="text-white/50">Ładowanie zadań...</div>;
  }

  if (!quests || quests.length === 0) {
    return <div className="text-white/50">Brak dostępnych zadań na dzisiaj</div>;
  }

  const slots = [
    { id: 'morning', label: 'Poranek', icon: Sun },
    { id: 'afternoon', label: 'Popołudnie', icon: Zap },
    { id: 'evening', label: 'Wieczór', icon: Moon },
  ];

  return (
    <div className="space-y-6">
      <div className="text-lg font-semibold text-white mb-4">Codzienna Rutyna</div>

      {slots.map(({ id, label, icon: Icon }) => {
        const slotQuests = questsBySlot[id] || [];
        const completed = slotQuests.filter(q => q.status === 'COMPLETED').length;

        return (
          <div key={id}>
            <div className="flex items-center gap-2 mb-3">
              <Icon size={18} className="text-white/60" />
              <h3 className="text-sm font-semibold text-white">
                {label}
                <span className="text-white/40 ml-2">
                  ({completed}/{slotQuests.length})
                </span>
              </h3>
            </div>

            {slotQuests.length > 0 ? (
              <div className="space-y-2 ml-6">
                {slotQuests.map(quest => (
                  <QuestCard key={quest.id} quest={quest} />
                ))}
              </div>
            ) : (
              <div className="text-xs text-white/30 ml-6">Brak zadań na ten czas</div>
            )}
          </div>
        );
      })}
    </div>
  );
};
