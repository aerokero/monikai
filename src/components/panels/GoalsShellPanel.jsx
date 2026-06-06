import React, { useMemo } from 'react';
import {
  BookOpenText,
  Flame,
  Gem,
  Heart,
  MessageCircleHeart,
  ScrollText,
  Sparkles,
  Trophy,
} from '../icons';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import useElementSize from '../../hooks/useElementSize';
import { useLanguage } from '../../contexts/LanguageContext';

const clampPercent = (value) => Math.max(0, Math.min(100, value));

const ProgressBar = ({ value = 0, tone = 'from-cyan-500 to-sky-400' }) => (
  <div className="h-2 w-full overflow-hidden rounded-full bg-white/6 ring-1 ring-white/6">
    <div
      className={`h-full rounded-full bg-gradient-to-r ${tone} transition-all duration-500`}
      style={{ width: `${clampPercent(value)}%` }}
    />
  </div>
);

const Card = ({ title, icon: Icon, children, className = '' }) => (
  <section className={`rounded-[18px] border border-white/10 bg-black/20 p-4 ${className}`}>
    <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
      {Icon ? <Icon size={15} className="text-cyan-300" /> : null}
      <span>{title}</span>
    </div>
    {children}
  </section>
);

const GoalsShellPanel = ({ personalityState = {} }) => {
  const { t } = useLanguage();
  const [panelRef, panelSize] = useElementSize();

  const relationship = personalityState?.relationship || {};
  const growth = personalityState?.growth || {};
  const rawQuests = Array.isArray(personalityState?.quests) ? personalityState.quests : [];
  const unlocks = Array.isArray(personalityState?.unlocks) ? personalityState.unlocks : [];

  const bondLevel = Math.max(1, Number(relationship?.bond_level || 1));
  const bondXp = Math.max(0, Number(relationship?.bond_xp || 0));
  const trust = Math.max(0, Math.min(100, Number(relationship?.trust || 0)));
  const playfulness = Math.max(0, Math.min(100, Number(relationship?.playfulness || 0)));
  const closeness = Math.max(0, Math.min(100, Number(relationship?.closeness || 0)));
  const streak = Math.max(0, Number(relationship?.streak_days || 0));

  const growthStats = [
    { id: 'reflection', label: t('goals.stats.reflection'), icon: BookOpenText, value: Number(growth?.reflection || 0), tone: 'from-cyan-500 to-sky-400' },
    { id: 'communication', label: t('goals.stats.communication'), icon: MessageCircleHeart, value: Number(growth?.communication || 0), tone: 'from-pink-500 to-rose-400' },
    { id: 'curiosity', label: t('goals.stats.curiosity'), icon: Sparkles, value: Number(growth?.curiosity || 0), tone: 'from-violet-500 to-fuchsia-400' },
    { id: 'consistency', label: t('goals.stats.consistency'), icon: Flame, value: Number(growth?.consistency || 0), tone: 'from-amber-500 to-orange-400' },
  ];

  const activeVisibleQuests = useMemo(
    () => rawQuests.filter((quest) => quest && quest.status === 'active' && (quest.visibility || 'visible') === 'visible'),
    [rawQuests]
  );
  const completedCount = useMemo(
    () => rawQuests.filter((quest) => quest && quest.status === 'completed').length,
    [rawQuests]
  );
  const averageGrowth = useMemo(
    () => growthStats.reduce((sum, stat) => sum + Math.max(0, Number(stat.value || 0)), 0) / (growthStats.length || 1),
    [growthStats]
  );
  const achievementPct = useMemo(() => {
    const checks = [
      bondLevel >= 2,
      bondLevel >= 4,
      trust >= 40,
      playfulness >= 35,
      streak >= 3,
      averageGrowth >= 25,
      unlocks.length >= 3,
      completedCount >= 2,
    ];
    const unlocked = checks.filter(Boolean).length + 1;
    return Math.round((unlocked / (checks.length + 1)) * 100);
  }, [averageGrowth, bondLevel, completedCount, playfulness, streak, trust, unlocks.length]);

  const unlockEntries = unlocks.map((unlock, index) => {
    if (typeof unlock === 'string') {
      return { id: `${unlock}-${index}`, title: unlock, subtitle: 'Unlocked' };
    }
    return {
      id: unlock?.id || `${unlock?.title || 'unlock'}-${index}`,
      title: unlock?.title || unlock?.name || `Unlock ${index + 1}`,
      subtitle: unlock?.type || unlock?.category || 'Unlocked',
    };
  });

  const lifetimeQuests = [
    {
      id: 'bond3',
      title: t('goals.lifetime.items.bond3.title'),
      description: t('goals.lifetime.items.bond3.desc'),
      current: Math.min(bondLevel, 3),
      target: 3,
      tone: 'from-cyan-500 to-sky-400',
    },
    {
      id: 'trust40',
      title: t('goals.lifetime.items.trust40.title'),
      description: t('goals.lifetime.items.trust40.desc'),
      current: Math.min(Math.round(trust), 40),
      target: 40,
      tone: 'from-emerald-500 to-teal-400',
    },
    {
      id: 'quests5',
      title: t('goals.lifetime.items.quests5.title'),
      description: t('goals.lifetime.items.quests5.desc'),
      current: Math.min(completedCount, 5),
      target: 5,
      tone: 'from-amber-500 to-orange-400',
    },
    {
      id: 'growth30',
      title: t('goals.lifetime.items.growth30.title'),
      description: t('goals.lifetime.items.growth30.desc'),
      current: Math.min(Math.round(averageGrowth), 30),
      target: 30,
      tone: 'from-violet-500 to-fuchsia-400',
    },
  ];

  const isWide = panelSize.width >= 980;

  return (
    <ShellPanelFrame
      icon={Trophy}
      title={t('goals.title')}
      subtitle="Relationship progress, active quests, and unlock tracking without the fixed-width legacy tree."
      bodyClassName="min-h-0"
    >
      <div ref={panelRef} className="flex h-full min-h-0 flex-col overflow-auto p-3 custom-scrollbar">
        <div className="grid gap-3 md:grid-cols-3">
          <Card title="Relationship" icon={Heart}>
            <div className="space-y-3">
              <div>
                <div className="flex items-center justify-between text-xs text-white/62">
                  <span>{t('goals.level')} {bondLevel}</span>
                  <span>{Math.round(bondXp)} XP</span>
                </div>
                <div className="mt-2"><ProgressBar value={Math.min(100, (bondXp % 100))} tone="from-rose-500 to-pink-400" /></div>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-white/38">Trust</div>
                  <div className="mt-1 text-lg text-white">{Math.round(trust)}</div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-white/38">Play</div>
                  <div className="mt-1 text-lg text-white">{Math.round(playfulness)}</div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-white/38">Streak</div>
                  <div className="mt-1 text-lg text-white">{streak}</div>
                </div>
              </div>
              <div>
                <div className="mb-1 text-xs text-white/55">{t('goals.closeness')}</div>
                <ProgressBar value={closeness} tone="from-pink-500 to-rose-400" />
              </div>
            </div>
          </Card>

          <Card title="Growth Summary" icon={Sparkles}>
            <div className="space-y-3">
              {growthStats.map((stat) => (
                <div key={stat.id}>
                  <div className="mb-1 flex items-center justify-between text-xs text-white/60">
                    <span>{stat.label}</span>
                    <span>{Math.round(Math.max(0, stat.value))}</span>
                  </div>
                  <ProgressBar value={stat.value} tone={stat.tone} />
                </div>
              ))}
            </div>
          </Card>

          <Card title="Progress Snapshot" icon={Gem}>
            <div className="space-y-3">
              <div>
                <div className="mb-1 flex items-center justify-between text-xs text-white/60">
                  <span>Overall progression</span>
                  <span>{achievementPct}%</span>
                </div>
                <ProgressBar value={achievementPct} tone="from-cyan-500 via-sky-400 to-blue-500" />
              </div>
              <div className="grid grid-cols-2 gap-2 text-center">
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-white/38">Quests</div>
                  <div className="mt-1 text-lg text-white">{activeVisibleQuests.length}</div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-white/38">Unlocks</div>
                  <div className="mt-1 text-lg text-white">{unlockEntries.length}</div>
                </div>
              </div>
            </div>
          </Card>
        </div>

        <div className={`mt-3 grid gap-3 ${isWide ? 'grid-cols-[minmax(0,1.04fr)_minmax(0,0.96fr)]' : 'grid-cols-1'}`}>
          <Card title={t('goals.daily.title')} icon={ScrollText}>
            <div className="space-y-3">
              {activeVisibleQuests.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-5 text-sm text-white/40">
                  {t('goals.daily.empty')}
                </div>
              ) : (
                activeVisibleQuests.map((quest) => {
                  const target = Math.max(1, Number(quest.target || 1));
                  const progress = Math.max(0, Number(quest.progress || 0));
                  const pct = (progress / target) * 100;
                  return (
                    <div key={quest.id || quest.title} className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-white">{quest.title || t('goals.quest_fallback')}</div>
                          {quest.description ? <div className="mt-1 text-xs text-white/46">{quest.description}</div> : null}
                        </div>
                        <div className="text-xs text-white/44">
                          {Math.round(Math.min(progress, target))}/{Math.round(target)}
                        </div>
                      </div>
                      <div className="mt-3"><ProgressBar value={pct} tone="from-cyan-500 to-sky-400" /></div>
                    </div>
                  );
                })
              )}
            </div>
          </Card>

          <div className="space-y-3">
            <Card title={t('goals.lifetime.title')} icon={Trophy}>
              <div className="space-y-3">
                {lifetimeQuests.map((quest) => (
                  <div key={quest.id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-white">{quest.title}</div>
                        <div className="mt-1 text-xs text-white/46">{quest.description}</div>
                      </div>
                      <div className="text-xs text-white/44">{quest.current}/{quest.target}</div>
                    </div>
                    <div className="mt-3">
                      <ProgressBar value={(quest.current / quest.target) * 100} tone={quest.tone} />
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card title={t('goals.unlocks')} icon={Gem}>
              <div className="space-y-2">
                {unlockEntries.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-5 text-sm text-white/40">
                    {t('goals.unlocks_empty')}
                  </div>
                ) : (
                  unlockEntries.slice(0, 8).map((unlock) => (
                    <div key={unlock.id} className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2.5">
                      <div className="text-sm text-white">{unlock.title}</div>
                      <div className="mt-1 text-xs uppercase tracking-[0.16em] text-white/40">{unlock.subtitle}</div>
                    </div>
                  ))
                )}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </ShellPanelFrame>
  );
};

export default GoalsShellPanel;
