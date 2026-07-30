import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Mic,
  MicOff,
  Plus,
  Sparkles,
  Terminal,
  Upload,
  X,
} from '../icons';
import AudioBar from '../AudioBar';
import { useAudioVideo } from '../../contexts/AudioVideoContext';
import { useLanguage } from '../../contexts/LanguageContext';

const MAX_FILES = 6;
const MAX_FILE_BYTES = 12 * 1024 * 1024;
const MAX_TOTAL_BYTES = 30 * 1024 * 1024;

function bytesToBase64(bytes) {
  let binary = '';
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

async function fileToAttachmentPayload(file) {
  const buf = await file.arrayBuffer();
  const b64 = bytesToBase64(new Uint8Array(buf));
  return {
    name: file.name,
    mime_type: file.type || 'application/octet-stream',
    data: b64,
    size: file.size,
  };
}

function sanitizeUrl(url) {
  try {
    const parsed = new URL(url, window.location.origin);
    return ['http:', 'https:', 'mailto:', 'tel:'].includes(parsed.protocol) ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function parseInlineMarkdown(text) {
  if (!text) return null;
  const tokenRe = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^\s)]+\))/g;
  const parts = [];
  let last = 0;
  let match;

  while ((match = tokenRe.exec(text)) !== null) {
    if (match.index > last) {
      parts.push({ type: 'text', value: text.slice(last, match.index) });
    }
    const token = match[0];
    if (token.startsWith('**') && token.endsWith('**')) {
      parts.push({ type: 'bold', value: token.slice(2, -2) });
    } else if (token.startsWith('`') && token.endsWith('`')) {
      parts.push({ type: 'code', value: token.slice(1, -1) });
    } else if (token.startsWith('[')) {
      const closeBracket = token.indexOf('](');
      parts.push({
        type: 'link',
        label: token.slice(1, closeBracket),
        url: token.slice(closeBracket + 2, -1),
      });
    } else {
      parts.push({ type: 'text', value: token });
    }
    last = match.index + token.length;
  }

  if (last < text.length) {
    parts.push({ type: 'text', value: text.slice(last) });
  }

  return parts.map((part, index) => {
    if (part.type === 'bold') {
      return <strong key={index} className="font-semibold">{part.value}</strong>;
    }
    if (part.type === 'code') {
      return (
        <code key={index} className="rounded-md border border-white/10 bg-black/30 px-1 py-0.5 font-mono text-[0.95em]">
          {part.value}
        </code>
      );
    }
    if (part.type === 'link') {
      const safe = sanitizeUrl(part.url);
      if (!safe) return <span key={index}>{`${part.label} (${part.url})`}</span>;
      return (
        <a key={index} href={safe} target="_blank" rel="noreferrer" className="underline underline-offset-2 text-white/90 hover:text-white">
          {part.label}
        </a>
      );
    }
    return <span key={index}>{part.value}</span>;
  });
}

function renderMarkdown(text) {
  return String(text || '').split('\n').map((line, index, lines) => (
    <span key={index}>
      {parseInlineMarkdown(line)}
      {index < lines.length - 1 ? <br /> : null}
    </span>
  ));
}

function cleanDialogueText(text) {
  return String(text || '')
    .replace(/<\/?internal>/gi, '')
    // A stream cut off mid-tag (reconnect glitch) can leave a dangling
    // "<", "</" or "</intern" fragment at the very end — never real content.
    .replace(/<\/?[a-zA-Z]{0,20}$/, '')
    .trim();
}

