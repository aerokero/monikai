import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  X,
  Sparkles,
  Crown,
  Trophy,
  ScrollText,
  Gem,
  Heart,
  HeartHandshake,
  MessageCircleHeart,
  BookOpenText,
  Flame,
} from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const TREE_NODE_SIZE = 64;
const TREE_CANVAS_W = 920;
const TREE_CANVAS_H = 320;
const TREE_TOOLTIP_W = 290;

const ProgressBar = ({ value = 0, tone = 'from-cyan-500 to-sky-400' }) => (
  <div className="h-2 w-full overflow-hidden rounded-full bg-white/6 ring-1 ring-white/6">
    <div
      className={`h-full rounded-full bg-gradient-to-r ${tone} transition-all duration-500`}
      style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
    />
  </div>
);

const SectionCard = ({ icon: Icon, title, children, className = '' }) => (
  <div className={`rounded-xl border border-white/10 bg-black/20 p-3.5 ${className}`}>
    {title ? (
      <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-white">
        {Icon ? <Icon size={15} className="text-cyan-300" /> : null}
        <span>{title}</span>
      </div>
    ) : null}
    {children}
  </div>
);

const AchievementNode = ({ node, active, onSelect, onHover, onLeave }) => {
  const Icon = node.icon;
  return (
    <button
      onClick={() => onSelect(node.id)}
      onMouseEnter={() => onHover(node.id)}
      onMouseLeave={onLeave}
      onFocus={() => onHover(node.id)}
      onBlur={onLeave}
      className={`absolute flex items-center justify-center rounded-lg border-2 transition-all duration-200 ${
        node.unlocked
          ? 'border-[#d4a42a] bg-[linear-gradient(180deg,#7f5c10,#b88a19)] text-white shadow-[0_0_0_1px_rgba(0,0,0,0.35)_inset,0_8px_24px_rgba(212,164,42,0.18)]'
          : 'border-[#787878] bg-[linear-gradient(180deg,#6a6a6a,#4f4f4f)] text-white/65 shadow-[0_0_0_1px_rgba(0,0,0,0.35)_inset]'
      } ${active ? 'ring-2 ring-cyan-300/70 ring-offset-2 ring-offset-black/60 scale-[1.04]' : 'hover:scale-[1.03]'}`}
      style={{
        left: node.x,
        top: node.y,
        width: TREE_NODE_SIZE,
        height: TREE_NODE_SIZE,
      }}
      title={node.title}
    >
      <Icon size={22} className={node.unlocked ? 'drop-shadow-[0_0_8px_rgba(255,255,255,0.22)]' : ''} />
    </button>
  );
};

