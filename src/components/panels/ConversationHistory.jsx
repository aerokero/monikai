import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, Gamepad2, MessageSquare, Plus, RefreshCw, Send, Trash2 } from '../icons';
import { useLanguage } from '../../contexts/LanguageContext';

// v3 Phase G: conversation history view. Talks to the backend socket API
// (conversations_list / conversations_get / conversations_new /
// conversations_continue). Old conversations are READ-ONLY — "continue"
// starts a fresh session seeded with the old one's digest.

function formatTime(startedAt) {
  if (!startedAt) return '';
  const match = String(startedAt).match(/T(\d{2}:\d{2})/);
  return match ? match[1] : '';
}

function streamMeta(item, t) {
  if (item.channel === 'minecraft') {
    return { icon: Gamepad2, label: t('conversations.stream_minecraft') || 'Minecraft — daily log' };
  }
  return { icon: Send, label: t('conversations.stream_telegram') || `${item.channel} — daily log` };
}

const ConversationHistory = ({ socket = null, active = false, onStarted = () => {}, variant = 'dock' }) => {
  const { t } = useLanguage();
  // dock: compact card inside the chat dock; shell: fills a full rail panel.
  const containerClass =
    variant === 'shell'
      ? 'flex h-full min-h-0 flex-col'
      : 'mb-3 flex max-h-[46vh] flex-col rounded-[18px] border border-[rgba(232,178,102,0.12)] bg-black/45 shadow-[0_14px_34px_rgba(0,0,0,0.48)] backdrop-blur-md';
  const [items, setItems] = useState([]);
  const [currentId, setCurrentId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  // Two-step inline delete confirmation. Native window.confirm() is off the
  // table: in Electron it breaks keyboard focus for the whole window.
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  useEffect(() => {
    if (!confirmDeleteId) return undefined;
    const timer = setTimeout(() => setConfirmDeleteId(null), 4000);
    return () => clearTimeout(timer);
  }, [confirmDeleteId]);

  const refresh = useCallback(() => {
    if (!socket) return;
    setLoading(true);
    socket.emit('conversations_list', { limit: 80 });
  }, [socket]);

  useEffect(() => {
    if (!socket) return undefined;

    const onList = (payload) => {
      setItems(Array.isArray(payload?.items) ? payload.items : []);
      setCurrentId(payload?.current_id || null);
      setLoading(false);
    };
    const onDetail = (payload) => {
      setDetail(payload?.item || null);
      setLoading(false);
    };
    const onStartedEvent = () => {
      setDetail(null);
      refresh();
      onStarted();
    };
    const onDeleted = (payload) => {
      const deletedId = payload?.id;
      setDetail((current) => (current && current.id === deletedId ? null : current));
      setItems((current) => current.filter((item) => item.id !== deletedId));
      if (payload?.current_id) setCurrentId(payload.current_id);
    };

    socket.on('conversations_list', onList);
    socket.on('conversation_detail', onDetail);
    socket.on('conversation_started', onStartedEvent);
    socket.on('conversation_deleted', onDeleted);
    return () => {
      socket.off('conversations_list', onList);
      socket.off('conversation_detail', onDetail);
      socket.off('conversation_started', onStartedEvent);
      socket.off('conversation_deleted', onDeleted);
    };
  }, [socket, refresh, onStarted]);

  useEffect(() => {
    if (active) refresh();
  }, [active, refresh]);

  const grouped = useMemo(() => {
    const byDay = new Map();
    for (const item of items) {
      if (!byDay.has(item.day)) byDay.set(item.day, []);
      byDay.get(item.day).push(item);
    }
    return Array.from(byDay.entries());
  }, [items]);

  const openDetail = (item) => {
    if (!socket) return;
    setLoading(true);
    socket.emit('conversations_get', { id: item.id, max_turns: 400 });
  };

  const startNew = () => {
    if (socket) socket.emit('conversations_new', {});
  };

  const continueConversation = (id) => {
    if (socket) socket.emit('conversations_continue', { id });
  };

  const requestDelete = (item) => {
    if (!socket) return;
    if (confirmDeleteId === item.id) {
      setConfirmDeleteId(null);
      socket.emit('conversations_delete', { id: item.id });
    } else {
      setConfirmDeleteId(item.id);
    }
  };

  // ------------------------------------------------------------------
  // Detail (read-only transcript)
  // ------------------------------------------------------------------
  if (detail) {
    const isStream = detail.kind === 'stream';
    const isCurrent = detail.id === currentId;
    const title = detail.title
      || (isStream ? streamMeta(detail, t).label : (t('conversations.untitled') || 'Conversation'));
    return (
      <div className={containerClass}>
        <div className="flex items-center gap-2 border-b border-[rgba(232,178,102,0.14)] px-3 py-2">
          <button
            type="button"
            onClick={() => setDetail(null)}
            title={t('conversations.back') || 'Back'}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[rgba(255,224,190,0.5)] transition hover:bg-[rgba(255,238,212,0.08)] hover:text-[rgba(255,240,218,0.85)]"
          >
            <ChevronLeft size={15} />
          </button>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-white">{title}</div>
            <div className="text-[11px] text-[rgba(255,224,190,0.45)]">
              {detail.day}
              {isCurrent ? ` · ${t('conversations.current') || 'current'}` : ''}
            </div>
          </div>
          {!isCurrent && !isStream && (
            <button
              type="button"
              onClick={() => continueConversation(detail.id)}
              className="shrink-0 rounded-full border border-[rgba(232,178,102,0.3)] bg-[rgba(232,178,102,0.14)] px-3 py-1 text-[12px] font-medium text-[rgba(255,226,180,0.95)] transition hover:bg-[rgba(232,178,102,0.24)]"
            >
              {t('conversations.continue') || 'Continue this conversation'}
            </button>
          )}
          <button
            type="button"
            onClick={() => requestDelete(detail)}
            title={t('conversations.delete') || 'Delete conversation'}
            className={`flex h-7 shrink-0 items-center justify-center gap-1 rounded-lg transition ${
              confirmDeleteId === detail.id
                ? 'bg-[rgba(166,72,58,0.28)] px-2 text-[12px] font-semibold text-[#f0ad9d]'
                : 'w-7 text-[rgba(255,224,190,0.4)] hover:bg-[rgba(166,72,58,0.18)] hover:text-[#f0ad9d]'
            }`}
          >
            <Trash2 size={14} />
            {confirmDeleteId === detail.id ? (t('conversations.delete_sure') || 'Delete?') : null}
          </button>
        </div>
        {detail.recap ? (
          <div className="border-b border-[rgba(232,178,102,0.1)] px-4 py-2 text-[12.5px] italic leading-relaxed text-[rgba(255,240,218,0.62)]">
            {detail.recap}
          </div>
        ) : null}
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3 custom-scrollbar">
          {(detail.turns || []).map((turn, index) => {
            const sender = String(turn.sender || '?');
            const fromAI = sender === 'AI';
            return (
              <div key={`turn-${index}`} className={`flex ${fromAI ? 'justify-start' : 'justify-end'}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed ${
                    fromAI
                      ? 'bg-[rgba(10,8,7,0.6)] text-[rgba(255,248,238,0.88)]'
                      : 'bg-[rgba(232,178,102,0.12)] text-[rgba(255,246,233,0.85)]'
                  }`}
                >
                  {!fromAI && sender !== 'User' ? (
                    <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-[rgba(232,178,102,0.6)]">
                      {sender}
                    </div>
                  ) : null}
                  {String(turn.text || '')}
                </div>
              </div>
            );
          })}
          {!(detail.turns || []).length && (
            <div className="py-4 text-center text-[13px] text-[rgba(255,224,190,0.4)]">
              {t('chat.no_messages') || 'No messages yet.'}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // List (grouped by day)
  // ------------------------------------------------------------------
  return (
    <div className={containerClass}>
      <div className="flex items-center gap-2 border-b border-[rgba(232,178,102,0.14)] px-3 py-2">
        <div className="flex-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[rgba(232,178,102,0.72)]">
          {variant === 'shell' ? '' : (t('conversations.title') || 'Conversations')}
        </div>
        <button
          type="button"
          onClick={refresh}
          title={t('conversations.refresh') || 'Refresh'}
          className="flex h-7 w-7 items-center justify-center rounded-lg text-[rgba(255,224,190,0.42)] transition hover:bg-[rgba(255,238,212,0.08)] hover:text-[rgba(255,240,218,0.8)]"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </button>
        <button
          type="button"
          onClick={startNew}
          className="flex items-center gap-1 rounded-full border border-[rgba(232,178,102,0.3)] bg-[rgba(232,178,102,0.14)] px-2.5 py-1 text-[12px] font-medium text-[rgba(255,226,180,0.95)] transition hover:bg-[rgba(232,178,102,0.24)]"
        >
          <Plus size={13} />
          {t('conversations.new') || 'New conversation'}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2 custom-scrollbar">
        {grouped.length === 0 && (
          <div className="py-5 text-center text-[13px] text-[rgba(255,224,190,0.4)]">
            {loading ? (t('conversations.loading') || 'Loading…') : (t('conversations.empty') || 'No saved conversations yet.')}
          </div>
        )}
        {grouped.map(([day, dayItems]) => (
          <div key={day} className="mb-2">
            <div className="px-2 py-1 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[rgba(255,224,190,0.36)]">
              {day}
            </div>
            <div className="space-y-1">
              {dayItems.map((item) => {
                const isStream = item.kind === 'stream';
                const isCurrent = item.id === currentId;
                const meta = isStream ? streamMeta(item, t) : null;
                const Icon = isStream ? meta.icon : MessageSquare;
                const title = item.title
                  || (isStream
                    ? meta.label
                    : `${t('conversations.untitled') || 'Conversation'} ${formatTime(item.started_at)}`.trim());
                return (
                  <div
                    key={item.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => openDetail(item)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        openDetail(item);
                      }
                    }}
                    className={`group flex w-full cursor-pointer items-start gap-2.5 rounded-xl border px-2.5 py-2 text-left transition ${
                      isCurrent
                        ? 'border-[rgba(232,178,102,0.32)] bg-[rgba(232,178,102,0.09)]'
                        : isStream
                          ? 'border-[rgba(120,200,150,0.14)] bg-[rgba(120,200,150,0.04)] hover:border-[rgba(120,200,150,0.28)] hover:bg-[rgba(120,200,150,0.08)]'
                          : 'border-transparent hover:border-[rgba(232,178,102,0.2)] hover:bg-[rgba(255,238,212,0.05)]'
                    }`}
                  >
                    <div
                      className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                        isStream
                          ? 'bg-[rgba(120,200,150,0.16)] text-[rgba(190,235,205,0.9)]'
                          : 'bg-[rgba(232,178,102,0.14)] text-[rgba(255,226,180,0.85)]'
                      }`}
                    >
                      <Icon size={14} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-[13px] font-medium text-[rgba(255,246,233,0.9)]">{title}</span>
                        {isCurrent && (
                          <span className="shrink-0 rounded-full bg-[rgba(232,178,102,0.2)] px-1.5 py-px text-[9.5px] font-semibold uppercase tracking-wide text-[rgba(255,226,180,0.9)]">
                            {t('conversations.current') || 'current'}
                          </span>
                        )}
                        {item.continues && (
                          <span className="shrink-0 rounded-full bg-white/10 px-1.5 py-px text-[9.5px] uppercase tracking-wide text-white/50">
                            {t('conversations.continued') || 'continuation'}
                          </span>
                        )}
                      </div>
                      {isStream ? (
                        <div className="mt-0.5 line-clamp-2 text-[12px] leading-snug text-[rgba(255,240,218,0.5)]">
                          {item.recap || (t('conversations.no_recap') || 'Recap appears once the day is processed.')}
                        </div>
                      ) : (
                        <div className="mt-0.5 text-[11px] text-[rgba(255,224,190,0.4)]">
                          {formatTime(item.started_at)}
                          {item.turn_count ? ` · ${item.turn_count} ${t('conversations.turns') || 'messages'}` : ''}
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        requestDelete(item);
                      }}
                      title={t('conversations.delete') || 'Delete conversation'}
                      className={`mt-0.5 flex h-7 shrink-0 items-center justify-center gap-1 rounded-lg transition ${
                        confirmDeleteId === item.id
                          ? 'bg-[rgba(166,72,58,0.28)] px-2 text-[11px] font-semibold !text-[#f0ad9d]'
                          : 'w-7 text-transparent group-hover:text-[rgba(255,224,190,0.4)] hover:!text-[#f0ad9d] hover:bg-[rgba(166,72,58,0.18)]'
                      }`}
                    >
                      <Trash2 size={13} />
                      {confirmDeleteId === item.id ? (t('conversations.delete_sure') || 'Delete?') : null}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ConversationHistory;
