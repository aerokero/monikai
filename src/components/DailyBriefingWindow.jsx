import React, { useEffect, useMemo, useState } from 'react';
import { X, Newspaper, RefreshCw, Pin, PinOff, Check, XCircle, Sparkles, ExternalLink, CloudSun, CloudRain, CloudSnow, CloudLightning, Sun, Cloud } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const openUrl = (url) => {
  if (!url) return;
  try {
    if (window?.require) {
      const { shell } = window.require('electron');
      shell.openExternal(url);
      return;
    }
  } catch (err) {
    console.error('Failed to open external url:', err);
  }
  window.open(url, '_blank', 'noopener,noreferrer');
};

const getHostLabel = (url) => {
  try {
    if (!url) return '';
    return new URL(url).hostname.replace(/^www\./, '');
  } catch (err) {
    return '';
  }
};

const sectionTone = (sectionId) => {
  if (sectionId === 'technology' || sectionId === 'ai') return 'from-sky-500/30 to-cyan-400/20';
  if (sectionId === 'science' || sectionId === 'space') return 'from-emerald-500/30 to-teal-400/20';
  if (sectionId === 'weather') return 'from-amber-500/30 to-orange-400/20';
  if (sectionId === 'security') return 'from-rose-500/30 to-red-400/20';
  return 'from-indigo-500/30 to-blue-400/20';
};

const parseMinMax = (summary) => {
  const text = String(summary || '').toLowerCase();
  const minMatch = text.match(/min\s*(-?\d+(?:[\.,]\d+)?)/i);
  const maxMatch = text.match(/max\s*(-?\d+(?:[\.,]\d+)?)/i);
  const min = minMatch ? minMatch[1].replace(',', '.') : null;
  const max = maxMatch ? maxMatch[1].replace(',', '.') : null;
  return { min, max };
};

const parseCondition = (summary) => String(summary || '').split('|')[0].trim();

const weatherIconForSummary = (summary) => {
  const s = String(summary || '').toLowerCase();
  if (s.includes('thunder') || s.includes('burza')) return CloudLightning;
  if (s.includes('snow') || s.includes('snieg')) return CloudSnow;
  if (s.includes('rain') || s.includes('deszcz') || s.includes('showers') || s.includes('opady')) return CloudRain;
  if (s.includes('clear') || s.includes('sunny') || s.includes('bezchmurnie') || s.includes('pogodnie')) return Sun;
  if (s.includes('cloud') || s.includes('zachmur')) return Cloud;
  return CloudSun;
};

const formatForecastDay = (value, language) => {
  const asDate = new Date(value);
  if (Number.isNaN(asDate.getTime())) return String(value || '');
  const now = new Date();
  const isToday = asDate.toDateString() === now.toDateString();
  if (isToday) return (language || 'pl').startsWith('pl') ? 'Dzis' : 'Today';
  return asDate.toLocaleDateString(language || 'pl', { month: 'short', day: '2-digit' });
};

