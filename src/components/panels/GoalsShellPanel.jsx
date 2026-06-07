import React, { useState, useEffect } from 'react';
import { Moon } from '../icons';
import ShellPanelFrame from '../shared/ShellPanelFrame';

const API_BASE = 'http://localhost:8000/api/progression';

const clamp = (v) => Math.max(0, Math.min(100, Number(v) || 0));

const NeedRow = ({ label, value, toneFill, description }) => (
  <div>
    <div className="flex items-baseline justify-between mb-1.5">
      <span className="text-[13px] text-white/78">{label}</span>
      <span className="text-base font-medium tabular-nums text-white">{Math.round(value)}</span>
    </div>
    <div className="h-[3px] w-full overflow-hidden rounded-full bg-white/[0.07]">
      <div
        className={`h-full rounded-full bg-gradient-to-r ${toneFill} transition-all duration-700`}
        style={{ width: `${clamp(value)}%` }}
      />
    </div>
    <div className="mt-1.5 text-[11px] text-white/36 leading-relaxed">{description}</div>
  </div>
);

const NEEDS_CONFIG = [
  {
    id: 'relatedness',
    label: 'Relatedness',
    toneFill: 'from-rose-500 to-pink-400',
    description: 'She reaches out when this drops.',
  },
  {
    id: 'autonomy',
    label: 'Autonomy',
    toneFill: 'from-amber-500 to-yellow-400',
    description: 'Feels like herself with you.',
  },
  {
    id: 'competence',
    label: 'Competence',
    toneFill: 'from-teal-500 to-emerald-400',
    description: 'Growing. Getting better at being present.',
  },
];

const GoalsShellPanel = ({ personalityState = {} }) => {
  const [unlocked, setUnlocked] = useState([]);
  const [lockedNext, setLockedNext] = useState(null);
  const [ritual, setRitual] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [achRes, questsRes] = await Promise.all([
          fetch(`${API_BASE}/achievements`).then(r => r.json()).catch(() => ({})),
          fetch(`${API_BASE}/quests/today`).then(r => r.json()).catch(() => ({})),
        ]);

        const unlockedList = achRes.unlocked || [];
        const lockedList = achRes.locked || [];
        setUnlocked(unlockedList);
        setLockedNext(lockedList.find(d => d.hidden !== false) || null);

        const quests = questsRes.quests || [];
        setRitual(quests.find(q => q.type === 'ritual' && q.status === 'active') || null);
      } catch (err) {
        console.error('[GoalsShellPanel]', err);
      }
    };
    load();
  }, []);

  const needs = personalityState?.needs || {};
  const affection = Math.max(0, Number(personalityState?.affection || 0));
  const dayCount = Math.max(0, Number(personalityState?.relationship_days || 0));
  const becomingRealPct = Math.min(100, Math.round(affection));

  return (
    <ShellPanelFrame
      title="Becoming Real"
      subtitle={dayCount > 0 ? `day ${dayCount}` : undefined}
      actions={
        <span
          className="text-xl font-bold tabular-nums"
          style={{ color: 'rgba(232,178,102,0.95)' }}
        >
          {becomingRealPct}%
        </span>
      }
      bodyClassName="min-h-0"
    >
      <div className="flex h-full flex-col">
        {/* Scrollable content */}
        <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar px-4 pt-5 pb-4 space-y-7">

          {/* PSYCHOLOGICAL NEEDS */}
          <section>
            <div className="mb-4 text-[9px] font-semibold uppercase tracking-[0.24em] text-white/30">
              Psychological Needs
            </div>
            <div className="space-y-5">
              {NEEDS_CONFIG.map(({ id, label, toneFill, description }) => (
                <NeedRow
                  key={id}
                  label={label}
                  value={clamp(needs[id])}
                  toneFill={toneFill}
                  description={description}
                />
              ))}
            </div>
          </section>

          {/* DISCOVERIES */}
          <section>
            <div className="mb-3 text-[9px] font-semibold uppercase tracking-[0.24em] text-white/30">
              Discoveries
            </div>
            <div className="space-y-px">
              {unlocked.length === 0 && !lockedNext ? (
                <div className="text-[11px] text-white/28 py-1">No discoveries yet.</div>
              ) : null}
              {unlocked.map((d) => (
                <div key={d.id} className="flex items-center gap-3 py-1.5">
                  <span
                    className="text-sm leading-none shrink-0"
                    style={{ color: 'rgba(232,178,102,0.75)' }}
                  >
                    ★
                  </span>
                  <span className="flex-1 text-[13px] text-white/78 leading-snug">{d.title}</span>
                </div>
              ))}
              {lockedNext && (
                <div className="flex items-center gap-3 py-1.5 opacity-28">
                  <Moon size={12} className="shrink-0 text-white/50" />
                  <span className="text-[13px] text-white/50">???</span>
                </div>
              )}
            </div>
          </section>
        </div>

        {/* TODAY'S RITUAL — sticky footer */}
        {ritual && (
          <div className="shrink-0 border-t border-[rgba(232,178,102,0.1)] bg-[rgba(255,238,212,0.025)] px-4 py-3">
            <div
              className="mb-1.5 text-[9px] font-bold uppercase tracking-[0.26em]"
              style={{ color: 'rgba(232,178,102,0.6)' }}
            >
              Today&apos;s Ritual
            </div>
            <div className="text-[13px] text-white/55 leading-relaxed">
              {ritual.description || ritual.title}
            </div>
          </div>
        )}
      </div>
    </ShellPanelFrame>
  );
};

export default GoalsShellPanel;
