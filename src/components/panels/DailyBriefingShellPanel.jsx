import React, { useEffect, useMemo, useState } from 'react';
import {
  Check,
  Cloud,
  CloudLightning,
  CloudRain,
  CloudSnow,
  CloudSun,
  ExternalLink,
  Newspaper,
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
  } catch (error) {
    console.error('Failed to open external url:', error);
  }
  window.open(url, '_blank', 'noopener,noreferrer');
};

const getHostLabel = (url) => {
  try {
    return url ? new URL(url).hostname.replace(/^www\./, '') : '';
  } catch {
    return '';
  }
};

const parseMinMax = (summary) => {
  const text = String(summary || '').toLowerCase();
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
    return (language || 'pl').startsWith('pl') ? 'Dzis' : 'Today';
  }
  return asDate.toLocaleDateString(language || 'pl', { month: 'short', day: '2-digit' });
};

const DailyBriefingShellPanel = ({ socket, language }) => {
  const { t } = useLanguage();
  const [briefing, setBriefing] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeSectionId, setActiveSectionId] = useState('');
  const [activeItemIndex, setActiveItemIndex] = useState(0);
  const [panelRef, panelSize] = useElementSize();

  const sections = briefing?.sections || [];
  const pinned = briefing?.profile?.pinned_sections || [];
  const isWide = panelSize.width >= 940;

  useEffect(() => {
    if (!sections.length) {
      setActiveSectionId('');
      return;
    }
    if (!sections.some((section) => section.id === activeSectionId)) {
      setActiveSectionId(sections[0].id);
    }
  }, [activeSectionId, sections]);

  useEffect(() => {
    setActiveItemIndex(0);
  }, [activeSectionId]);

  const currentSection = useMemo(
    () => sections.find((section) => section.id === activeSectionId) || sections[0] || null,
    [activeSectionId, sections]
  );
  const currentItems = Array.isArray(currentSection?.items) ? currentSection.items : [];
  const activeItem = currentItems[activeItemIndex] || currentItems[0] || null;
  const breakingItem = useMemo(() => {
    for (const section of sections) {
      if (Array.isArray(section?.items) && section.items.length) {
        return section.items[0];
      }
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

    const onData = (payload) => {
      setBriefing(payload || null);
      setIsLoading(false);
      setError('');
    };

    const onError = (payload) => {
      const message = String(payload?.msg || 'Daily briefing error');
      if (message.toLowerCase().includes('briefing')) {
        setError(message);
        setIsLoading(false);
      }
    };

    socket.on('daily_briefing_data', onData);
    socket.on('error', onError);

    return () => {
      socket.off('daily_briefing_data', onData);
      socket.off('error', onError);
    };
  }, [language, socket]);

  const updatePinned = (sectionId, shouldPin) => {
    const profile = briefing?.profile;
    if (!profile || !socket) return;
    const nextPinned = (profile.pinned_sections || []).filter((id) => id !== sectionId);
    if (shouldPin) nextPinned.push(sectionId);
    const nextProfile = { ...profile, pinned_sections: nextPinned.slice(0, 3) };
    setBriefing((current) => (current ? { ...current, profile: nextProfile } : current));
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

  const renderWeatherSection = () => {
    const overview = currentItems.find((item) => String(item.kind || '').toLowerCase() === 'overview') || currentItems[0];
    const forecast = currentItems.filter((item) => String(item.kind || '').toLowerCase() === 'forecast');
    return (
      <div className="grid gap-3 md:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <div className="rounded-[18px] border border-white/10 bg-white/[0.03] p-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-white/40">Weather</div>
          <div className="mt-3 text-3xl font-semibold text-white">{overview?.title || '--'}</div>
          <div className="mt-2 text-sm leading-relaxed text-white/70">{overview?.summary || t('briefing.no_items')}</div>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {forecast.slice(0, 6).map((item, index) => {
            const Icon = weatherIconForSummary(item.summary);
            const temps = parseMinMax(item.summary);
            return (
              <div key={`${currentSection?.id}-forecast-${index}`} className="rounded-[18px] border border-white/10 bg-black/22 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm text-white/90">{formatForecastDay(item.title, language)}</div>
                    <div className="mt-1 text-xs text-white/50">{parseCondition(item.summary)}</div>
                  </div>
                  <Icon size={26} className="text-cyan-300" />
                </div>
                <div className="mt-3 space-y-1 text-sm text-white/76">
                  <div><span className="text-white/45">Min:</span> {temps.min ? `${temps.min}°C` : '-'}</div>
                  <div><span className="text-white/45">Max:</span> {temps.max ? `${temps.max}°C` : '-'}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderStoryDetail = () => {
    if (!activeItem) {
      return (
        <div className="rounded-[18px] border border-dashed border-white/10 bg-white/[0.02] px-4 py-6 text-sm text-white/40">
          {t('briefing.no_items')}
        </div>
      );
    }

    return (
      <article className="rounded-[18px] border border-white/10 bg-white/[0.03] p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-[0.18em] text-cyan-200/70">
              {getHostLabel(activeItem.url) || currentSection?.title}
            </div>
            <h3 className="mt-2 text-lg font-semibold leading-snug text-white">{activeItem.title}</h3>
          </div>
          {activeItem.url ? (
            <button
              onClick={() => openUrl(activeItem.url)}
              className="shrink-0 rounded-xl border border-white/10 bg-white/[0.05] p-2 text-white/70 transition-colors hover:bg-white/[0.1] hover:text-white"
              title={t('briefing.open')}
            >
              <ExternalLink size={15} />
            </button>
          ) : null}
        </div>
        {activeItem.summary ? (
          <p className="mt-4 text-sm leading-relaxed text-white/74">{activeItem.summary}</p>
        ) : null}
      </article>
    );
  };

  return (
    <ShellPanelFrame
      icon={Newspaper}
      title={t('briefing.title')}
      subtitle="Responsive briefing cards with active story focus."
      actions={(
        <button
          onClick={() => requestBriefing(true)}
          className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs transition-colors ${
            isLoading
              ? 'border-white/10 bg-white/[0.03] text-white/35'
              : 'border-white/12 bg-white/[0.06] text-white/78 hover:bg-white/[0.11]'
          }`}
        >
          <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
          {t('briefing.refresh')}
        </button>
      )}
      bodyClassName="min-h-0"
    >
      <div ref={panelRef} className="flex h-full min-h-0 flex-col overflow-auto p-3 custom-scrollbar">
        <div className="rounded-[18px] border border-white/10 bg-white/[0.03] px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-white/84">
            <span className="rounded-full border border-red-400/28 bg-red-500/16 px-2 py-0.5 text-[10px] font-bold tracking-[0.18em] text-red-200">
              BREAKING
            </span>
            <span className="truncate">{breakingItem?.title || t('briefing.no_items')}</span>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {sections.map((section) => {
            const isActive = currentSection?.id === section.id;
            return (
              <button
                key={section.id}
                onClick={() => setActiveSectionId(section.id)}
                className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
                  isActive
                    ? 'border-white/32 bg-white/[0.14] text-white'
                    : 'border-white/10 bg-white/[0.04] text-white/68 hover:bg-white/[0.09]'
                }`}
              >
                {section.title}
              </button>
            );
          })}
          {currentSection ? (
            <button
              onClick={() => updatePinned(currentSection.id, !pinned.includes(currentSection.id))}
              className={`ml-auto inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-colors ${
                pinned.includes(currentSection.id)
                  ? 'border-amber-400/30 bg-amber-400/12 text-amber-100'
                  : 'border-white/12 bg-white/[0.04] text-white/70 hover:bg-white/[0.09]'
              }`}
            >
              {pinned.includes(currentSection.id) ? <PinOff size={12} /> : <Pin size={12} />}
              {pinned.includes(currentSection.id) ? t('briefing.unpin') : t('briefing.pin')}
            </button>
          ) : null}
        </div>

        {briefing?.proposal ? (
          <div className="mt-3 rounded-[18px] border border-emerald-400/25 bg-emerald-400/10 p-4">
            <div className="flex items-start gap-3 text-emerald-100">
              <Sparkles size={15} className="mt-0.5 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">{t('briefing.ai_proposal')}</div>
                <div className="mt-1 text-sm text-emerald-100/88">{briefing.proposal.reason}</div>
                <div className="mt-2 text-xs text-emerald-100/74">
                  {t('briefing.swap')}: {briefing.proposal.from_section} -&gt; {briefing.proposal.to_section} ({Math.round((briefing.proposal.confidence || 0) * 100)}%)
                </div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={handleAcceptProposal}
                className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-300/30 bg-emerald-400/18 px-3 py-2 text-xs text-emerald-100"
              >
                <Check size={13} />
                {t('briefing.accept')}
              </button>
              <button
                onClick={handleRejectProposal}
                className="inline-flex items-center gap-1.5 rounded-xl border border-white/12 bg-white/[0.06] px-3 py-2 text-xs text-white/76"
              >
                <XCircle size={13} />
                {t('briefing.reject')}
              </button>
            </div>
          </div>
        ) : null}

        {v2BriefingText ? (
          <section className="mt-3 rounded-[18px] border border-cyan-300/20 bg-cyan-300/[0.07] p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-cyan-100">
              <Sparkles size={15} />
              <span>{t('briefing.soul_briefing')}</span>
            </div>
            <div className="mt-3 max-h-52 overflow-y-auto whitespace-pre-wrap break-words pr-1 text-sm leading-relaxed text-white/78 custom-scrollbar">
              {v2BriefingText}
            </div>
          </section>
        ) : null}

        {error ? (
          <div className="mt-3 rounded-[18px] border border-red-400/24 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </div>
        ) : null}

        {!error && !isLoading && !currentSection ? (
          <div className="mt-3 rounded-[18px] border border-dashed border-white/10 bg-white/[0.02] px-4 py-8 text-center text-sm text-white/40">
            {t('briefing.no_items')}
          </div>
        ) : null}

        {currentSection?.id === 'weather' ? (
          <div className="mt-3">{renderWeatherSection()}</div>
        ) : currentSection ? (
          <div className={`mt-3 grid min-h-0 gap-3 ${isWide ? 'grid-cols-[minmax(280px,0.82fr)_minmax(0,1.18fr)]' : 'grid-cols-1'}`}>
            <div className="space-y-2">
              {currentItems.slice(0, 10).map((item, index) => (
                <button
                  key={`${currentSection.id}-${index}`}
                  onClick={() => setActiveItemIndex(index)}
                  className={`w-full rounded-[18px] border p-3 text-left transition-colors ${
                    index === activeItemIndex
                      ? 'border-white/28 bg-white/[0.12] text-white'
                      : 'border-white/10 bg-white/[0.03] text-white/74 hover:bg-white/[0.08]'
                  }`}
                >
                  <div className="text-xs uppercase tracking-[0.18em] text-cyan-200/62">
                    {getHostLabel(item.url) || currentSection.title}
                  </div>
                  <div className="mt-2 text-sm font-medium leading-snug">{item.title}</div>
                  {item.summary ? (
                    <div className="mt-2 text-xs leading-relaxed text-white/50">
                      {item.summary.length > 150 ? `${item.summary.slice(0, 150)}...` : item.summary}
                    </div>
                  ) : null}
                </button>
              ))}
            </div>
            <div className="min-h-0">{renderStoryDetail()}</div>
          </div>
        ) : null}

        <div className="mt-3 text-[11px] text-white/42">
          {briefing?.generated_at ? `${t('briefing.updated')}: ${new Date(briefing.generated_at).toLocaleString()}` : t('briefing.loading')}
        </div>
      </div>
    </ShellPanelFrame>
  );
};

export default DailyBriefingShellPanel;
