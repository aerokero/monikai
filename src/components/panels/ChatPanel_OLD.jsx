import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  Brain,
  Gamepad2,
  Gift,
  Heart,
  Maximize2,
  Minimize2,
  Paperclip,
  Send,
  Terminal,
  Utensils,
  X,
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
    className={`group rounded-xl border p-3 text-left transition-all hover:-translate-y-0.5 ${
      active
        ? 'border-white/30 bg-white/15'
        : 'border-white/10 bg-black/20 hover:border-white/20 hover:bg-white/10'
    }`}
  >
    <div className="flex items-start gap-3">
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${accentClass}`}>
        <Icon size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold text-white">{title}</div>
        <div className="mt-1 text-[11px] leading-relaxed text-white/45">{description}</div>
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
  const [eatTogetherActive, setEatTogetherActive] = useState(false);
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

  const toggleThoughts = () => {
    if (!socket) return;
    const next = !showThoughts;
    setShowThoughts(next);
    socket.emit('update_settings', { show_internal_thoughts: next });
  };

  const toggleAgenticLog = () => {
    const next = !showAgenticLog;
    setShowAgenticLog(next);
    try {
      localStorage.setItem('show_agentic_log', next ? 'true' : 'false');
    } catch {
      // ignore storage errors
    }
  };

  const handleAction = (action) => {
    if (!socket) return;
    let text = '';

    switch (action) {
      case 'eat':
        if (eatTogetherActive) {
          setEatTogetherActive(false);
          text = "That was nice. Let's wrap up our little meal together.";
        } else {
          setEatTogetherActive(true);
          text = "Let's eat together for a bit. I want something cozy and low-key.";
        }
        break;
      case 'headpat':
        text = 'headpat';
        break;
      case 'gift': {
        const gift = window.prompt('What would you like to give me?');
        if (gift) text = `I brought you a little gift: ${gift}.`;
        break;
      }
      case 'minecraft':
        text = "Let's play Minecraft together!";
        break;
      default:
        return;
    }

    if (text) {
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
    if (!sender) return 'Monika';
    if (sender.includes('(Thought)')) return 'Monika';
    if (sender.toLowerCase() === 'you' || sender.toLowerCase() === 'ty') return t('chat.you') || 'You';
    return sender;
  })();

  return (
    <div
      ref={rootRef}
      className="flex h-full w-full min-h-0 flex-col overflow-hidden rounded-[26px] border-[3px] border-white/80 bg-[linear-gradient(180deg,rgba(255,245,249,0.96),rgba(255,221,239,0.94))] shadow-[0_22px_60px_rgba(183,82,131,0.34)]"
    >
      {/* Header with title only */}
      <div className="flex items-center justify-between border-b border-[#efb7d2] bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(255,236,245,0.94))] px-5 py-3 shrink-0">
        <div className="flex items-center gap-2">
          <div className="h-2.5 w-2.5 rounded-full bg-[#d067a7] shadow-[0_0_10px_rgba(208,103,167,0.5)]" />
          <span className="text-sm font-semibold tracking-[0.18em] text-[#7d3d66] uppercase">{t('chat.title') || 'Chat with Monika'}</span>
        </div>
        <button
          onClick={onToggleExpand}
          className="text-xs font-semibold text-[#9f6f8a] transition-all hover:text-[#7d3d66]"
          title={isExpanded ? 'Collapse chat' : 'Expand chat'}
        >
          {isExpanded ? 'Collapse' : 'Expand'}
        </button>
      </div>

      {/* Content area */}
      <div className="flex-1 min-h-0 overflow-y-auto bg-[linear-gradient(180deg,rgba(255,236,245,0.72),rgba(255,224,238,0.72))] p-4 custom-scrollbar">

      {/* Chat View */}
      {viewMode === 'chat' && (
        <div>
          {showAgenticLog && hasAgenticActivity ? (
            <div className="mb-4 overflow-hidden rounded-[20px] border border-[#efb7d2] bg-[rgba(255,255,255,0.74)] shadow-[0_8px_24px_rgba(207,121,167,0.12)]">
              <div className="flex items-center gap-2 border-b border-[#f2c4db] px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-[#8f4576]">
                <Terminal size={12} />
                Agentic Log
              </div>
              <div className="max-h-36 space-y-1 overflow-y-auto px-3 py-2 font-mono text-[11px] text-[#6f5163] custom-scrollbar">
                {visibleAgenticLogs.length === 0 ? (
                  <div className="text-[#a07a90]">No agent activity yet.</div>
                ) : (
                  visibleAgenticLogs.map((entry, index) => (
                    <div key={`agentic-${index}`} className="break-words">
                      <span className="mr-2 text-[#c78cac]">{'>'}</span>
                      {String(entry || '')}
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : null}

          <div className="relative space-y-3 rounded-[26px] border-[3px] border-white/80 bg-[linear-gradient(180deg,rgba(255,206,229,0.88),rgba(255,183,214,0.84))] px-4 pb-4 pt-8 shadow-[inset_0_0_0_1px_rgba(240,145,189,0.45),0_16px_30px_rgba(177,88,126,0.18)]">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18px_18px,rgba(232,122,176,0.18)_0,rgba(232,122,176,0.18)_6px,transparent_7px)] bg-[length:34px_34px] opacity-70" />
            <div className="relative -mb-1 inline-flex min-h-[48px] items-center rounded-t-[18px] rounded-br-[18px] border-[3px] border-white/90 bg-[linear-gradient(180deg,#fffefe,#ffeef7)] px-5 py-2 shadow-[0_12px_22px_rgba(194,104,148,0.2)]">
              <span className="text-[28px] font-black leading-none tracking-tight text-[#ba5b97]" style={{ textShadow: '0 2px 0 rgba(255,255,255,0.85)' }}>
                {speakerLabel}
              </span>
            </div>
            {visibleMessages.length === 0 ? (
              <div className="relative py-12 text-center text-sm text-[#7f556e]">
                <p>No messages yet.</p>
                <p className="mt-2 text-xs text-[#9c7590]">Start a conversation with Monika!</p>
              </div>
            ) : (
              visibleMessages.map((message, index) => {
                const sender = String(message?.sender || '');
                const lower = sender.toLowerCase();
                const isUser = lower === 'ty' || lower === 'you';
                const isThought = sender.includes('(Thought)');

                return (
                  <div key={index} className={`relative flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
                    <div className="mb-1 flex items-center gap-2">
                      <span className={`text-[10px] font-bold uppercase tracking-wider ${
                        isUser ? 'text-[#7d3d66]' : isThought ? 'text-[#9d8090]' : 'text-[#a74f83]'
                      }`}>
                        {isThought ? (t('chat.monika_thought') || 'Monika (thought)') : (sender || '…')}
                      </span>
                      {message?.time ? <span className="font-mono text-[10px] text-[#b387a2]">{message.time}</span> : null}
                    </div>
                    <div className={`max-w-[92%] whitespace-pre-wrap break-words rounded-[18px] border-[2px] px-4 py-3 text-sm leading-relaxed shadow-[0_10px_24px_rgba(191,101,144,0.08)] ${
                      isUser
                        ? 'rounded-tr-[6px] border-[#f2b8d5] bg-[rgba(255,250,253,0.82)] text-[#6f455d]'
                        : isThought
                          ? 'rounded-tl-[6px] border-dashed border-[#efc4d9] bg-[rgba(255,247,251,0.58)] italic text-[#8a6d7c]'
                          : 'rounded-tl-[6px] border-[#f2bdd8] bg-[rgba(255,251,253,0.86)] text-[#5f4353]'
                    }`}>
                      {renderMarkdown(message?.text)}
                    </div>
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>
      )}

      {/* Activities View */}
      {viewMode === 'activities' && (
        <div className="grid grid-cols-2 gap-3">
          <ActivityTile
            icon={Utensils}
            title="Eat Together"
            description={eatTogetherActive ? 'Stop eating' : 'Have a meal'}
            onClick={() => handleAction('eat')}
            accentClass={eatTogetherActive ? 'bg-orange-500/28 text-orange-200' : 'bg-orange-500/18 text-orange-300'}
            active={eatTogetherActive}
          />
          <ActivityTile
            icon={Heart}
            title="Affection"
            description="Show you care"
            onClick={() => handleAction('headpat')}
            accentClass="bg-pink-500/18 text-pink-300"
          />
          <ActivityTile
            icon={Gift}
            title="Gift"
            description="Give her something"
            onClick={() => handleAction('gift')}
            accentClass="bg-violet-500/18 text-violet-300"
          />
          <ActivityTile
            icon={Gamepad2}
            title="Minecraft"
            description="Play together"
            onClick={() => handleAction('minecraft')}
            accentClass="bg-emerald-500/18 text-emerald-300"
          />
        </div>
      )}

      {/* Attachments View */}
      {viewMode === 'attachments' && (
        <div>
          {attachments.length === 0 ? (
            <div className="flex items-center justify-center text-center">
              <div>
                <p className="text-sm text-[#7f556e]">No attachments yet</p>
                <p className="text-xs text-[#9c7590] mt-1">Add files to share with Monika</p>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {attachments.map((item) => {
                const isImage = (item.file?.type || '').startsWith('image/');
                return (
                  <div
                    key={item.id}
                    className="flex items-center justify-between gap-3 rounded-[12px] border border-[#efc1d8] bg-[rgba(255,251,253,0.82)] p-3 hover:bg-[rgba(255,248,251,0.92)] transition"
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      {isImage && item.previewUrl ? (
                        <img src={item.previewUrl} alt={item.file?.name} className="h-12 w-12 rounded-lg border border-white/10 object-cover flex-shrink-0" />
                      ) : (
                        <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-[#efc1d8] bg-[#fff5fa] text-lg flex-shrink-0">
                          📄
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-[#6a4659] truncate">{item.file?.name}</div>
                        <div className="text-xs text-[#9d7b8f]">{Math.round((item.file?.size || 0) / 1024)} KB</div>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeAttachment(item.id)}
                      className="text-[#b78aa3] transition hover:text-red-600 flex-shrink-0 font-semibold text-sm"
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
        <div className="rounded-[16px] border border-[#efb7d2] bg-[rgba(255,255,255,0.74)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[#efb7d2] bg-[#fff7fb]">
            <h3 className="text-sm font-semibold text-[#7d3d66]">Internal Thoughts</h3>
            <p className="text-xs text-[#9d7b8f] mt-1">
              {showThoughts ? 'Monika\'s internal thoughts are visible' : 'Enable to see Monika\'s inner monologue'}
            </p>
          </div>
          <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
            {visibleMessages.filter(m => String(m?.sender || '').includes('(Thought)')).length === 0 ? (
              <p className="text-sm text-[#9c7590]">No thoughts recorded yet.</p>
            ) : (
              visibleMessages
                .filter(m => String(m?.sender || '').includes('(Thought)'))
                .map((message, index) => (
                  <div key={index} className="rounded-[12px] border border-dashed border-[#efc4d9] bg-[rgba(255,247,251,0.58)] p-3 italic text-sm text-[#8a6d7c]">
                    {renderMarkdown(message?.text)}
                  </div>
                ))
            )}
          </div>
        </div>
      )}

      {/* Settings View */}
      {viewMode === 'settings' && (
        <div className="space-y-3">
          {/* Show Thoughts Setting */}
          <div className="rounded-[12px] border border-[#efb7d2] bg-[rgba(255,255,255,0.82)] p-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-semibold text-[#7d3d66] text-sm">Show Internal Thoughts</h4>
                <p className="text-xs text-[#9d7b8f] mt-1">Display Monika's inner monologue in chat</p>
              </div>
              <button
                onClick={toggleThoughts}
                className={`text-xs font-semibold transition-all ${showThoughts ? 'text-[#8b3d6f]' : 'text-[#9f6f8a] hover:text-[#7d3d66]'}`}
              >
                {showThoughts ? 'On' : 'Off'}
              </button>
            </div>
          </div>

          {/* Show Agentic Log Setting */}
          <div className="rounded-[12px] border border-[#efb7d2] bg-[rgba(255,255,255,0.82)] p-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-semibold text-[#7d3d66] text-sm">Auto-show Agentic Log</h4>
                <p className="text-xs text-[#9d7b8f] mt-1">Show activity logs when Monika is thinking</p>
              </div>
              <button
                onClick={() => {
                  const next = !showAgenticLog;
                  setShowAgenticLog(next);
                  try {
                    localStorage.setItem('show_agentic_log', next ? 'true' : 'false');
                  } catch {}
                }}
                className={`text-xs font-semibold transition-all ${showAgenticLog ? 'text-[#8b3d6f]' : 'text-[#9f6f8a] hover:text-[#7d3d66]'}`}
              >
                {showAgenticLog ? 'On' : 'Off'}
              </button>
            </div>
          </div>

          {/* About */}
          <div className="rounded-[12px] border border-[#efb7d2] bg-[rgba(255,255,255,0.82)] p-4">
            <h4 className="font-semibold text-[#7d3d66] text-sm">About</h4>
            <p className="text-xs text-[#9d7b8f] mt-2">MonikAI - A Monika-first adaptive UI</p>
          </div>
        </div>
      )}
      </div>

      {/* Input Area (only on chat view) */}
      {viewMode === 'chat' && (
        <div className="relative shrink-0 border-t border-[#efb7d2] bg-[linear-gradient(180deg,rgba(255,245,249,0.96),rgba(255,229,239,0.96))] p-3">
          {userSpeaking ? (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-20">
              <AudioBar audioData={micAudioData || new Array(32).fill(0)} />
            </div>
          ) : null}

          <div className="relative z-10 flex flex-col gap-3">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your message... (Shift+Enter for new line)"
              rows={2}
              className="w-full resize-none rounded-[18px] border-[2px] border-white bg-[rgba(255,252,254,0.84)] px-4 py-3 text-sm text-[#6a4659] placeholder:text-[#b18aa0] outline-none focus:border-[#d67cab] custom-scrollbar shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]"
            />

            {attachments.length ? (
              <div className="flex flex-wrap gap-2">
                {attachments.map((item) => {
                  const isImage = (item.file?.type || '').startsWith('image/');
                  return (
                    <div
                      key={item.id}
                      className="flex items-center gap-2 rounded-[16px] border border-[#efc1d8] bg-[rgba(255,251,253,0.82)] px-2.5 py-1.5"
                      title={`${item.file?.name} (${Math.round((item.file?.size || 0) / 1024)} KB)`}
                    >
                      {isImage && item.previewUrl ? (
                        <img src={item.previewUrl} alt={item.file?.name} className="h-7 w-7 rounded-lg border border-white/10 object-cover" />
                      ) : (
                        <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#efc1d8] bg-[#fff5fa] text-[10px] text-[#a1778f]">
                          FILE
                        </div>
                      )}
                      <div className="max-w-[220px] truncate text-[12px] text-[#7b5a6d]">{item.file?.name}</div>
                      <button
                        type="button"
                        onClick={() => removeAttachment(item.id)}
                        className="text-[#b78aa3] transition hover:text-[#8d5475]"
                        title="Remove"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : null}

            {attachError ? <div className="text-[11px] text-[#c0576f]">{attachError}</div> : null}

            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] text-[#9d7b8f]">
                Shift+Enter for a new line
                {attachments.length ? (
                  <span className="ml-2 text-[#b08a9e]">
                    · {t('chat.attachments') || 'Attachments'}: {attachments.length}/{MAX_FILES} · {Math.round(totalAttachBytes / 1024)} KB
                  </span>
                ) : null}
              </div>

              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept="image/*,.txt,.md,.json,.csv,.log,.pdf"
                  onChange={(event) => addFiles(event.target.files)}
                  className="hidden"
                />

                {studyModeActive ? (
                  <button
                    type="button"
                    onClick={() => onShareStudyPage && onShareStudyPage()}
                    disabled={!onShareStudyPage}
                    className={`flex items-center gap-2 rounded-full border px-3 py-2 text-[11px] transition-all ${
                      onShareStudyPage
                        ? 'border-[#d67cab] bg-white text-[#8d5475] hover:bg-[#fff6fa]'
                        : 'cursor-not-allowed border-[#efc1d8] bg-[#fff7fb] text-[#c0a0b1]'
                    }`}
                    title="Send me the current study page"
                  >
                    <BookOpen size={14} />
                    <span className="whitespace-nowrap">Send me the current page</span>
                  </button>
                ) : null}

                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="text-xs font-semibold text-[#9f6f8a] transition-all hover:text-[#7d3d66]"
                  title="Attach file"
                >
                  Attach
                </button>

                <button
                  type="button"
                  onClick={handleSendMessage}
                  disabled={!canSend}
                  className={`text-xs font-semibold transition-all ${
                    canSend
                      ? 'text-[#8b3d6f] hover:text-[#6f2d57]'
                      : 'text-[#c4a4b5] cursor-not-allowed'
                  }`}
                  title="Send message"
                >
                  Send
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Bottom Tab Bar (like DDLC menu) */}
      <div className="flex gap-0 border-t border-[#efb7d2] bg-[linear-gradient(180deg,rgba(255,244,249,0.88),rgba(255,230,241,0.82))] px-2 py-2 overflow-x-auto shrink-0">
        {/* Chat Tab */}
        <button
          onClick={() => setViewMode('chat')}
          className={`px-4 py-1.5 text-xs font-semibold transition-all whitespace-nowrap ${
            viewMode === 'chat'
              ? 'text-[#8b3d6f]'
              : 'text-[#9f6f8a] hover:text-[#7d3d66]'
          }`}
          title="Chat with Monika"
        >
          Chat
        </button>

        {/* Activities Tab */}
        <button
          onClick={() => setViewMode('activities')}
          className={`px-4 py-1.5 text-xs font-semibold transition-all whitespace-nowrap ${
            viewMode === 'activities'
              ? 'text-[#8b3d6f]'
              : 'text-[#9f6f8a] hover:text-[#7d3d66]'
          }`}
          title="Activities and actions"
        >
          Activities
        </button>

        {/* Attachments Tab */}
        <button
          onClick={() => setViewMode('attachments')}
          className={`px-4 py-1.5 text-xs font-semibold transition-all whitespace-nowrap relative ${
            viewMode === 'attachments'
              ? 'text-[#8b3d6f]'
              : 'text-[#9f6f8a] hover:text-[#7d3d66]'
          }`}
          title="Manage attachments"
        >
          Attachments
          {attachments.length > 0 && (
            <span className="ml-1.5 inline-flex items-center justify-center h-4 w-4 rounded-full bg-red-500 text-[10px] text-white font-bold">
              {attachments.length}
            </span>
          )}
        </button>

        {/* Thoughts Tab */}
        <button
          onClick={() => {
            setViewMode('thoughts');
            toggleThoughts();
          }}
          className={`px-4 py-1.5 text-xs font-semibold transition-all whitespace-nowrap ${
            viewMode === 'thoughts'
              ? 'text-[#8b3d6f]'
              : 'text-[#9f6f8a] hover:text-[#7d3d66]'
          }`}
          title={showThoughts ? 'Hide internal thoughts' : 'Show internal thoughts'}
        >
          Thoughts {showThoughts && '✓'}
        </button>

        {/* Settings Tab */}
        <button
          onClick={() => setViewMode('settings')}
          className={`px-4 py-1.5 text-xs font-semibold transition-all whitespace-nowrap ${
            viewMode === 'settings'
              ? 'text-[#8b3d6f]'
              : 'text-[#9f6f8a] hover:text-[#7d3d66]'
          }`}
          title="Settings"
        >
          Settings
        </button>

        {/* Agentic Log Indicator */}
        {hasAgenticActivity && (
          <button
            onClick={() => setShowAgenticLog(!showAgenticLog)}
            className={`px-4 py-1.5 text-xs font-semibold transition-all whitespace-nowrap ml-auto ${
              showAgenticLog
                ? 'text-[#8b3d6f]'
                : 'text-[#9f6f8a] hover:text-[#7d3d66]'
            }`}
            title={showAgenticLog ? 'Hide agentic log' : 'Show agentic log'}
          >
            Logs {showAgenticLog && '✓'}
          </button>
        )}
      </div>
    </div>
  );
};
                {showAgenticLog ? (
                  <div className="mb-4 overflow-hidden rounded-[20px] border border-[#efb7d2] bg-[rgba(255,255,255,0.74)] shadow-[0_8px_24px_rgba(207,121,167,0.12)]">
                    <div className="flex items-center gap-2 border-b border-[#f2c4db] px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-[#8f4576]">
                      <Terminal size={12} />
                      Agentic Log
                    </div>
                    <div className="max-h-36 space-y-1 overflow-y-auto px-3 py-2 font-mono text-[11px] text-[#6f5163] custom-scrollbar">
                      {visibleAgenticLogs.length === 0 ? (
                        <div className="text-[#a07a90]">No agent activity yet.</div>
                      ) : (
                        visibleAgenticLogs.map((entry, index) => (
                          <div key={`agentic-${index}`} className="break-words">
                            <span className="mr-2 text-[#c78cac]">{'>'}</span>
                            {String(entry || '')}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                ) : null}

                <div className="relative space-y-3 rounded-[26px] border-[3px] border-white/80 bg-[linear-gradient(180deg,rgba(255,206,229,0.88),rgba(255,183,214,0.84))] px-4 pb-4 pt-8 shadow-[inset_0_0_0_1px_rgba(240,145,189,0.45),0_16px_30px_rgba(177,88,126,0.18)]">
                  <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18px_18px,rgba(232,122,176,0.18)_0,rgba(232,122,176,0.18)_6px,transparent_7px)] bg-[length:34px_34px] opacity-70" />
                  <div className="relative -mb-1 inline-flex min-h-[48px] items-center rounded-t-[18px] rounded-br-[18px] border-[3px] border-white/90 bg-[linear-gradient(180deg,#fffefe,#ffeef7)] px-5 py-2 shadow-[0_12px_22px_rgba(194,104,148,0.2)]">
                    <span className="text-[28px] font-black leading-none tracking-tight text-[#ba5b97]" style={{ textShadow: '0 2px 0 rgba(255,255,255,0.85)' }}>
                      {speakerLabel}
                    </span>
                  </div>
                  {visibleMessages.length === 0 ? (
                    <div className="relative py-12 text-center text-sm text-[#7f556e]">
                      <p>No messages yet.</p>
                      <p className="mt-2 text-xs text-[#9c7590]">Start a conversation with Monika!</p>
                    </div>
                  ) : (
                    visibleMessages.map((message, index) => {
                      const sender = String(message?.sender || '');
                      const lower = sender.toLowerCase();
                      const isUser = lower === 'ty' || lower === 'you';
                      const isThought = sender.includes('(Thought)');

                      return (
                        <div key={index} className={`relative flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
                          <div className="mb-1 flex items-center gap-2">
                            <span className={`text-[10px] font-bold uppercase tracking-wider ${
                              isUser ? 'text-[#7d3d66]' : isThought ? 'text-[#9d8090]' : 'text-[#a74f83]'
                            }`}>
                              {isThought ? (t('chat.monika_thought') || 'Monika (thought)') : (sender || '…')}
                            </span>
                            {message?.time ? <span className="font-mono text-[10px] text-[#b387a2]">{message.time}</span> : null}
                          </div>
                          <div className={`max-w-[92%] whitespace-pre-wrap break-words rounded-[18px] border-[2px] px-4 py-3 text-sm leading-relaxed shadow-[0_10px_24px_rgba(191,101,144,0.08)] ${
                            isUser
                              ? 'rounded-tr-[6px] border-[#f2b8d5] bg-[rgba(255,250,253,0.82)] text-[#6f455d]'
                              : isThought
                                ? 'rounded-tl-[6px] border-dashed border-[#efc4d9] bg-[rgba(255,247,251,0.58)] italic text-[#8a6d7c]'
                                : 'rounded-tl-[6px] border-[#f2bdd8] bg-[rgba(255,251,253,0.86)] text-[#5f4353]'
                          }`}>
                            {renderMarkdown(message?.text)}
                          </div>
                        </div>
                      );
                    })
                  )}
                  <div ref={messagesEndRef} />
                </div>
              </div>

              <div className="relative shrink-0 border-t border-[#efb7d2] bg-[linear-gradient(180deg,rgba(255,245,249,0.96),rgba(255,229,239,0.96))] p-3">
                {userSpeaking ? (
                  <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-20">
                    <AudioBar audioData={micAudioData || new Array(32).fill(0)} />
                  </div>
                ) : null}

                <div className="relative z-10 flex flex-col gap-3">
                  <textarea
                    ref={textareaRef}
                    value={inputValue}
                    onChange={(event) => setInputValue(event.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Type your message... (Shift+Enter for new line)"
                    rows={2}
                    className="w-full resize-none rounded-[18px] border-[2px] border-white bg-[rgba(255,252,254,0.84)] px-4 py-3 text-sm text-[#6a4659] placeholder:text-[#b18aa0] outline-none focus:border-[#d67cab] custom-scrollbar shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]"
                  />

                  {attachments.length ? (
                    <div className="flex flex-wrap gap-2">
                      {attachments.map((item) => {
                        const isImage = (item.file?.type || '').startsWith('image/');
                        return (
                          <div
                            key={item.id}
                            className="flex items-center gap-2 rounded-[16px] border border-[#efc1d8] bg-[rgba(255,251,253,0.82)] px-2.5 py-1.5"
                            title={`${item.file?.name} (${Math.round((item.file?.size || 0) / 1024)} KB)`}
                          >
                            {isImage && item.previewUrl ? (
                              <img src={item.previewUrl} alt={item.file?.name} className="h-7 w-7 rounded-lg border border-white/10 object-cover" />
                            ) : (
                              <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#efc1d8] bg-[#fff5fa] text-[10px] text-[#a1778f]">
                                FILE
                              </div>
                            )}
                            <div className="max-w-[220px] truncate text-[12px] text-[#7b5a6d]">{item.file?.name}</div>
                            <button
                              type="button"
                              onClick={() => removeAttachment(item.id)}
                              className="text-[#b78aa3] transition hover:text-[#8d5475]"
                              title="Remove"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}

                  {attachError ? <div className="text-[11px] text-[#c0576f]">{attachError}</div> : null}

                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[11px] text-[#9d7b8f]">
                      Shift+Enter for a new line
                      {attachments.length ? (
                        <span className="ml-2 text-[#b08a9e]">
                          · {t('chat.attachments') || 'Attachments'}: {attachments.length}/{MAX_FILES} · {Math.round(totalAttachBytes / 1024)} KB
                        </span>
                      ) : null}
                    </div>

                    <div className="flex items-center gap-2">
                      <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        accept="image/*,.txt,.md,.json,.csv,.log,.pdf"
                        onChange={(event) => addFiles(event.target.files)}
                        className="hidden"
                      />

                      {studyModeActive ? (
                        <button
                          type="button"
                          onClick={() => onShareStudyPage && onShareStudyPage()}
                          disabled={!onShareStudyPage}
                          className={`flex items-center gap-2 rounded-full border px-3 py-2 text-[11px] transition-all ${
                            onShareStudyPage
                              ? 'border-[#d67cab] bg-white text-[#8d5475] hover:bg-[#fff6fa]'
                              : 'cursor-not-allowed border-[#efc1d8] bg-[#fff7fb] text-[#c0a0b1]'
                          }`}
                          title="Send me the current study page"
                        >
                          <BookOpen size={14} />
                          <span className="whitespace-nowrap">Send me the current page</span>
                        </button>
                      ) : null}

                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="text-xs font-semibold text-[#9f6f8a] transition-all hover:text-[#7d3d66]"
                        title="Attach file"
                      >
                        Attach
                      </button>

                      <button
                        type="button"
                        onClick={handleSendMessage}
                        disabled={!canSend}
                        className={`text-xs font-semibold transition-all ${
                          canSend
                            ? 'text-[#8b3d6f] hover:text-[#6f2d57]'
                            : 'text-[#c4a4b5] cursor-not-allowed'
                        }`}
                        title="Send message"
                      >
                        Send
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : null}

          {/* Activities View */}
          {viewMode === 'activities' ? (
            <div className="flex-1 overflow-y-auto bg-[linear-gradient(180deg,rgba(255,236,245,0.72),rgba(255,224,238,0.72))] p-4 custom-scrollbar">
              <div className="grid grid-cols-2 gap-3">
                <ActivityTile
                  icon={Utensils}
                  title="Eat Together"
                  description={eatTogetherActive ? 'Stop eating' : 'Have a meal'}
                  onClick={() => handleAction('eat')}
                  accentClass={eatTogetherActive ? 'bg-orange-500/28 text-orange-200' : 'bg-orange-500/18 text-orange-300'}
                  active={eatTogetherActive}
                />
                <ActivityTile
                  icon={Heart}
                  title="Affection"
                  description="Show you care"
                  onClick={() => handleAction('headpat')}
                  accentClass="bg-pink-500/18 text-pink-300"
                />
                <ActivityTile
                  icon={Gift}
                  title="Gift"
                  description="Give her something"
                  onClick={() => handleAction('gift')}
                  accentClass="bg-violet-500/18 text-violet-300"
                />
                <ActivityTile
                  icon={Gamepad2}
                  title="Minecraft"
                  description="Play together"
                  onClick={() => handleAction('minecraft')}
                  accentClass="bg-emerald-500/18 text-emerald-300"
                />
              </div>
            </div>
          ) : null}

          {/* Attachments View */}
          {viewMode === 'attachments' ? (
            <div className="flex-1 overflow-y-auto bg-[linear-gradient(180deg,rgba(255,236,245,0.72),rgba(255,224,238,0.72))] p-4 custom-scrollbar">
              {attachments.length === 0 ? (
                <div className="flex h-full items-center justify-center text-center">
                  <div>
                    <div className="text-4xl mb-2">📎</div>
                    <p className="text-sm text-[#7f556e]">No attachments yet</p>
                    <p className="text-xs text-[#9c7590] mt-1">Add files to share with Monika</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  {attachments.map((item) => {
                    const isImage = (item.file?.type || '').startsWith('image/');
                    return (
                      <div
                        key={item.id}
                        className="flex items-center justify-between gap-3 rounded-[12px] border border-[#efc1d8] bg-[rgba(255,251,253,0.82)] p-3 hover:bg-[rgba(255,248,251,0.92)] transition"
                      >
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                          {isImage && item.previewUrl ? (
                            <img src={item.previewUrl} alt={item.file?.name} className="h-12 w-12 rounded-lg border border-white/10 object-cover flex-shrink-0" />
                          ) : (
                            <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-[#efc1d8] bg-[#fff5fa] text-lg flex-shrink-0">
                              📄
                            </div>
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium text-[#6a4659] truncate">{item.file?.name}</div>
                            <div className="text-xs text-[#9d7b8f]">{Math.round((item.file?.size || 0) / 1024)} KB</div>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => removeAttachment(item.id)}
                          className="text-[#b78aa3] transition hover:text-red-600 flex-shrink-0 font-semibold text-sm"
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
          ) : null}

          {/* Thoughts View */}
          {viewMode === 'thoughts' ? (
            <div className="flex-1 overflow-y-auto bg-[linear-gradient(180deg,rgba(255,236,245,0.72),rgba(255,224,238,0.72))] p-4 custom-scrollbar">
              <div className="rounded-[16px] border border-[#efb7d2] bg-[rgba(255,255,255,0.74)] overflow-hidden">
                <div className="px-4 py-3 border-b border-[#efb7d2] bg-[#fff7fb]">
                  <h3 className="text-sm font-semibold text-[#7d3d66]">Internal Thoughts</h3>
                  <p className="text-xs text-[#9d7b8f] mt-1">
                    {showThoughts ? 'Monika\'s internal thoughts are visible' : 'Enable to see Monika\'s inner monologue'}
                  </p>
                </div>
                <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
                  {visibleMessages.filter(m => String(m?.sender || '').includes('(Thought)')).length === 0 ? (
                    <p className="text-sm text-[#9c7590]">No thoughts recorded yet.</p>
                  ) : (
                    visibleMessages
                      .filter(m => String(m?.sender || '').includes('(Thought)'))
                      .map((message, index) => (
                        <div key={index} className="rounded-[12px] border border-dashed border-[#efc4d9] bg-[rgba(255,247,251,0.58)] p-3 italic text-sm text-[#8a6d7c]">
                          {renderMarkdown(message?.text)}
                        </div>
                      ))
                  )}
                </div>
              </div>
            </div>
          ) : null}

          {/* Settings View */}
          {viewMode === 'settings' ? (
            <div className="flex-1 overflow-y-auto bg-[linear-gradient(180deg,rgba(255,236,245,0.72),rgba(255,224,238,0.72))] p-4 custom-scrollbar">
              <div className="space-y-3">
                {/* Show Thoughts Setting */}
                <div className="rounded-[12px] border border-[#efb7d2] bg-[rgba(255,255,255,0.82)] p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-semibold text-[#7d3d66] text-sm">Show Internal Thoughts</h4>
                      <p className="text-xs text-[#9d7b8f] mt-1">Display Monika's inner monologue in chat</p>
                    </div>
                    <button
                      onClick={toggleThoughts}
                      className={`text-xs font-semibold transition-all ${showThoughts ? 'text-[#8b3d6f]' : 'text-[#9f6f8a] hover:text-[#7d3d66]'}`}
                    >
                      {showThoughts ? 'On' : 'Off'}
                    </button>
                  </div>
                </div>

                {/* Show Agentic Log Setting */}
                <div className="rounded-[12px] border border-[#efb7d2] bg-[rgba(255,255,255,0.82)] p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-semibold text-[#7d3d66] text-sm">Auto-show Agentic Log</h4>
                      <p className="text-xs text-[#9d7b8f] mt-1">Show activity logs when Monika is thinking</p>
                    </div>
                    <button
                      onClick={() => {
                        const next = !showAgenticLog;
                        setShowAgenticLog(next);
                        try {
                          localStorage.setItem('show_agentic_log', next ? 'true' : 'false');
                        } catch {}
                      }}
                      className={`text-xs font-semibold transition-all ${showAgenticLog ? 'text-[#8b3d6f]' : 'text-[#9f6f8a] hover:text-[#7d3d66]'}`}
                    >
                      {showAgenticLog ? 'On' : 'Off'}
                    </button>
                  </div>
                </div>

                {/* About */}
                <div className="rounded-[12px] border border-[#efb7d2] bg-[rgba(255,255,255,0.82)] p-4">
                  <h4 className="font-semibold text-[#7d3d66] text-sm">About</h4>
                  <p className="text-xs text-[#9d7b8f] mt-2">MonikAI - A Monika-first adaptive UI</p>
                </div>
              </div>
            </div>
          ) : null}
      </>
    </div>
  );
};

export default ChatPanel;
