import React, { useEffect, useMemo, useState } from 'react';
import {
  Check,
  Cloud,
  CloudLightning,
  CloudRain,
  CloudSnow,
  CloudSun,
  ExternalLink,
  Pin,
  PinOff,
  RefreshCw,
  Sparkles,
  Sun,
  XCircle,
} from '../icons';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import useElementSize from '../../hooks/useElementSize';
import { useLanguage } from '../../contexts/LanguageContext';

const openUrl = (url) => {
  if (!url) return;
  try {
    if (window?.require) {
      const { shell } = window.require('electron');
      shell.openExternal(url);
      return;
    }
  } catch {}
  window.open(url, '_blank', 'noopener,noreferrer');
};

const getHostLabel = (url) => {
  try { return url ? new URL(url).hostname.replace(/^www\./, '') : ''; } catch { return ''; }
};

const parseMinMax = (summary) => {
  const text = String(summary || '');
  const minMatch = text.match(/min\s*(-?\d+(?:[\.,]\d+)?)/i);
  const maxMatch = text.match(/max\s*(-?\d+(?:[\.,]\d+)?)/i);
  return {
    min: minMatch ? minMatch[1].replace(',', '.') : null,
    max: maxMatch ? maxMatch[1].replace(',', '.') : null,
  };
};

const parseCondition = (summary) => String(summary || '').split('|')[0].trim();

const weatherIconForSummary = (summary) => {
  const text = String(summary || '').toLowerCase();
  if (text.includes('thunder') || text.includes('burza')) return CloudLightning;
  if (text.includes('snow') || text.includes('snieg')) return CloudSnow;
  if (text.includes('rain') || text.includes('deszcz') || text.includes('showers') || text.includes('opady')) return CloudRain;
  if (text.includes('clear') || text.includes('sunny') || text.includes('bezchmurnie') || text.includes('pogodnie')) return Sun;
  if (text.includes('cloud') || text.includes('zachmur')) return Cloud;
  return CloudSun;
};

const formatForecastDay = (value, language) => {
  const asDate = new Date(value);
  if (Number.isNaN(asDate.getTime())) return String(value || '');
  const now = new Date();
  if (asDate.toDateString() === now.toDateString()) {
    return (language || 'pl').startsWith('pl') ? 'Dzisiaj' : 'Today';
  }
  return asDate.toLocaleDateString(language || 'pl', { weekday: 'short', month: 'short', day: 'numeric' });
};

/* ── Shared card — identical structure to calendar event card ──── */
const BriefingCard = ({ meta, title, description, icon: Icon, url, onClick, active }) => (
  <div
    role={onClick ? 'button' : undefined}
    tabIndex={onClick ? 0 : undefined}
    onClick={onClick}
    onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick() : undefined}
    className={`rounded-lg border p-4 transition-colors ${
      active
        ? 'border-[#de9d50]/30 bg-[#de9d50]/[0.06]'
        : 'border-[#2c1e15] bg-[#140d08]/40 hover:border-[#3c2e26]'
    } ${onClick ? 'cursor-pointer' : ''}`}
  >
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        {meta && <div className="mb-0.5 text-xs text-[#8c7769]">{meta}</div>}
        <div className="text-sm font-semibold text-[#f5e6d3]">{title}</div>
        {description && <div className="mt-1 text-xs text-[#8c7769]">{description}</div>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {Icon && <Icon size={15} className="text-[#de9d50]" />}
        {url && (
          <button
            onClick={(e) => { e.stopPropagation(); openUrl(url); }}
            className="rounded-full border border-[#3c2e26] bg-[#1e1612] p-1.5 text-[#8c7769] transition-colors hover:border-[#de9d50] hover:text-[#de9d50]"
          >
            <ExternalLink size={11} />
          </button>
        )}
      </div>
    </div>
  </div>
);