const ChatPanel = ({
  messages = [],
  inputValue = '',
  setInputValue = () => {},
  handleSend = () => {},
  socket = null,
  userSpeaking = false,
  micAudioData = null,
  isExpanded = false,
  onToggleExpand = () => {},
  agenticLogs = [],
  onMinimizedChange = null,
  onSizeChange = null,
  sessionActive = false,
  compactDock = false,
}) => {
  const { t } = useLanguage();
  const { isMuted, toggleMute } = useAudioVideo();
  const rootRef = useRef(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const draftTimerRef = useRef(null);
  const draftRequestIdRef = useRef('');

  const [attachments, setAttachments] = useState([]);
  const [attachError, setAttachError] = useState('');
  const [prevAgenticLogLength, setPrevAgenticLogLength] = useState(0);
  const [conversationLab, setConversationLab] = useState(() => {
    try {
      return localStorage.getItem('conversation_lab_enabled') === 'true';
    } catch {
      return false;
    }
  });
  const [draftSet, setDraftSet] = useState(null);
  const [draftIndex, setDraftIndex] = useState(0);
  const [draftBusy, setDraftBusy] = useState(false);
  const [draftError, setDraftError] = useState('');
  const [draftProgress, setDraftProgress] = useState(null);
  
  // Auto-show agentic log when there's new agent activity (context-based)
  const hasAgenticActivity = useMemo(() => agenticLogs && agenticLogs.length > 0, [agenticLogs]);
  const [showAgenticLog, setShowAgenticLog] = useState(() => {
    try {
      return localStorage.getItem('show_agentic_log') === 'true';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, showAgenticLog]);

  // Auto-show agentic log when new agent activity detected
  useEffect(() => {
    const currentLength = agenticLogs ? agenticLogs.length : 0;
    if (currentLength > prevAgenticLogLength && currentLength > 0) {
      setShowAgenticLog(true);
      setPrevAgenticLogLength(currentLength);
    } else if (currentLength > prevAgenticLogLength) {
      setPrevAgenticLogLength(currentLength);
    }
  }, [agenticLogs, prevAgenticLogLength]);

  useEffect(() => {
    if (typeof onMinimizedChange === 'function') {
      onMinimizedChange(false);
    }
  }, [onMinimizedChange]);

  useEffect(() => {
    const node = rootRef.current;
    if (!node || typeof onSizeChange !== 'function') return undefined;
    const notify = () => onSizeChange(node.getBoundingClientRect().height);
    notify();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => notify());
    observer.observe(node);
    return () => observer.disconnect();
  }, [onSizeChange, attachments.length, showAgenticLog, isExpanded]);

  useEffect(() => () => {
    attachments.forEach((item) => {
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    });
  }, [attachments]);

  useEffect(() => {
    if (!socket) return undefined;
    const onProgress = (payload) => {
      if (
        payload?.request_id
        && payload.request_id !== draftRequestIdRef.current
      ) {
        return;
      }
      setDraftProgress(payload || null);
    };
    const onDisconnect = () => {
      if (!draftRequestIdRef.current) return;
      if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
      draftTimerRef.current = null;
      draftRequestIdRef.current = '';
      setDraftBusy(false);
      setDraftError('Połączenie z backendem zostało przerwane.');
      setDraftProgress(null);
    };
    socket.on('conversation_draft_progress', onProgress);
    socket.on('disconnect', onDisconnect);
    return () => {
      socket.off('conversation_draft_progress', onProgress);
      socket.off('disconnect', onDisconnect);
    };
  }, [socket]);

  useEffect(() => () => {
    if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
  }, []);

  const visibleMessages = useMemo(() => {
    const list = Array.isArray(messages) ? messages : [];
    return list.filter((message) => !String(message?.sender || '').includes('(Thought)')).slice(-40);
  }, [messages]);

  const visibleAgenticLogs = useMemo(() => {
    const source = Array.isArray(agenticLogs) ? agenticLogs : [];
    return source.slice(-120);
  }, [agenticLogs]);

  const totalAttachBytes = useMemo(
    () => attachments.reduce((sum, item) => sum + (item?.file?.size || 0), 0),
    [attachments]
  );
  const canSend = (
    Boolean((inputValue || '').trim()) || attachments.length > 0
  ) && !draftBusy && !draftSet;
  const dialogueMessages = visibleMessages.slice(-8);
  const draftProgressLabel = useMemo(() => {
    const stage = draftProgress?.stage;
    if (stage === 'compiling_context') return 'Kompiluję historię, postać i aktywne lore…';
    if (stage === 'context_ready') return 'Kontekst gotowy. Uruchamiam model tekstowy…';
    if (stage === 'generating_candidate') {
      return `Generuję wariant ${Math.min(
        (draftProgress?.ready_count || 0) + 1,
        draftProgress?.target_count || 3,
      )} z ${draftProgress?.target_count || 3}…`;
    }
    if (stage === 'candidate_ready') {
      return `Gotowe ${draftProgress?.ready_count || 0} z ${
        draftProgress?.target_count || 3
      } wariantów…`;
    }
    if (stage === 'timeout') return 'Model przekroczył limit czasu; zachowuję gotowe warianty…';
    return 'Wysyłam żądanie do backendu…';
  }, [draftProgress]);
  const userSenderAliases = useMemo(() => {
    const aliases = new Set(['you', 'ty', 'user']);
    const localizedYou = String(t('chat.you') || '').trim().toLowerCase();
    if (localizedYou) aliases.add(localizedYou);
    return aliases;
  }, [t]);

  const isUserMessage = (sender) => userSenderAliases.has(String(sender || '').trim().toLowerCase());

  const clearAttachments = () => {
    setAttachments((current) => {
      current.forEach((item) => {
        if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      });
      return [];
    });
    setAttachError('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const addFiles = (fileList) => {
    setAttachError('');
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;

    setAttachments((current) => {
      const next = [...current];
      const createdPreviewUrls = [];

      for (const file of incoming) {
        if (next.length >= MAX_FILES) {
          setAttachError(`You can attach up to ${MAX_FILES} files.`);
          break;
        }
        if (file.size > MAX_FILE_BYTES) {
          setAttachError(`${file.name} exceeds the 12 MB file limit.`);
          continue;
        }
        const alreadyAdded = next.some(
          (item) =>
            item.file &&
            item.file.name === file.name &&
            item.file.size === file.size &&
            item.file.lastModified === file.lastModified
        );
        if (alreadyAdded) continue;

        const isImage = (file.type || '').startsWith('image/');
        const previewUrl = isImage ? URL.createObjectURL(file) : null;
        if (previewUrl) createdPreviewUrls.push(previewUrl);
        next.push({
          id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(16).slice(2)}`,
          file,
          previewUrl,
        });
      }

      const nextTotal = next.reduce((sum, item) => sum + (item?.file?.size || 0), 0);
      if (nextTotal > MAX_TOTAL_BYTES) {
        setAttachError('Total attachments cannot exceed 30 MB.');
        createdPreviewUrls.forEach((url) => URL.revokeObjectURL(url));
        return current;
      }

      return next;
    });
  };

  const removeAttachment = (id) => {
    setAttachments((current) => {
      const item = current.find((entry) => entry.id === id);
      if (item?.previewUrl) URL.revokeObjectURL(item.previewUrl);
      return current.filter((entry) => entry.id !== id);
    });
  };

  const handleSendMessage = async () => {
    if (!canSend) return;

    let payloadAttachments = [];
    if (attachments.length) {
      try {
        payloadAttachments = await Promise.all(attachments.map((item) => fileToAttachmentPayload(item.file)));
      } catch {
        setAttachError('Failed to prepare attachments.');
        return;
      }
    }

    const useConversationLab = conversationLab && attachments.length === 0;
    if (useConversationLab) {
      if (!socket?.connected) {
        setDraftError('Backend jest rozłączony. Uruchom serwer i połącz sesję.');
        return;
      }
      const requestId = `draft-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      draftRequestIdRef.current = requestId;
      setDraftBusy(true);
      setDraftError('');
      setDraftProgress({ stage: 'requesting', ready_count: 0, target_count: 3 });
      draftTimerRef.current = setTimeout(() => {
        if (draftRequestIdRef.current !== requestId) return;
        draftRequestIdRef.current = '';
        draftTimerRef.current = null;
        setDraftBusy(false);
        setDraftProgress(null);
        setDraftError(
          'Generowanie przekroczyło 35 sekund. Backend lub model nie odpowiedział.',
        );
      }, 35000);
      handleSend({
        key: 'Enter',
        attachments: payloadAttachments,
        conversationLab: true,
        candidateCount: 3,
        requestId,
        onDraftResult: (result) => {
          if (draftRequestIdRef.current !== requestId) return;
          if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
          draftTimerRef.current = null;
          draftRequestIdRef.current = '';
          setDraftBusy(false);
          setDraftProgress(null);
          if (!result?.ok || !Array.isArray(result?.candidates) || !result.candidates.length) {
            const contextError = result?.trace?.context?.error;
            setDraftError(
              contextError
                ? `Błąd kontekstu: ${contextError}`
                : (result?.error || 'Nie udało się przygotować wariantów.'),
            );
            return;
          }
          setDraftSet(result);
          setDraftIndex(0);
        },
      });
    } else {
      handleSend({ key: 'Enter', attachments: payloadAttachments });
    }
    clearAttachments();
    textareaRef.current?.focus();
  };

  const toggleConversationLab = () => {
    const next = !conversationLab;
    setConversationLab(next);
    try {
      localStorage.setItem('conversation_lab_enabled', String(next));
    } catch {}
  };

  const selectDraft = () => {
    if (!socket || !draftSet || draftBusy) return;
    setDraftBusy(true);
    setDraftError('');
    socket.emit(
      'conversation_draft_select',
      {
        response_set_id: draftSet.response_set_id,
        index: draftIndex,
        speak: true,
      },
      (result) => {
        setDraftBusy(false);
        if (!result?.ok) {
          setDraftError(result?.error || 'Nie udało się zatwierdzić odpowiedzi.');
          return;
        }
        setDraftSet(null);
        setDraftIndex(0);
      },
    );
  };

  const cancelDraft = () => {
    if (socket && draftSet?.response_set_id) {
      socket.emit('conversation_draft_cancel', {
        response_set_id: draftSet.response_set_id,
      });
    }
    setDraftSet(null);
    setDraftIndex(0);
    setDraftBusy(false);
    setDraftError('');
    setDraftProgress(null);
    draftRequestIdRef.current = '';
    if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
    draftTimerRef.current = null;
  };

  const handleKeyDown = async (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      await handleSendMessage();
    }
  };

  return (
    <div
      ref={rootRef}
      className={`monika-chat-panel-root relative flex h-full w-full min-h-0 flex-col justify-end overflow-visible px-4 pb-3 pt-0 box-border transition-[box-shadow,background-color] duration-700 ${
        compactDock ? 'is-compact-dock' : ''
      } ${
        sessionActive ? 'rounded-2xl ring-1 ring-amber-400/20 bg-amber-500/[0.025] shadow-[0_0_60px_-15px_rgba(245,158,11,0.25)]' : ''
      }`}
    >
      {/* Subtle "you've stepped into a different space" cue during a session */}
      {sessionActive && (
        <div className="flex items-center justify-center shrink-0 -mb-1 z-20">
          <span className="rounded-full bg-amber-500/15 border border-amber-400/20 px-3 py-0.5 text-[11px] font-medium tracking-wide text-amber-200/90">
            {t('companion.session.title') || 'Sesja'}
          </span>
        </div>
      )}
      {!compactDock && (
        <div className="absolute right-6 top-1 z-30">
          <button
            onClick={onToggleExpand}
            className="rounded-lg border border-[rgba(232,178,102,0.12)] bg-black/25 p-1.5 text-[rgba(255,224,190,0.38)] transition hover:bg-[rgba(232,178,102,0.08)] hover:text-[rgba(255,240,218,0.74)]"
            title={isExpanded ? 'Collapse' : 'Expand'}
          >
            <Maximize2 size={15} />
          </button>
        </div>
      )}

      {/* Main Box - Chat content */}
      <div
        className="relative flex-1 min-h-0 overflow-hidden border-0 bg-transparent flex flex-col"
        style={{
          background: 'transparent',
          backdropFilter: 'none',
          boxShadow: 'none',
        }}
      >
        {/* Content Area - Main scrollable messages */}
        {!compactDock && (
          <div className="monika-chat-panel-content flex-1 min-h-0 overflow-y-auto custom-scrollbar relative flex flex-col px-1 pb-2 pt-0 z-10">
          <div className="flex min-h-full flex-col">
            <div className="mt-auto" />
            {showAgenticLog && hasAgenticActivity ? (
              <div className="mb-3 max-h-32 overflow-hidden rounded-[12px] border border-[rgba(232,178,102,0.14)] bg-black/45 shadow-[0_10px_28px_rgba(0,0,0,0.32)]">
                <div className="flex items-center gap-2 border-b border-[rgba(232,178,102,0.14)] px-3 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-[rgba(232,178,102,0.72)]">
                  <Terminal size={12} />
                  Agent Log
                </div>
                <div className="max-h-24 space-y-1 overflow-y-auto px-3 py-2 font-mono text-[12px] text-[rgba(255,240,218,0.58)] custom-scrollbar">
                  {visibleAgenticLogs.length === 0 ? (
                    <div>Thinking...</div>
                  ) : (
                    visibleAgenticLogs.map((entry, index) => (
                      <div key={`agentic-${index}`} className="break-words">
                        <span className="mr-2 text-[rgba(232,178,102,0.62)]">{'>'}</span>
                        {String(entry || '')}
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : null}

            {dialogueMessages.length > 0 ? (
              <div className="mb-4 px-5">
                <div className="space-y-6 pr-2">
                  {dialogueMessages.map((message, index) => {
                    const fromUser = isUserMessage(message.sender);
                    const isLatest = index === dialogueMessages.length - 1;
                    const text = cleanDialogueText(message.text);
                    if (!text) return null;
                    if (fromUser) {
                      return (
                        <div key={message.id || `dialogue-${index}`} className="flex justify-end">
                          <div className={`max-w-[min(72%,38rem)] rounded-full bg-[rgba(18,18,18,0.68)] px-6 py-3 text-[clamp(0.95rem,1.05vw,1.08rem)] font-medium leading-snug text-[rgba(255,246,233,0.9)] shadow-[0_10px_24px_rgba(0,0,0,0.28)] backdrop-blur-sm ${
                            isLatest ? '' : 'opacity-[0.66]'
                          }`}>
                            {renderMarkdown(text)}
                          </div>
                        </div>
                      );
                    }

                    return (
                      <div
                        key={message.id || `dialogue-${index}`}
                        className="flex justify-start"
                      >
                        <div className={`max-w-[min(82%,52rem)] rounded-[26px] bg-[rgba(10,8,7,0.56)] px-6 py-4 font-sans text-[clamp(1rem,1.14vw,1.18rem)] font-medium leading-[1.42] text-[rgba(255,248,238,0.94)] shadow-[0_10px_24px_rgba(0,0,0,0.24)] backdrop-blur-sm ${
                          isLatest ? '' : 'opacity-[0.68]'
                        }`}>
                          {renderMarkdown(text)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
            {(draftBusy || draftSet || draftError) ? (
              <div className="mb-4 px-5">
                <div className="max-w-[min(82%,52rem)] rounded-[22px] border border-[rgba(232,178,102,0.2)] bg-[rgba(17,12,10,0.82)] px-5 py-4 shadow-[0_14px_30px_rgba(0,0,0,0.3)]">
                  <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-[0.15em] text-[rgba(232,178,102,0.75)]">
                    <span className="flex items-center gap-2">
                      <Sparkles size={13} />
                      Conversation Lab
                    </span>
                    {draftSet ? (
                      <span>{draftIndex + 1} / {draftSet.candidates.length}</span>
                    ) : null}
                  </div>
                  {draftBusy && !draftSet ? (
                    <div className="text-sm text-[rgba(255,240,218,0.65)]">
                      {draftProgressLabel}
                    </div>
                  ) : null}
                  {draftSet ? (
                    <>
                      <div className="min-h-[3.5rem] text-[clamp(1rem,1.1vw,1.15rem)] font-medium leading-[1.42] text-[rgba(255,248,238,0.94)]">
                        {renderMarkdown(draftSet.candidates[draftIndex]?.text)}
                      </div>
                      <div className="mt-2 font-mono text-[10px] text-white/35">
                        {draftSet.diagnostics?.author_model || 'model nieznany'}
                        {' · '}
                        {draftSet.context?.status || 'kontekst nieznany'}
                        {draftSet.diagnostics?.candidate_attempts?.[draftIndex]?.latency_ms
                          ? ` · ${Math.round(
                            draftSet.diagnostics.candidate_attempts[draftIndex].latency_ms,
                          )} ms`
                          : ''}
                      </div>
                      <div className="mt-3 flex items-center justify-between">
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => setDraftIndex((current) => (
                              current <= 0 ? draftSet.candidates.length - 1 : current - 1
                            ))}
                            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.06] text-white/70 transition hover:bg-white/[0.1] hover:text-white"
                            title="Poprzedni wariant"
                          >
                            <ChevronLeft size={15} />
                          </button>
                          <button
                            type="button"
                            onClick={() => setDraftIndex((current) => (
                              (current + 1) % draftSet.candidates.length
                            ))}
                            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.06] text-white/70 transition hover:bg-white/[0.1] hover:text-white"
                            title="Następny wariant"
                          >
                            <ChevronRight size={15} />
                          </button>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={cancelDraft}
                            className="rounded-full px-3 py-1.5 text-xs text-white/55 transition hover:bg-white/[0.06] hover:text-white/80"
                          >
                            Anuluj
                          </button>
                          <button
                            type="button"
                            onClick={selectDraft}
                            disabled={draftBusy}
                            className="flex items-center gap-1.5 rounded-full bg-[rgba(232,178,102,0.92)] px-3.5 py-1.5 text-xs font-semibold text-[#20160f] transition hover:bg-[rgba(255,205,128,1)] disabled:opacity-50"
                          >
                            <Check size={13} />
                            Wybierz
                          </button>
                        </div>
                      </div>
                    </>
                  ) : null}
                  {draftError ? (
                    <div className="mt-2 text-xs text-[#df8978]">{draftError}</div>
                  ) : null}
                </div>
              </div>
            ) : null}
            <div ref={messagesEndRef} />
          </div>
          </div>
        )}

        {/* Unified Bottom Bar - All controls in one place */}
        <div className="shrink-0 text-sm px-6">
          <div className="flex flex-col gap-2">
              <div className="flex min-h-[64px] items-center gap-3 rounded-full border border-[rgba(232,178,102,0.16)] bg-[rgba(13,10,9,0.88)] px-4 py-2 shadow-[0_14px_34px_rgba(0,0,0,0.5),inset_0_1px_0_rgba(255,234,198,0.05)] backdrop-blur-xl">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept="image/*,.txt,.md,.json,.csv,.log,.pdf"
                  onChange={(event) => addFiles(event.target.files)}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  title={t('chat.attach_file_tab') || 'Attach file'}
                  className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[rgba(255,240,218,0.78)] transition hover:bg-[rgba(255,238,212,0.08)] hover:text-[rgba(255,248,235,0.95)]"
                >
                  <Plus size={24} />
                  {attachments.length > 0 && (
                    <span className="absolute right-0 top-0 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[rgba(232,178,102,0.95)] text-[9px] font-bold text-[#20160f]">
                      {attachments.length}
                    </span>
                  )}
                </button>
                <button
                  type="button"
                  onClick={toggleConversationLab}
                  title={conversationLab ? 'Wyłącz Conversation Lab' : 'Włącz Conversation Lab'}
                  aria-pressed={conversationLab}
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition ${
                    conversationLab
                      ? 'bg-[rgba(232,178,102,0.12)] text-[rgba(232,178,102,0.95)]'
                      : 'text-[rgba(255,240,218,0.58)] hover:bg-[rgba(255,238,212,0.08)] hover:text-[rgba(255,248,235,0.95)]'
                  }`}
                >
                  <Sparkles size={18} />
                </button>
                {hasAgenticActivity && (
                  <button
                    type="button"
                    onClick={() => setShowAgenticLog(!showAgenticLog)}
                    title="Agent logs"
                    aria-pressed={showAgenticLog}
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition ${
                      showAgenticLog
                        ? 'bg-[rgba(232,178,102,0.12)] text-[rgba(232,178,102,0.95)]'
                        : 'text-[rgba(255,240,218,0.58)] hover:bg-[rgba(255,238,212,0.08)] hover:text-[rgba(255,248,235,0.95)]'
                    }`}
                  >
                    <Terminal size={18} />
                  </button>
                )}
                <textarea
                  ref={textareaRef}
                  value={inputValue}
                  onChange={(event) => setInputValue(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={t('chat.placeholder')}
                  rows={1}
                  className="max-h-24 min-h-[32px] flex-1 resize-none border-0 bg-transparent px-0 py-1 text-[16px] font-medium leading-7 text-[rgba(255,246,233,0.92)] placeholder:text-[rgba(255,224,190,0.52)] outline-none"
                />
                <button
                  type="button"
                  onClick={toggleMute}
                  aria-label={isMuted ? t('tools.microphone_off') : t('tools.microphone_on')}
                  aria-pressed={!isMuted}
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition ${
                    isMuted
                      ? 'bg-[rgba(166,72,58,0.14)] text-[#df8978] hover:bg-[rgba(166,72,58,0.22)] hover:text-[#f0ad9d]'
                      : 'bg-[rgba(88,118,73,0.14)] text-[#9fbd8f] hover:bg-[rgba(88,118,73,0.22)] hover:text-[#c0d4ad]'
                  }`}
                  title={isMuted ? t('tools.microphone_off') : t('tools.microphone_on')}
                >
                  {isMuted ? <MicOff size={19} /> : <Mic size={19} />}
                </button>
                <button
                  type="button"
                  onClick={handleSendMessage}
                  disabled={!canSend}
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition ${
                    canSend
                      ? 'bg-[rgba(232,178,102,0.95)] text-[#20160f] shadow-[0_8px_18px_rgba(232,178,102,0.24)] hover:bg-[rgba(255,205,128,1)]'
                      : 'cursor-not-allowed bg-[rgba(255,224,190,0.08)] text-[rgba(255,224,190,0.24)]'
                  }`}
                  title="Send message"
                >
                  <Upload size={19} />
                </button>
              </div>

            {attachments.length ? (
              <div className="flex flex-wrap gap-1">
                {attachments.map((item) => {
                  const isImage = (item.file?.type || '').startsWith('image/');
                  return (
                    <div
                      key={item.id}
                      className="flex items-center gap-1 rounded-[10px] border border-[rgba(232,178,102,0.16)] bg-[rgba(255,238,212,0.08)] px-2 py-1 text-[12px]"
                      title={`${item.file?.name} (${Math.round((item.file?.size || 0) / 1024)} KB)`}
                    >
                      {isImage && item.previewUrl ? (
                        <img src={item.previewUrl} alt={item.file?.name} className="h-5 w-5 rounded border border-white/10 object-cover" />
                      ) : (
                        <div className="flex h-5 w-5 items-center justify-center rounded border border-white/20 bg-white/10 text-[11px] text-white/60">
                          F
                        </div>
                      )}
                      <span className="max-w-[150px] truncate text-[rgba(255,240,218,0.7)]">{item.file?.name}</span>
                      <button
                        type="button"
                        onClick={() => removeAttachment(item.id)}
                        className="text-white/50 transition hover:text-white/80"
                        title="Remove"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </div>
      </div>
      </div>
    </div>
  );
};

export default ChatPanel;
