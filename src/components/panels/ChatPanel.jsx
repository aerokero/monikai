import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  Brain,
  ClipboardList,
  Gamepad2,
  Gift,
  Heart,
  Maximize2,
  MessageSquare,
  Paperclip,
  Send,
  Settings,
  Terminal,
  Utensils,
  X,
  Zap,
} from 'lucide-react';
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

const ActivityTile = ({ icon: Icon, title, description, onClick, accentClass, active = false }) => (
  <button
    onClick={onClick}
    className={`group rounded-xl border p-3 text-left transition-all duration-200 hover:-translate-y-0.5 ${
      active
        ? 'border-[rgba(255,100,140,0.3)] bg-[rgba(255,100,140,0.08)]'
        : 'border-white/10 bg-white/4 hover:border-white/20 hover:bg-white/6'
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
}) => {
  const { t } = useLanguage();
  const rootRef = useRef(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  const [showThoughts, setShowThoughts] = useState(false);
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
    if (!socket) return undefined;
    const onSettings = (data) => {
      if (data && typeof data.show_internal_thoughts !== 'undefined') {
        setShowThoughts(data.show_internal_thoughts);
      }
    };
    socket.on('settings', onSettings);
    socket.emit('get_settings');
    return () => socket.off('settings', onSettings);
  }, [socket]);

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
    let list = Array.isArray(messages) ? messages : [];
    if (!showThoughts) {
      list = list.filter((message) => !String(message?.sender || '').includes('(Thought)'));
    }
    return list.slice(-40);
  }, [messages, showThoughts]);

  const visibleAgenticLogs = useMemo(() => {
    const source = Array.isArray(agenticLogs) ? agenticLogs : [];
    return source.slice(-120);
  }, [agenticLogs]);
  const latestVisibleMessage = visibleMessages.length ? visibleMessages[visibleMessages.length - 1] : null;

  const totalAttachBytes = useMemo(
    () => attachments.reduce((sum, item) => sum + (item?.file?.size || 0), 0),
    [attachments]
  );
  const canSend = Boolean((inputValue || '').trim()) || attachments.length > 0;
  const isEatTogetherActive = Boolean(eatTogetherActive || localEatTogetherActive);

  const toggleThoughts = () => {
    if (!socket) return;
    const next = !showThoughts;
    setShowThoughts(next);
    socket.emit('update_settings', { show_internal_thoughts: next });
  };

  const handleAction = (action) => {
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
          onToggleSession();
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

  const speakerLabel = (() => {
    const sender = String(latestVisibleMessage?.sender || '').trim();
    const lower = sender.toLowerCase();
    if (!sender || lower === 'ai' || lower === 'monika' || lower === 'assistant') return 'Monika';
    if (sender.includes('(Thought)')) return 'Monika';
    if (lower === 'you' || lower === 'ty') return t('chat.you') || 'You';
    return sender;
  })();

  return (
    <div ref={rootRef} className="flex h-full w-full min-h-0 flex-col overflow-visible gap-0 px-3 pt-0 pb-3 box-border">
      {/* Speaker Label - Outside the box (DDLC style) */}
      <div className="flex items-center justify-between px-3 shrink-0 mb-[-1px] z-20">
        <div className="rounded-t-[10px] rounded-b-none bg-white px-5 py-1.5 shadow-[0_-4px_16px_rgba(0,0,0,0.3)]">
          <span className="relative inline-block text-[22px] font-black leading-none tracking-tight">
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 text-transparent"
              style={{ WebkitTextStroke: '4px #b65798' }}
            >
              {speakerLabel}
            </span>
            <span className="relative text-white">{speakerLabel}</span>
          </span>
        </div>
        <button
          onClick={onToggleExpand}
          className="text-white/40 transition hover:text-white/70 mb-1"
          title={isExpanded ? 'Collapse' : 'Expand'}
        >
          <Maximize2 size={15} />
        </button>
      </div>

      {/* Main Box - Chat content */}
      <div
        className="relative flex-1 min-h-0 overflow-hidden rounded-[16px] rounded-tl-none border border-white/5 flex flex-col"
        style={{
          background: 'linear-gradient(135deg, rgba(0,0,0,0.55), rgba(32,8,48,0.35))',
          backdropFilter: 'blur(12px)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        }}
      >
        {/* Content Area - Main scrollable messages and views */}
        <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar relative flex flex-col p-4 z-10">
        {/* Chat View */}
        {viewMode === 'chat' && (
          <div className="space-y-3">
            {showAgenticLog && hasAgenticActivity ? (
              <div className="mb-4 overflow-hidden rounded-[14px] border border-white/10 bg-white/4 shadow-[0_4px_16px_rgba(0,0,0,0.4)]">
                <div className="flex items-center gap-2 border-b border-white/30 px-3 py-2 font-mono text-[12px] uppercase tracking-wider text-white/70">
                  <Terminal size={12} />
                  Agent Log
                </div>
                <div className="max-h-36 space-y-1 overflow-y-auto px-3 py-2 font-mono text-[13px] text-white/60 custom-scrollbar">
                  {visibleAgenticLogs.length === 0 ? (
                    <div className="text-white/50">Thinking...</div>
                  ) : (
                    visibleAgenticLogs.map((entry, index) => (
                      <div key={`agentic-${index}`} className="break-words">
                        <span className="mr-2 text-white/70">{'>'}</span>
                        {String(entry || '')}
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : null}

            {visibleMessages.length === 0 ? (
              <div className="py-12 text-center text-white/30">
                <p>No messages yet.</p>
                <p className="mt-2 text-sm text-white/20">Start a conversation with Monika!</p>
              </div>
            ) : (
              visibleMessages.map((message, index) => {
                const sender = String(message?.sender || '');
                const lower = sender.toLowerCase();
                const isUser = lower === 'ty' || lower === 'you';
                const isThought = sender.includes('(Thought)');
                const displaySender = isThought
                  ? 'Thought'
                  : (isUser ? (t('chat.you') || 'You') : 'Monika');

                return (
                  <div key={index} className={`relative flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
                    {isThought && !showThoughts ? null : (
                      <>
                        {/* Sender label — only for Monika, tiny and subtle */}
                        {!isUser && (
                          <div className="mb-0.5 flex items-baseline gap-1.5">
                            <span className="text-[10px] font-medium tracking-widest text-[rgba(255,100,140,0.5)]">
                              {displaySender}
                            </span>
                            {message?.time ? (
                              <span className="font-mono text-[9px] text-white/15">{message.time}</span>
                            ) : null}
                          </div>
                        )}
                        {isUser ? (
                          <p className="w-full text-[14px] leading-relaxed text-white/45 text-right">
                            {renderMarkdown(message?.text)}
                          </p>
                        ) : isThought ? (
                          <p className="text-[14px] leading-relaxed italic pl-3 border-l border-white/12 text-white/35">
                            {renderMarkdown(message?.text)}
                          </p>
                        ) : (
                          <p className="text-[15px] leading-relaxed text-white/90">
                            {renderMarkdown(message?.text)}
                          </p>
                        )}
                      </>
                    )}
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        {/* Activities View */}
        {viewMode === 'activities' && (
          <div className="rounded-[14px] border border-white/8 bg-white/3 p-3">
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
                accentClass="bg-pink-500/22 text-pink-200"
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
              <ActivityTile
                icon={ClipboardList}
                title={sessionActive ? t('companion.session.end') : t('companion.session.start')}
                description={sessionActive ? t('companion.session.end_desc') : t('companion.session.start_desc')}
                onClick={() => handleAction('session')}
                accentClass={sessionActive ? 'bg-amber-500/32 text-amber-100' : 'bg-amber-500/22 text-amber-200'}
                active={Boolean(sessionActive)}
              />
            </div>
          </div>
        )}

        {/* Attachments View */}
        {viewMode === 'attachments' && (
          <div>
            {attachments.length === 0 ? (
              <div className="flex items-center justify-center text-center text-white/70">
                <div>
                  <p className="text-sm">No attachments yet</p>
                  <p className="text-sm text-white/50 mt-1">Add files to share with Monika</p>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {attachments.map((item) => {
                  const isImage = (item.file?.type || '').startsWith('image/');
                  return (
                    <div
                      key={item.id}
                      className="flex items-center justify-between gap-3 rounded-[12px] border border-white/20 bg-white/15 p-3 hover:bg-white/20 transition"
                    >
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        {isImage && item.previewUrl ? (
                          <img src={item.previewUrl} alt={item.file?.name} className="h-12 w-12 rounded-lg border border-white/10 object-cover flex-shrink-0" />
                        ) : (
                          <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-white/20 bg-white/10 text-lg flex-shrink-0">
                            📄
                          </div>
                        )}
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-white/90 truncate">{item.file?.name}</div>
                          <div className="text-sm text-white/60">{Math.round((item.file?.size || 0) / 1024)} KB</div>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeAttachment(item.id)}
                        className="text-white/60 transition hover:text-red-400 flex-shrink-0 font-semibold text-sm"
                        title="Remove"
                      >
                        Remove
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Thoughts View */}
        {viewMode === 'thoughts' && (
          <div className="rounded-[16px] border border-white/20 bg-white/10 overflow-hidden">
            <div className="px-4 py-3 border-b border-white/20 bg-white/15">
              <h3 className="text-sm font-semibold text-white/90">{t('chat.internal_thoughts')}</h3>
              <p className="text-sm text-white/60 mt-1">
                {showThoughts ? t('chat.thoughts_visible') : t('chat.enable_thoughts')}
              </p>
            </div>
            <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
              {visibleMessages.filter(m => String(m?.sender || '').includes('(Thought)')).length === 0 ? (
                <p className="text-sm text-white/60">{t('chat.no_thoughts')}</p>
              ) : (
                visibleMessages
                  .filter(m => String(m?.sender || '').includes('(Thought)'))
                  .map((message, index) => (
                    <div key={index} className="rounded-[12px] border border-dashed border-white/20 bg-white/10 p-3 italic text-sm text-white/80">
                      {renderMarkdown(message?.text)}
                    </div>
                  ))
              )}
            </div>
          </div>
        )}

        </div>

        {/* Unified Bottom Bar - All controls in one place */}
        <div className="flex flex-col gap-2 border-t border-white/8 bg-transparent px-3 py-2 shrink-0 text-sm">
        {/* Input Row - Only shows in chat or activities */}
        {(viewMode === 'chat' || viewMode === 'activities') && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <textarea
                ref={textareaRef}
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type your message... (Shift+Enter for new line)"
                rows={1}
                className="flex-1 resize-none rounded-[12px] border border-white/12 bg-white/6 px-3 py-2 text-sm text-white/90 placeholder:text-white/30 outline-none focus:border-[rgba(255,100,140,0.45)] transition-colors"
              />
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
                onClick={handleSendMessage}
                disabled={!canSend}
                className={`font-semibold whitespace-nowrap transition-all ${
                  canSend
                    ? 'text-[rgba(255,100,140,0.85)] hover:text-[rgba(255,100,140,1)]'
                    : 'text-white/25 cursor-not-allowed'
                }`}
                title="Send message"
              >
                Send
              </button>
            </div>

            {attachments.length ? (
              <div className="flex flex-wrap gap-1">
                {attachments.map((item) => {
                  const isImage = (item.file?.type || '').startsWith('image/');
                  return (
                    <div
                      key={item.id}
                      className="flex items-center gap-1 rounded-[10px] border border-white/20 bg-white/15 px-2 py-1 text-[12px]"
                      title={`${item.file?.name} (${Math.round((item.file?.size || 0) / 1024)} KB)`}
                    >
                      {isImage && item.previewUrl ? (
                        <img src={item.previewUrl} alt={item.file?.name} className="h-5 w-5 rounded border border-white/10 object-cover" />
                      ) : (
                        <div className="flex h-5 w-5 items-center justify-center rounded border border-white/20 bg-white/10 text-[11px] text-white/60">
                          F
                        </div>
                      )}
                      <span className="max-w-[150px] truncate text-white/70">{item.file?.name}</span>
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
        <div className="flex items-center justify-center gap-1">
          {[
            { mode: 'chat', icon: MessageSquare, title: t('chat.chat_tab') || 'Chat' },
            { mode: 'activities', icon: Zap, title: t('chat.activities_tab') || 'Activities' },
            { mode: 'thoughts', icon: Brain, title: t('chat.thoughts_tab') || 'Thoughts' },
          ].map(({ mode, icon: Icon, title }) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              title={title}
              className={`flex items-center justify-center w-7 h-7 rounded-lg transition-all ${
                viewMode === mode
                  ? 'text-[rgba(255,100,140,0.9)] bg-[rgba(255,100,140,0.1)]'
                  : 'text-white/35 hover:text-white/65 hover:bg-white/5'
              }`}
            >
              <Icon size={14} />
            </button>
          ))}

          <div className="w-px h-4 bg-white/10 mx-1" />

          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            title={t('chat.attach_file_tab') || 'Attach file'}
            className="relative flex items-center justify-center w-7 h-7 rounded-lg text-white/35 hover:text-white/65 hover:bg-white/5 transition-all"
          >
            <Paperclip size={14} />
            {attachments.length > 0 && (
              <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[rgba(255,100,140,0.9)] text-[9px] font-bold text-white">
                {attachments.length}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={onOpenSettings}
            title={t('chat.settings_tab') || 'Settings'}
            className="flex items-center justify-center w-7 h-7 rounded-lg text-white/35 hover:text-white/65 hover:bg-white/5 transition-all"
          >
            <Settings size={14} />
          </button>

          {hasAgenticActivity && (
            <button
              onClick={() => setShowAgenticLog(!showAgenticLog)}
              title="Agent logs"
              className={`flex items-center justify-center w-7 h-7 rounded-lg transition-all ${
                showAgenticLog
                  ? 'text-[rgba(255,100,140,0.9)] bg-[rgba(255,100,140,0.1)]'
                  : 'text-white/35 hover:text-white/65 hover:bg-white/5'
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