const DailyBriefingShellPanel = ({ socket, language }) => {
  const { t } = useLanguage();
  const [briefing, setBriefing] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeSectionId, setActiveSectionId] = useState('');
  const [panelRef] = useElementSize();

  const sections = briefing?.sections || [];
  const pinned = briefing?.profile?.pinned_sections || [];

  useEffect(() => {
    if (!sections.length) { setActiveSectionId(''); return; }
    if (!sections.some((s) => s.id === activeSectionId)) setActiveSectionId(sections[0].id);
  }, [activeSectionId, sections]);

  const currentSection = useMemo(
    () => sections.find((s) => s.id === activeSectionId) || sections[0] || null,
    [activeSectionId, sections],
  );
  const currentItems = Array.isArray(currentSection?.items) ? currentSection.items : [];

  const breakingItem = useMemo(() => {
    for (const section of sections) {
      if (Array.isArray(section?.items) && section.items.length) return section.items[0];
    }
    return null;
  }, [sections]);

  const v2BriefingText = String(briefing?.v2_briefing?.text || '').trim();

  const requestBriefing = (force = false) => {
    if (!socket) return;
    setIsLoading(true);
    setError('');
    socket.emit('get_daily_briefing', { language, force });
  };

  useEffect(() => {
    if (!socket) return undefined;
    requestBriefing(false);
    const onData = (payload) => { setBriefing(payload || null); setIsLoading(false); setError(''); };
    const onError = (payload) => {
      const msg = String(payload?.msg || '');
      if (msg.toLowerCase().includes('briefing')) { setError(msg); setIsLoading(false); }
    };
    socket.on('daily_briefing_data', onData);
    socket.on('error', onError);
    return () => { socket.off('daily_briefing_data', onData); socket.off('error', onError); };
  }, [language, socket]);

  const updatePinned = (sectionId, shouldPin) => {
    const profile = briefing?.profile;
    if (!profile || !socket) return;
    const nextPinned = (profile.pinned_sections || []).filter((id) => id !== sectionId);
    if (shouldPin) nextPinned.push(sectionId);
    const nextProfile = { ...profile, pinned_sections: nextPinned.slice(0, 3) };
    setBriefing((cur) => (cur ? { ...cur, profile: nextProfile } : cur));
    socket.emit('set_daily_briefing_profile', { profile: nextProfile, language });
  };

  const handleAcceptProposal = () => {
    if (!briefing?.proposal || !socket) return;
    socket.emit('accept_daily_briefing_proposal', { proposal: briefing.proposal, language });
    setIsLoading(true);
  };
  const handleRejectProposal = () => {
    if (!briefing?.proposal || !socket) return;
    socket.emit('reject_daily_briefing_proposal', { proposal: briefing.proposal, language });
    setIsLoading(true);
  };

  /* ── Weather: vertical list identical to calendar event list ──── */
  const renderWeatherItems = () => {
    const overview = currentItems.find((item) => String(item.kind || '').toLowerCase() === 'overview') || currentItems[0];
    const forecast = currentItems.filter((item) => String(item.kind || '').toLowerCase() === 'forecast');

    return (
      <div className="space-y-1.5">
        {/* Overview — like a calendar "today" event */}
        {overview && (() => {
          const Icon = weatherIconForSummary(overview.summary);
          return (
            <BriefingCard
              meta={`${t('briefing.today') || 'Dzisiaj'} · Pogoda`}
              title={overview.title}
              description={overview.summary}
              icon={Icon}
            />
          );
        })()}
        {/* Forecast days — each as a calendar-style event card */}
        {forecast.map((item, index) => {
          const Icon = weatherIconForSummary(item.summary);
          const temps = parseMinMax(item.summary);
          const condition = parseCondition(item.summary);
          const tempStr = (temps.min || temps.max)
            ? [temps.min ? `Min ${temps.min}°` : null, temps.max ? `Max ${temps.max}°` : null].filter(Boolean).join(' · ')
            : null;
          return (
            <BriefingCard
              key={`forecast-${index}`}
              meta={`${formatForecastDay(item.title, language)} · Prognoza`}
              title={condition || item.title}
              description={tempStr}
              icon={Icon}
            />
          );
        })}
      </div>
    );
  };

  /* ── News: vertical list identical to calendar event list ─────── */
  const renderNewsItems = () => (
    <div className="space-y-1.5">
      {currentItems.slice(0, 12).map((item, index) => {
        const host = getHostLabel(item.url);
        const meta = [host || currentSection?.title, item.published_at ? new Date(item.published_at).toLocaleDateString(language || 'pl') : null]
          .filter(Boolean).join(' · ');
        const description = item.summary
          ? (item.summary.length > 180 ? `${item.summary.slice(0, 180)}…` : item.summary)
          : null;
        return (
          <BriefingCard
            key={`${currentSection?.id}-${index}`}
            meta={meta}
            title={item.title}
            description={description}
            url={item.url}
          />
        );
      })}
    </div>
  );

  /* ── Render ───────────────────────────────────────────────────── */
  return (
    <ShellPanelFrame
      icon={null}
      title={t('briefing.title')}
      titleClassName="font-serif text-[28px] text-[#f5e6d3] font-normal tracking-wide py-1"
      headerClassName="flex items-start justify-between gap-4 border-b border-[#2c1e15] bg-transparent px-6 pt-6 pb-4"
      bodyClassName="flex flex-col h-full overflow-hidden"
      actions={(
        <button
          onClick={() => requestBriefing(true)}
          className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
            isLoading
              ? 'border-[#2c1e15] bg-[#1e1612] text-[#8c7769]/40'
              : 'border-[#3c2e26] bg-[#1e1612] text-[#8c7769] hover:border-[#de9d50] hover:text-[#de9d50]'
          }`}
        >
          <RefreshCw size={12} className={`mr-1.5 inline ${isLoading ? 'animate-spin' : ''}`} />
          {t('briefing.refresh')}
        </button>
      )}
    >
      <div ref={panelRef} className="flex-1 overflow-y-auto px-6 py-4 pb-10 custom-scrollbar text-sm">
        <div className="flex flex-col gap-4">

          {/* BREAKING — same card style */}
          {breakingItem && (
            <div className="rounded-lg border border-[#2c1e15] bg-[#140d08]/40 px-4 py-3">
              <div className="flex items-center gap-2.5">
                <span className="shrink-0 rounded-full border border-red-400/30 bg-red-500/14 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.2em] text-red-300">
                  Breaking
                </span>
                <span className="truncate text-sm text-[#f5e6d3]/80">{breakingItem.title}</span>
              </div>
            </div>
          )}

          {/* Section tabs — same pill switcher as calendar */}
          {sections.length > 0 && (
            <div className="flex items-center gap-2">
              <div className="flex flex-1 gap-1 rounded-full border border-[#3c2e26] bg-[#1e1612] p-1">
                {sections.map((section) => {
                  const isActive = currentSection?.id === section.id;
                  return (
                    <button
                      key={section.id}
                      onClick={() => setActiveSectionId(section.id)}
                      className={`flex-1 rounded-full py-1.5 text-xs font-semibold transition-all ${
                        isActive ? 'bg-[#de9d50] text-[#16100d]' : 'text-[#8c7769] hover:text-[#f5e6d3]'
                      }`}
                    >
                      {section.title}
                    </button>
                  );
                })}
              </div>
              {currentSection && (
                <button
                  onClick={() => updatePinned(currentSection.id, !pinned.includes(currentSection.id))}
                  className={`rounded-full border p-2 transition-colors ${
                    pinned.includes(currentSection.id)
                      ? 'border-[#de9d50] bg-[#de9d50]/[0.1] text-[#de9d50]'
                      : 'border-[#3c2e26] bg-[#1e1612] text-[#8c7769] hover:border-[#de9d50] hover:text-[#de9d50]'
                  }`}
                >
                  {pinned.includes(currentSection.id) ? <PinOff size={12} /> : <Pin size={12} />}
                </button>
              )}
            </div>
          )}

          {/* AI Proposal */}
          {briefing?.proposal && (
            <div className="rounded-lg border border-[#de9d50]/20 bg-[#de9d50]/[0.04] p-4">
              <div className="flex items-start gap-3">
                <Sparkles size={13} className="mt-0.5 shrink-0 text-[#de9d50]" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-[#f5e6d3]">{t('briefing.ai_proposal')}</div>
                  <div className="mt-0.5 text-xs text-[#8c7769]">{briefing.proposal.reason}</div>
                  <div className="mt-1 text-xs text-[#8c7769]/50">
                    {briefing.proposal.from_section} → {briefing.proposal.to_section} · {Math.round((briefing.proposal.confidence || 0) * 100)}%
                  </div>
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <button onClick={handleAcceptProposal} className="flex-1 rounded-full bg-[#de9d50] py-2 text-xs font-bold text-[#16100d] hover:brightness-110">
                  <Check size={11} className="mr-1 inline" />{t('briefing.accept')}
                </button>
                <button onClick={handleRejectProposal} className="flex-1 rounded-full border border-[#3c2e26] bg-[#1e1612] py-2 text-xs text-[#8c7769] hover:text-[#f5e6d3]">
                  <XCircle size={11} className="mr-1 inline" />{t('briefing.reject')}
                </button>
              </div>
            </div>
          )}

          {/* Soul briefing */}
          {v2BriefingText && (
            <div className="rounded-lg border border-[#de9d50]/18 bg-[#de9d50]/[0.04] p-4">
              <div className="mb-2 flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.22em] text-[#de9d50]/70">
                <Sparkles size={10} />{t('briefing.soul_briefing')}
              </div>
              <div className="max-h-40 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-[#8c7769] custom-scrollbar">
                {v2BriefingText}
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-lg border border-red-400/20 bg-red-500/8 px-4 py-3 text-xs text-red-300">{error}</div>
          )}

          {/* Loading / empty */}
          {isLoading && !currentSection && (
            <div className="flex items-center justify-center py-12 text-sm text-[#8c7769]/50">{t('briefing.loading')}</div>
          )}
          {!isLoading && !error && !currentSection && (
            <div className="flex items-center justify-center py-12 text-sm text-[#8c7769]/50">{t('briefing.no_items')}</div>
          )}

          {/* Content — weather or news, both as vertical lists */}
          {currentSection?.id === 'weather' && renderWeatherItems()}
          {currentSection && currentSection.id !== 'weather' && renderNewsItems()}

          {/* Timestamp */}
          {briefing?.generated_at && (
            <div className="text-[11px] text-[#8c7769]/40">
              {t('briefing.updated')}: {new Date(briefing.generated_at).toLocaleString()}
            </div>
          )}

        </div>
      </div>
    </ShellPanelFrame>
  );
};

export default DailyBriefingShellPanel;