const DailyBriefingWindow = ({
  socket,
  onClose,
  position,
  onMouseDown,
  activeDragElement,
  zIndex,
  language,
  embedded = false,
}) => {
  const { t } = useLanguage();
  const [briefing, setBriefing] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeSectionId, setActiveSectionId] = useState('');

  const activeSections = briefing?.sections || [];
  const pinned = briefing?.profile?.pinned_sections || [];

  useEffect(() => {
    if (!activeSections.length) {
      setActiveSectionId('');
      return;
    }
    const exists = activeSections.some((sec) => sec.id === activeSectionId);
    if (!exists) {
      setActiveSectionId(activeSections[0].id);
    }
  }, [activeSections, activeSectionId]);

  const currentSection = useMemo(() => {
    if (!activeSections.length) return null;
    return activeSections.find((sec) => sec.id === activeSectionId) || activeSections[0];
  }, [activeSections, activeSectionId]);

  const breakingItem = useMemo(() => {
    for (const section of activeSections) {
      if (section?.items?.length) return section.items[0];
    }
    return null;
  }, [activeSections]);

  const requestBriefing = (force = false) => {
    setIsLoading(true);
    setError('');
    socket.emit('get_daily_briefing', { language, force });
  };

  useEffect(() => {
    requestBriefing(false);

    const onData = (payload) => {
      setBriefing(payload || null);
      setIsLoading(false);
    };

    const onError = (payload) => {
      const msg = String(payload?.msg || 'Daily briefing error');
      if (msg.toLowerCase().includes('briefing')) {
        setError(msg);
        setIsLoading(false);
      }
    };

    socket.on('daily_briefing_data', onData);
    socket.on('error', onError);

    return () => {
      socket.off('daily_briefing_data', onData);
      socket.off('error', onError);
    };
  }, [socket, language]);

  const updatePinned = (sectionId, shouldPin) => {
    const profile = briefing?.profile;
    if (!profile) return;

    const nextPinned = (profile.pinned_sections || []).filter((id) => id !== sectionId);
    if (shouldPin) nextPinned.push(sectionId);

    const nextProfile = {
      ...profile,
      pinned_sections: nextPinned.slice(0, 3),
    };

    setBriefing((prev) => (prev ? { ...prev, profile: nextProfile } : prev));
    socket.emit('set_daily_briefing_profile', { profile: nextProfile, language });
  };

  const handleAcceptProposal = () => {
    if (!briefing?.proposal) return;
    socket.emit('accept_daily_briefing_proposal', { proposal: briefing.proposal, language });
    setIsLoading(true);
  };

  const handleRejectProposal = () => {
    if (!briefing?.proposal) return;
    socket.emit('reject_daily_briefing_proposal', { proposal: briefing.proposal, language });
    setIsLoading(true);
  };

  return (
    <div
      id="daily_briefing"
      className={`${embedded ? 'monika-embedded-panel' : 'absolute'} flex flex-col transition-[box-shadow,border-color] duration-200
        backdrop-blur-2xl bg-black/50 border border-white/[0.14] shadow-2xl overflow-hidden rounded-xl
        ${activeDragElement === 'daily_briefing' ? 'ring-1 ring-white/50 border-white/30' : ''}
      `}
      style={embedded ? undefined : {
        left: position.x,
        top: position.y,
        transform: 'translate(-50%, -50%)',
        width: 'min(1120px, calc(100vw - 40px))',
        height: 'min(700px, calc(100vh - 90px))',
        pointerEvents: 'auto',
        zIndex,
      }}
      onMouseDown={embedded ? undefined : onMouseDown}
    >
      <div
        className={`flex items-center justify-between p-4 border-b border-white/10 bg-white/5 shrink-0 ${embedded ? '' : 'cursor-grab active:cursor-grabbing'}`}
        data-drag-handle={embedded ? undefined : true}
      >
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-md bg-white/10 border border-white/15 flex items-center justify-center">
            <Newspaper size={16} className="text-white" />
          </div>
          <div>
            <div className="text-lg font-semibold tracking-tight text-white">{t('briefing.title')}</div>
            <div className="text-[11px] text-white/45">Curated intelligence from global sources.</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => requestBriefing(true)}
            className={`px-2.5 py-1.5 text-xs border rounded-md transition-colors inline-flex items-center gap-1.5 ${isLoading ? 'text-white/35 border-white/15' : 'text-white/80 border-white/20 hover:border-white/35 hover:bg-white/10'}`}
            title={t('briefing.refresh')}
          >
            <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
            {t('briefing.refresh')}
          </button>
          {!embedded && (
            <button
              onClick={onClose}
              className="p-1.5 hover:bg-red-500/20 hover:text-red-400 rounded-lg text-white/50 transition-colors"
              title={t('schedule.close')}
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      <div className="px-4 py-3 shrink-0 border-b border-white/10 bg-white/[0.02]">
        <div className="rounded-md border border-white/10 bg-white/[0.03] overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 text-xs text-white/80">
            <span className="text-[10px] font-bold tracking-wide text-red-300 bg-red-500/20 px-1.5 py-0.5 rounded-sm border border-red-400/30">BREAKING</span>
            <span className="truncate">{breakingItem?.title || t('briefing.no_items')}</span>
          </div>
        </div>

        <div className="mt-3 flex items-center gap-2 overflow-x-auto pb-1 custom-scrollbar">
          {activeSections.map((section) => {
            const isActive = currentSection?.id === section.id;
            return (
              <button
                key={section.id}
                onClick={() => setActiveSectionId(section.id)}
                className={`shrink-0 px-3 py-1.5 rounded-md text-xs border transition-colors ${isActive ? 'text-white border-white/35 bg-white/15' : 'text-white/70 border-white/15 hover:border-white/30 hover:bg-white/10'}`}
              >
                {section.title}
              </button>
            );
          })}
        </div>

        {briefing?.proposal && (
          <div className="mt-3 rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-3">
            <div className="flex items-start gap-2 text-emerald-200">
              <Sparkles size={14} className="mt-0.5" />
              <div className="flex-1">
                <div className="text-xs font-medium mb-1">{t('briefing.ai_proposal')}</div>
                <div className="text-xs text-emerald-100/90">{briefing.proposal.reason}</div>
                <div className="text-[11px] text-emerald-200/80 mt-1">
                  {t('briefing.swap')}: {briefing.proposal.from_section} -&gt; {briefing.proposal.to_section} ({Math.round((briefing.proposal.confidence || 0) * 100)}%)
                </div>
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                onClick={handleAcceptProposal}
                className="px-2.5 py-1.5 rounded-md text-xs bg-emerald-500/30 border border-emerald-400/40 text-emerald-100 hover:bg-emerald-500/40"
              >
                <span className="inline-flex items-center gap-1"><Check size={13} /> {t('briefing.accept')}</span>
              </button>
              <button
                onClick={handleRejectProposal}
                className="px-2.5 py-1.5 rounded-md text-xs bg-white/10 border border-white/20 text-white/80 hover:bg-white/15"
              >
                <span className="inline-flex items-center gap-1"><XCircle size={13} /> {t('briefing.reject')}</span>
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 bg-black/30 shrink-0">
        <div className="text-[11px] text-white/45">{t('briefing.dynamic_hint')}</div>
        {currentSection && (
          <button
            onClick={() => updatePinned(currentSection.id, !pinned.includes(currentSection.id))}
            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] border ${pinned.includes(currentSection.id) ? 'text-amber-200 border-amber-400/40 bg-amber-400/10' : 'text-white/75 border-white/20 hover:border-white/35 hover:bg-white/10'}`}
            title={pinned.includes(currentSection.id) ? t('briefing.unpin') : t('briefing.pin')}
          >
            {pinned.includes(currentSection.id) ? <PinOff size={12} /> : <Pin size={12} />}
            {pinned.includes(currentSection.id) ? t('briefing.unpin') : t('briefing.pin')}
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar bg-black/20">
        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">{error}</div>
        )}

        {!isLoading && !currentSection && !error && (
          <div className="h-48 flex flex-col items-center justify-center text-white/35">
            <Newspaper size={26} className="mb-2" />
            <span className="text-xs">{t('briefing.no_items')}</span>
          </div>
        )}

        {currentSection?.error && (
          <div className="rounded-md border border-yellow-500/30 bg-yellow-500/10 p-2 text-[11px] text-yellow-200">
            {currentSection.error}
          </div>
        )}

        {currentSection?.id === 'weather' && (
          <div className="space-y-2">
            {(() => {
              const items = currentSection.items || [];
              const overview = items.find((it) => String(it.kind || '').toLowerCase() === 'overview') || items[0];
              const forecast = items.filter((it) => String(it.kind || '').toLowerCase() === 'forecast');

              return (
                <>
                  {overview && (
                    <div className="rounded-lg border border-white/10 bg-white/[0.04] p-3">
                      <div className="text-3xl font-semibold text-white text-center">{overview.title}</div>
                      <div className="mt-1 text-sm text-white/75 text-center leading-relaxed">{overview.summary}</div>
                    </div>
                  )}

                  <div className="flex gap-2 overflow-x-auto pb-1 custom-scrollbar">
                    {forecast.slice(0, 7).map((item, idx) => {
                      const Icon = weatherIconForSummary(item.summary);
                      const temps = parseMinMax(item.summary);
                      const condition = parseCondition(item.summary);
                      return (
                        <div
                          key={`${currentSection.id}-card-${idx}`}
                          className="shrink-0 w-[210px] rounded-lg border border-white/10 bg-white/[0.04] p-2.5 min-h-[96px]"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="text-sm text-white/90">{formatForecastDay(item.title, language)}</div>
                              <div className="text-xs text-white/55 mt-1">{condition}</div>
                            </div>
                            <Icon size={30} className="text-cyan-300/90 shrink-0" />
                          </div>

                          <div className="mt-2 text-sm text-white/80">
                            <div><span className="text-white/55">Min:</span> {temps.min ? `${temps.min}°C` : '-'}</div>
                            <div><span className="text-white/55">Max:</span> {temps.max ? `${temps.max}°C` : '-'}</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              );
            })()}
          </div>
        )}

        {currentSection?.id !== 'weather' && (currentSection?.items || []).slice(0, 10).map((item, idx) => (
          <div
            key={`${currentSection.id}-${idx}`}
            className="group rounded-md border border-white/10 hover:border-white/30 bg-white/[0.03] hover:bg-white/[0.06] transition-colors p-3"
          >
            <div className="flex items-start gap-3">
              <div className={`mt-0.5 h-9 w-9 rounded-md border border-white/10 bg-gradient-to-br ${sectionTone(currentSection.id)} flex items-center justify-center shrink-0`}>
                <Newspaper size={14} className="text-slate-100" />
              </div>

              <div className="min-w-0 flex-1">
                <div className="text-sm text-white/90 leading-snug">{item.title}</div>
                <div className="mt-1 flex items-center gap-2 text-[11px] text-white/35">
                  <span className="text-cyan-300/90 uppercase tracking-wide">{getHostLabel(item.url) || currentSection.title}</span>
                  {briefing?.generated_at && <span>{new Date(briefing.generated_at).toLocaleTimeString()}</span>}
                </div>
                {item.summary && (
                  <div className="mt-1.5 text-[12px] text-white/65 leading-relaxed">
                    {item.summary.length > 220 ? `${item.summary.slice(0, 220)}...` : item.summary}
                  </div>
                )}
              </div>

              {!!item.url && (
                <button
                  onClick={() => openUrl(item.url)}
                  className="shrink-0 p-1.5 rounded-md text-white/45 hover:text-white hover:bg-white/10"
                  title={t('briefing.open')}
                >
                  <ExternalLink size={13} />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="px-4 py-2 border-t border-white/10 text-[11px] text-white/45 shrink-0 bg-black/20">
        {briefing?.generated_at
          ? `${t('briefing.updated')}: ${new Date(briefing.generated_at).toLocaleString()}`
          : t('briefing.loading')}
      </div>
    </div>
  );
};

export default DailyBriefingWindow;
