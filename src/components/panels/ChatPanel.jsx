import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  ClipboardList,
  Gamepad2,
  Gift,
  Heart,
  Maximize2,
  MessageSquare,
  Plus,
  Settings,
  Terminal,
  Upload,
  Utensils,
  X,
  Zap,
} from '../icons';
import AudioBar from '../AudioBar';
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
    .trim();
}

const ActivityTile = ({ icon: Icon, title, description, onClick, accentClass, active = false }) => (
  <button
    onClick={onClick}
    className={`group rounded-xl border p-3 text-left transition-all duration-200 hover:-translate-y-0.5 ${
      active
        ? 'border-[rgba(232,178,102,0.32)] bg-[rgba(232,178,102,0.08)]'
        : 'border-[rgba(232,178,102,0.12)] bg-[rgba(255,238,212,0.035)] hover:border-[rgba(232,178,102,0.22)] hover:bg-[rgba(255,238,212,0.06)]'
    }`}
  >
    <div className="flex items-start gap-3">
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${accentClass}`}>
        <Icon size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-white">{title}</div>
        <div className="mt-1 text-[13px] leading-relaxed text-white/80">{description}</div>
      </div>
    </div>
  </button>
);

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
  studyModeActive = false,
  onShareStudyPage = null,
  onMinimizedChange = null,
  onSizeChange = null,
  onOpenSettings = () => {},
  onHeadpat = null,
  eatTogetherActive = false,
  onStartEatTogether = null,
  onStopEatTogether = null,
  onToggleMinecraft = null,
  showMinecraftWindow = false,
  sessionActive = false,
  onToggleSession = null,
  onOpenStudy = null,
  compactDock = false,
}) => {
  const { t } = useLanguage();
  const rootRef = useRef(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  const [attachments, setAttachments] = useState([]);
  const [attachError, setAttachError] = useState('');
  const [viewMode, setViewMode] = useState('chat');
  const [localEatTogetherActive, setLocalEatTogetherActive] = useState(false);
  const [prevAgenticLogLength, setPrevAgenticLogLength] = useState(0);
  
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
  }, [onSizeChange, viewMode, attachments.length, showAgenticLog, isExpanded]);

  useEffect(() => () => {
    attachments.forEach((item) => {
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    });
  }, [attachments]);

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
  const canSend = Boolean((inputValue || '').trim()) || attachments.length > 0;
  const isEatTogetherActive = Boolean(eatTogetherActive || localEatTogetherActive);
  const dialogueMessages = visibleMessages.slice(-8);
  const isUserMessage = (sender) => ['you', 'ty'].includes(String(sender || '').trim().toLowerCase());

  const handleAction = (action, arg) => {
    let text = '';

    switch (action) {
      case 'eat':
        if (isEatTogetherActive) {
          if (typeof onStopEatTogether === 'function') onStopEatTogether();
          setLocalEatTogetherActive(false);
          text = "That was nice. Let's wrap up our little meal together.";
        } else {
          if (typeof onStartEatTogether === 'function') onStartEatTogether();
          setLocalEatTogetherActive(true);
          text = "Let's eat together for a bit. I want something cozy and low-key.";
        }
        break;
      case 'headpat':
        text = 'headpat for you';
        if (typeof onHeadpat === 'function') onHeadpat();
        break;
      case 'gift': {
        const gift = window.prompt(t('companion.activities.gift_prompt'));
        if (gift) text = `I brought you a little gift: ${gift}.`;
        break;
      }
      case 'minecraft':
        if (typeof onToggleMinecraft === 'function') {
          onToggleMinecraft();
          return;
        }
        text = "Let's play Minecraft together!";
        break;
      case 'study':
        if (typeof onOpenStudy === 'function') {
          onOpenStudy();
          return;
        }
        text = "Let's study Japanese together.";
        break;
      case 'session':
        if (typeof onToggleSession === 'function') {
          onToggleSession(arg);
          return;
        }
        break;
      default:
        return;
    }

    if (text && socket) {
      socket.emit('user_input', { text });
    }
  };

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

    handleSend({ key: 'Enter', attachments: payloadAttachments });
    clearAttachments();
    textareaRef.current?.focus();
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
        {/* Content Area - Main scrollable messages and views */}
        {!compactDock && (
          <div className="monika-chat-panel-content flex-1 min-h-0 overflow-y-auto custom-scrollbar relative flex flex-col px-1 pb-2 pt-0 z-10">
        {/* Chat View */}
        {viewMode === 'chat' && (
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
                <div className="max-h-[34vh] space-y-6 overflow-y-auto pr-2 custom-scrollbar">
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
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Activities View */}
        {viewMode === 'activities' && (
          <div className="mb-3 rounded-[18px] border border-[rgba(232,178,102,0.12)] bg-black/45 p-4 shadow-[0_14px_34px_rgba(0,0,0,0.48)] backdrop-blur-md">
            <div className="grid grid-cols-2 gap-3">
              <ActivityTile
                icon={Utensils}
                title={t('companion.activities.eat')}
                description={t('companion.activities.eat_desc')}
                onClick={() => handleAction('eat')}
                accentClass={isEatTogetherActive ? 'bg-orange-500/32 text-orange-100' : 'bg-orange-500/22 text-orange-200'}
                active={isEatTogetherActive}
              />
              <ActivityTile
                icon={Heart}
                title={t('companion.activities.headpat')}
                description={t('companion.activities.headpat_desc')}
                onClick={() => handleAction('headpat')}
                accentClass="bg-[rgba(226,151,153,0.18)] text-[rgba(255,210,210,0.9)]"
              />
              <ActivityTile
                icon={Gift}
                title={t('companion.activities.gift')}
                description={t('companion.activities.gift_desc')}
                onClick={() => handleAction('gift')}
                accentClass="bg-violet-500/22 text-violet-200"
              />
              <ActivityTile
                icon={Gamepad2}
                title={t('companion.activities.minecraft') || 'Minecraft'}
                description={t('companion.activities.minecraft_desc') || 'Open the Minecraft companion activity panel.'}
                onClick={() => handleAction('minecraft')}
                accentClass={showMinecraftWindow ? 'bg-emerald-500/32 text-emerald-100' : 'bg-emerald-500/22 text-emerald-200'}
                active={Boolean(showMinecraftWindow)}
              />
              <ActivityTile
                icon={BookOpen}
                title={t('companion.study.japanese_together') || 'Japanese Study Together'}
                description={t('companion.study.desc') || 'Open study materials and learn together.'}
                onClick={() => handleAction('study')}
                accentClass={studyModeActive ? 'bg-cyan-500/32 text-cyan-100' : 'bg-cyan-500/22 text-cyan-200'}
                active={Boolean(studyModeActive)}
              />
              {sessionActive ? (
                <ActivityTile
                  icon={ClipboardList}
                  title={t('companion.session.end')}
                  description={t('companion.session.end_desc')}
                  onClick={() => handleAction('session')}
                  accentClass="bg-amber-500/32 text-amber-100"
                  active={true}
                />
              ) : (
                <>
                  <ActivityTile
                    icon={Heart}
                    title={t('companion.session.talk') || 'I need to talk'}
                    description={t('companion.session.talk_desc') || 'A calm, warm conversation.'}
                    onClick={() => handleAction('session', 'reflective')}
                    accentClass="bg-amber-500/22 text-amber-200"
                    active={false}
                  />
                  <ActivityTile
                    icon={ClipboardList}
                    title={t('companion.session.work') || 'I want to work on something'}
                    description={t('companion.session.work_desc') || 'Deeper, therapeutic work.'}
                    onClick={() => handleAction('session', 'therapy')}
                    accentClass="bg-amber-500/22 text-amber-200"
                    active={false}
                  />
                </>
              )}
            </div>
          </div>
        )}

          </div>
        )}

        {/* Unified Bottom Bar - All controls in one place */}
        <div className="shrink-0 text-sm">
          {/* Input Row - Only shows in chat or activities */}
          {(compactDock || viewMode === 'chat' || viewMode === 'activities') && (
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
        )}

        {/* Menu Bar - Icon tabs */}
        <div className="mt-2 flex items-center justify-center gap-1">
          {[
            { mode: 'chat', icon: MessageSquare, title: t('chat.chat_tab') || 'Chat' },
            { mode: 'activities', icon: Zap, title: t('chat.activities_tab') || 'Activities' },
          ].map(({ mode, icon: Icon, title }) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              title={title}
              className={`flex items-center justify-center w-7 h-7 rounded-lg transition-all ${
                viewMode === mode
                  ? 'text-[rgba(232,178,102,0.95)] bg-[rgba(232,178,102,0.12)]'
                  : 'text-[rgba(255,224,190,0.36)] hover:text-[rgba(255,240,218,0.68)] hover:bg-[rgba(255,238,212,0.055)]'
              }`}
            >
              <Icon size={14} />
            </button>
          ))}

          <div className="w-px h-4 bg-white/10 mx-1" />

          <button
            type="button"
            onClick={onOpenSettings}
            title={t('chat.settings_tab') || 'Settings'}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-[rgba(255,224,190,0.36)] transition-all hover:bg-[rgba(255,238,212,0.055)] hover:text-[rgba(255,240,218,0.68)]"
          >
            <Settings size={14} />
          </button>

          {hasAgenticActivity && (
            <button
              onClick={() => setShowAgenticLog(!showAgenticLog)}
              title="Agent logs"
              className={`flex items-center justify-center w-7 h-7 rounded-lg transition-all ${
                showAgenticLog
                  ? 'text-[rgba(232,178,102,0.95)] bg-[rgba(232,178,102,0.12)]'
                  : 'text-[rgba(255,224,190,0.36)] hover:text-[rgba(255,240,218,0.68)] hover:bg-[rgba(255,238,212,0.055)]'
              }`}
            >
              <Terminal size={14} />
            </button>
          )}
        </div>
      </div>
      </div>
    </div>
  );
};

export default ChatPanel;