const GoalsWindow = ({
  onClose,
  position,
  onMouseDown,
  activeDragElement,
  zIndex,
  personalityState,
  width = 1080,
  height = 760,
}) => {
  const { t } = useLanguage();
  const isStackedLayout = width < 1120;
  const rootRef = useRef(null);
  const treeCanvasRef = useRef(null);

  const relationship = personalityState?.relationship || {};
  const growth = personalityState?.growth || {};
  const rawQuests = Array.isArray(personalityState?.quests) ? personalityState.quests : [];
  const unlocks = Array.isArray(personalityState?.unlocks) ? personalityState.unlocks : [];

  const activeVisibleQuests = useMemo(
    () => rawQuests.filter((q) => q && q.status === 'active' && (q.visibility || 'visible') === 'visible').slice(0, 3),
    [rawQuests]
  );
  const completedCount = useMemo(
    () => rawQuests.filter((q) => q && q.status === 'completed').length,
    [rawQuests]
  );

  const bondLevel = Math.max(1, Number(relationship?.bond_level || 1));
  const bondXp = Math.max(0, Number(relationship?.bond_xp || 0));
  const trust = Math.max(0, Math.min(100, Number(relationship?.trust || 0)));
  const playfulness = Math.max(0, Math.min(100, Number(relationship?.playfulness || 0)));
  const streak = Math.max(0, Number(relationship?.streak_days || 0));
  const reflectionValue = Number(growth?.reflection || 0);
  const communicationValue = Number(growth?.communication || 0);
  const curiosityValue = Number(growth?.curiosity || 0);
  const consistencyValue = Number(growth?.consistency || 0);
  const avgGrowth = (reflectionValue + communicationValue + curiosityValue + consistencyValue) / 4;

  const achievementNodes = useMemo(() => {
    const defs = [
      {
        id: 'first_bond',
        title: t('goals.tree.nodes.first_bond.title'),
        description: t('goals.tree.nodes.first_bond.desc'),
        reward: t('goals.tree.nodes.first_bond.reward'),
        requirement: t('goals.tree.nodes.first_bond.req'),
        unlocked: true,
        icon: Heart,
        x: 36,
        y: 128,
      },
      {
        id: 'bond_lvl_2',
        parent: 'first_bond',
        title: t('goals.tree.nodes.bond_lvl_2.title'),
        description: t('goals.tree.nodes.bond_lvl_2.desc'),
        reward: t('goals.tree.nodes.bond_lvl_2.reward'),
        requirement: t('goals.tree.nodes.bond_lvl_2.req'),
        unlocked: bondLevel >= 2,
        progressLabel: `${Math.min(bondLevel, 2)}/2`,
        icon: HeartHandshake,
        x: 154,
        y: 128,
      },
      {
        id: 'trust_40',
        parent: 'bond_lvl_2',
        title: t('goals.tree.nodes.trust_40.title'),
        description: t('goals.tree.nodes.trust_40.desc'),
        reward: t('goals.tree.nodes.trust_40.reward'),
        requirement: t('goals.tree.nodes.trust_40.req'),
        unlocked: trust >= 40,
        progressLabel: `${Math.round(Math.min(trust, 40))}/40`,
        icon: MessageCircleHeart,
        x: 292,
        y: 42,
      },
      {
        id: 'playful_35',
        parent: 'bond_lvl_2',
        title: t('goals.tree.nodes.playful_35.title'),
        description: t('goals.tree.nodes.playful_35.desc'),
        reward: t('goals.tree.nodes.playful_35.reward'),
        requirement: t('goals.tree.nodes.playful_35.req'),
        unlocked: playfulness >= 35,
        progressLabel: `${Math.round(Math.min(playfulness, 35))}/35`,
        icon: Sparkles,
        x: 292,
        y: 214,
      },
      {
        id: 'reflection_25',
        parent: 'trust_40',
        title: t('goals.tree.nodes.reflection_25.title'),
        description: t('goals.tree.nodes.reflection_25.desc'),
        reward: t('goals.tree.nodes.reflection_25.reward'),
        requirement: t('goals.tree.nodes.reflection_25.req'),
        unlocked: Number(growth?.reflection || 0) >= 25,
        progressLabel: `${Math.round(Math.min(Number(growth?.reflection || 0), 25))}/25`,
        icon: BookOpenText,
        x: 438,
        y: 42,
      },
      {
        id: 'streak_3',
        parent: 'playful_35',
        title: t('goals.tree.nodes.streak_3.title'),
        description: t('goals.tree.nodes.streak_3.desc'),
        reward: t('goals.tree.nodes.streak_3.reward'),
        requirement: t('goals.tree.nodes.streak_3.req'),
        unlocked: streak >= 3,
        progressLabel: `${Math.min(streak, 3)}/3`,
        icon: Flame,
        x: 438,
        y: 214,
      },
      {
        id: 'unlocks_3',
        parent: 'reflection_25',
        title: t('goals.tree.nodes.unlocks_3.title'),
        description: t('goals.tree.nodes.unlocks_3.desc'),
        reward: t('goals.tree.nodes.unlocks_3.reward'),
        requirement: t('goals.tree.nodes.unlocks_3.req'),
        unlocked: unlocks.length >= 3,
        progressLabel: `${Math.min(unlocks.length, 3)}/3`,
        icon: Gem,
        x: 584,
        y: 42,
      },
      {
        id: 'quests_2',
        parent: 'streak_3',
        title: t('goals.tree.nodes.quests_2.title'),
        description: t('goals.tree.nodes.quests_2.desc'),
        reward: t('goals.tree.nodes.quests_2.reward'),
        requirement: t('goals.tree.nodes.quests_2.req'),
        unlocked: completedCount >= 2,
        progressLabel: `${Math.min(completedCount, 2)}/2`,
        icon: ScrollText,
        x: 584,
        y: 214,
      },
      {
        id: 'bond_lvl_4',
        parent: 'unlocks_3',
        title: t('goals.tree.nodes.bond_lvl_4.title'),
        description: t('goals.tree.nodes.bond_lvl_4.desc'),
        reward: t('goals.tree.nodes.bond_lvl_4.reward'),
        requirement: t('goals.tree.nodes.bond_lvl_4.req'),
        unlocked: bondLevel >= 4,
        progressLabel: `${Math.min(bondLevel, 4)}/4`,
        icon: Crown,
        x: 752,
        y: 128,
      },
    ];
    return defs;
  }, [t, bondLevel, trust, playfulness, streak, reflectionValue, unlocks.length, completedCount]);

  const [selectedAchievementId, setSelectedAchievementId] = useState(null);
  const [hoveredAchievementId, setHoveredAchievementId] = useState(null);

  useEffect(() => {
    if (selectedAchievementId && !achievementNodes.some((node) => node.id === selectedAchievementId)) {
      setSelectedAchievementId(null);
    }
  }, [achievementNodes, selectedAchievementId]);

  useEffect(() => {
    if (hoveredAchievementId && !achievementNodes.some((node) => node.id === hoveredAchievementId)) {
      setHoveredAchievementId(null);
    }
  }, [achievementNodes, hoveredAchievementId]);

  const activeAchievementId = hoveredAchievementId || selectedAchievementId || null;
  const activeAchievement = achievementNodes.find((node) => node.id === activeAchievementId) || null;

  const connectors = useMemo(() => {
    const byId = Object.fromEntries(achievementNodes.map((node) => [node.id, node]));
    return achievementNodes
      .filter((node) => node.parent)
      .map((node) => {
        const parent = byId[node.parent];
        if (!parent) return null;
        const x1 = parent.x + TREE_NODE_SIZE;
        const y1 = parent.y + TREE_NODE_SIZE / 2;
        const x2 = node.x;
        const y2 = node.y + TREE_NODE_SIZE / 2;
        const midX = Math.round((x1 + x2) / 2);
        return {
          id: `${parent.id}->${node.id}`,
          points: `${x1},${y1} ${midX},${y1} ${midX},${y2} ${x2},${y2}`,
          unlocked: node.unlocked,
        };
      })
      .filter(Boolean);
  }, [achievementNodes]);

  const unlockedAchievements = achievementNodes.filter((node) => node.unlocked).length;
  const achievementPct = achievementNodes.length ? Math.round((unlockedAchievements / achievementNodes.length) * 100) : 0;

  const activeTooltipPosition = useMemo(() => {
    if (!activeAchievement || !rootRef.current || !treeCanvasRef.current) return null;
    const rootRect = rootRef.current.getBoundingClientRect();
    const treeRect = treeCanvasRef.current.getBoundingClientRect();
    const padding = 16;
    const tooltipH = 176;
    const nodeLeft = treeRect.left - rootRect.left + activeAchievement.x;
    const nodeTop = treeRect.top - rootRect.top + activeAchievement.y;
    const preferredRight = nodeLeft + TREE_NODE_SIZE + TREE_TOOLTIP_W + 28 <= rootRect.width - padding;
    const rawLeft = preferredRight
      ? nodeLeft + TREE_NODE_SIZE + 18
      : nodeLeft - TREE_TOOLTIP_W - 18;
    const rawTop = nodeTop - 10;
    return {
      left: Math.max(padding, Math.min(rawLeft, rootRect.width - TREE_TOOLTIP_W - padding)),
      top: Math.max(padding, Math.min(rawTop, rootRect.height - tooltipH - padding)),
    };
  }, [activeAchievement, width, height, isStackedLayout]);

  const lifetimeQuests = [
    {
      id: 'bond3',
      title: t('goals.lifetime.items.bond3.title'),
      description: t('goals.lifetime.items.bond3.desc'),
      current: Math.min(bondLevel, 3),
      target: 3,
    },
    {
      id: 'trust40',
      title: t('goals.lifetime.items.trust40.title'),
      description: t('goals.lifetime.items.trust40.desc'),
      current: Math.min(Math.round(trust), 40),
      target: 40,
    },
    {
      id: 'quests5',
      title: t('goals.lifetime.items.quests5.title'),
      description: t('goals.lifetime.items.quests5.desc'),
      current: Math.min(completedCount, 5),
      target: 5,
    },
    {
      id: 'growth30',
      title: t('goals.lifetime.items.growth30.title'),
      description: t('goals.lifetime.items.growth30.desc'),
      current: Math.min(Math.round(avgGrowth), 30),
      target: 30,
    },
  ];

  return (
    <div
      id="goals"
      ref={rootRef}
      className={`absolute flex flex-col overflow-hidden rounded-xl border border-white/[0.14] bg-black/55 backdrop-blur-2xl shadow-2xl transition-[box-shadow,border-color] duration-200 ${
        activeDragElement === 'goals' ? 'ring-1 ring-white/50 border-white/30' : ''
      }`}
      style={{
        width,
        height,
        left: position.x,
        top: position.y,
        transform: 'translate(-50%, -50%)',
        zIndex,
      }}
      onMouseDown={onMouseDown}
    >
      <div className="relative border-b border-white/10 bg-white/5 px-4 py-4 handle cursor-grab active:cursor-grabbing" data-drag-handle>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/8 text-white ring-1 ring-white/10">
                <Trophy size={16} />
              </div>
              <div>
                <div className="text-sm font-medium tracking-wider text-white/90 uppercase">{t('goals.title')}</div>
              </div>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-white/50 transition-colors hover:bg-red-500/20 hover:text-red-400">
            <X size={16} />
          </button>
        </div>
      </div>

      <div
        className="grid min-h-0 flex-1 gap-0 overflow-hidden"
        style={{ gridTemplateColumns: isStackedLayout ? 'minmax(0, 1fr)' : 'minmax(0, 1.58fr) minmax(320px, 0.78fr)' }}
      >
        <div className={`min-h-0 overflow-y-auto p-4 ${isStackedLayout ? '' : 'border-r border-white/8'}`}>
          <div className="rounded-xl border border-white/10 bg-black/20 p-3.5">
            <div className="flex items-center justify-between gap-3 text-[13px] font-semibold text-white">
              <div className="flex items-center gap-2">
                <Trophy size={16} className="text-amber-300" />
                <span>{t('goals.tree.summary', { unlocked: unlockedAchievements, total: achievementNodes.length })}</span>
              </div>
              <span className="text-white/72">({achievementPct}%)</span>
            </div>
            <div className="mt-2.5">
              <ProgressBar value={achievementPct} tone="from-sky-400 via-cyan-400 to-blue-500" />
            </div>
          </div>

          <div className="mt-4 rounded-[22px] border border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.04),transparent_24%),linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.015))] p-3.5">
            <div className="overflow-x-auto overflow-y-hidden pb-1">
              <div
                ref={treeCanvasRef}
                className="relative rounded-xl border border-white/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.015))] bg-[length:10px_10px] p-3"
                style={{
                  width: TREE_CANVAS_W,
                  height: TREE_CANVAS_H,
                  backgroundImage:
                    'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)',
                }}
              >
                <svg className="absolute inset-0 pointer-events-none" width={TREE_CANVAS_W} height={TREE_CANVAS_H}>
                  {connectors.map((line) => (
                    <polyline
                      key={line.id}
                      points={line.points}
                      fill="none"
                      stroke={line.unlocked ? 'rgba(244, 196, 70, 0.92)' : 'rgba(255,255,255,0.22)'}
                      strokeWidth="4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  ))}
                  {connectors.map((line) => (
                    <polyline
                      key={`${line.id}-shadow`}
                      points={line.points}
                      fill="none"
                      stroke="rgba(0,0,0,0.4)"
                      strokeWidth="6"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  ))}
                </svg>

                {achievementNodes.map((node) => (
                  <AchievementNode
                    key={node.id}
                    node={node}
                    active={activeAchievement?.id === node.id}
                    onSelect={setSelectedAchievementId}
                    onHover={setHoveredAchievementId}
                    onLeave={() => setHoveredAchievementId(null)}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className={`min-h-0 overflow-y-auto p-4 ${isStackedLayout ? 'border-t border-white/8' : ''}`}>
          <SectionCard icon={ScrollText} title={t('goals.daily.title')}>
            <div className="space-y-3">
              {activeVisibleQuests.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-5 text-sm text-white/40">
                  {t('goals.daily.empty')}
                </div>
              ) : (
                activeVisibleQuests.map((q) => {
                  const target = Math.max(1, Number(q.target || 1));
                  const progress = Math.max(0, Number(q.progress || 0));
                  const pct = Math.max(0, Math.min(100, (progress / target) * 100));
                  return (
                    <div key={q.id || q.title} className="rounded-2xl border border-white/10 bg-white/[0.025] p-2.5">
                      <div className="mb-1.5 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-[13px] font-semibold text-white">{q.title}</div>
                          {q.description ? <div className="mt-1 text-[11px] text-white/42">{q.description}</div> : null}
                        </div>
                        <div className="text-[11px] font-mono text-white/45">
                          {Math.round(Math.min(progress, target))}/{Math.round(target)}
                        </div>
                      </div>
                      <ProgressBar value={pct} tone="from-cyan-500 to-sky-400" />
                    </div>
                  );
                })
              )}
            </div>
          </SectionCard>

          <div className="mt-4">
            <SectionCard icon={Gem} title={t('goals.lifetime.title')}>
              <div className="space-y-3">
                {lifetimeQuests.map((q) => {
                  const pct = Math.max(0, Math.min(100, (q.current / q.target) * 100));
                  return (
                    <div key={q.id} className="rounded-2xl border border-white/10 bg-white/[0.025] p-2.5">
                      <div className="mb-1.5 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-[13px] font-semibold text-white">{q.title}</div>
                          <div className="mt-1 text-[11px] text-white/42">{q.description}</div>
                        </div>
                        <div className="text-[11px] font-mono text-white/45">
                          {q.current}/{q.target}
                        </div>
                      </div>
                      <ProgressBar value={pct} tone="from-amber-500 to-orange-400" />
                    </div>
                  );
                })}
              </div>
            </SectionCard>
          </div>
        </div>
      </div>

      {activeAchievement && activeTooltipPosition ? (
        <div
          className="pointer-events-none absolute z-[80] w-[290px] rounded-xl border border-white/12 bg-black/90 p-3.5 shadow-2xl backdrop-blur-2xl"
          style={{
            left: activeTooltipPosition.left,
            top: activeTooltipPosition.top,
          }}
        >
          <div className="mb-2 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white">{activeAchievement.title}</div>
              <div className="mt-1 text-[12px] leading-relaxed text-white/55">{activeAchievement.description}</div>
            </div>
            <div
              className={`rounded-full border px-2 py-0.5 text-[9px] uppercase tracking-[0.18em] ${
                activeAchievement.unlocked
                  ? 'border-amber-300/18 bg-amber-300/10 text-amber-100/82'
                  : 'border-white/10 bg-black/20 text-white/35'
              }`}
            >
              {activeAchievement.unlocked ? t('goals.tree.status_unlocked') : t('goals.tree.status_locked')}
            </div>
          </div>
          <div className="space-y-2 text-[12px]">
            <div className="rounded-2xl border border-white/8 bg-black/20 px-3 py-2.5">
              <div className="text-[9px] uppercase tracking-[0.2em] text-white/35">{t('goals.tree.requirement')}</div>
              <div className="mt-1 text-white/82">{activeAchievement.requirement}</div>
              {!activeAchievement.unlocked && activeAchievement.progressLabel ? (
                <div className="mt-1 text-[11px] text-white/38">{activeAchievement.progressLabel}</div>
              ) : null}
            </div>
            <div className="rounded-2xl border border-cyan-400/10 bg-cyan-400/8 px-3 py-2.5">
              <div className="text-[9px] uppercase tracking-[0.2em] text-cyan-100/45">{t('goals.tree.reward')}</div>
              <div className="mt-1 text-cyan-50">{activeAchievement.reward}</div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default GoalsWindow;
