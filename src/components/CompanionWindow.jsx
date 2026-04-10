import React, { useEffect, useState } from 'react';
import { Heart, Utensils, Gift, Smile, Book, X, ClipboardList, Coffee, Gamepad2 } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const TabButton = ({ active, icon: Icon, label, onClick }) => (
  <button
    onClick={onClick}
    className={`flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200 ${
      active
        ? 'border border-white/20 bg-white/15 text-white'
        : 'border border-white/10 bg-black/20 text-white/60 hover:bg-white/10 hover:text-white'
    }`}
  >
    <Icon size={14} />
    <span>{label}</span>
  </button>
);

const Surface = ({ children, className = '' }) => (
  <div className={`rounded-xl border border-white/10 bg-black/20 ${className}`}>
    {children}
  </div>
);

const ActionTile = ({ icon: Icon, title, description, onClick, accentClass, wide = false, trailing = null }) => (
  <button
    onClick={onClick}
    className={`group rounded-xl border border-white/10 bg-black/20 p-5 text-left transition-all hover:-translate-y-0.5 hover:border-white/20 hover:bg-white/10 ${wide ? 'col-span-2' : ''}`}
  >
    <div className="flex items-start gap-4">
      <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl transition-colors ${accentClass}`}>
        <Icon size={22} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-semibold text-white">{title}</div>
          {trailing}
        </div>
        <div className="mt-1 text-xs leading-relaxed text-white/45">{description}</div>
      </div>
    </div>
  </button>
);

const CompanionWindow = ({
  socket,
  onClose,
  position,
  onMouseDown,
  activeDragElement,
  zIndex,
  studyCatalog,
  studySelection,
  onOpenStudy,
  onShowStudy,
  onHeadpat,
  sessionActive,
  onToggleSession,
  eatTogetherActive,
  onStartEatTogether,
  onStopEatTogether,
  personalityState,
  onToggleMinecraft,
  showMinecraftWindow,
  width = 760,
  height = 700,
  embedded = false,
  allowMinecraft = true,
}) => {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState('session');
  const isWide = width >= 700;

  const handleAction = (action) => {
    let text = '';
    switch (action) {
      case 'eat':
        if (eatTogetherActive) {
          if (onStopEatTogether) onStopEatTogether();
          text = "That was nice. Let's wrap up our little meal together.";
        } else {
          if (onStartEatTogether) onStartEatTogether();
          text = "Let's eat together for a bit. I want something cozy and low-key.";
        }
        break;
      case 'headpat':
        text = 'headpat for you';
        if (onHeadpat) onHeadpat();
        break;
      case 'gift': {
        const gift = prompt(t('companion.activities.gift_prompt'));
        if (gift) text = `I brought you a little gift: ${gift}.`;
        break;
      }
      default:
        return;
    }
    if (text) {
      socket.emit('user_input', { text });
    }
  };

  const folders = Array.isArray(studyCatalog?.folders) ? studyCatalog.folders : [];
  const [selectedFolder, setSelectedFolder] = useState(studySelection?.folder || '');
  const [selectedFile, setSelectedFile] = useState(studySelection?.file || '');

  useEffect(() => {
    if (studySelection?.folder) setSelectedFolder(studySelection.folder);
    if (studySelection?.file) setSelectedFile(studySelection.file);
  }, [studySelection?.folder, studySelection?.file]);

  const activeFolder = folders.find((f) => f.name === selectedFolder) || folders[0];
  const visibleFiles = activeFolder ? (activeFolder.files || []).filter((f) => !f.is_answer_key) : [];

  useEffect(() => {
    if (!selectedFolder && activeFolder) {
      setSelectedFolder(activeFolder.name);
    }
  }, [selectedFolder, activeFolder]);

  useEffect(() => {
    if (!selectedFile && visibleFiles.length > 0) {
      setSelectedFile(visibleFiles[0].name);
    }
  }, [selectedFile, visibleFiles]);

  const openSelectedStudy = () => {
    const folder = activeFolder;
    const fileName = selectedFile || visibleFiles[0]?.name || '';
    if (!folder || !fileName) return;
    const fileEntry = (folder.files || []).find((f) => f.name === fileName);
    if (fileEntry && onOpenStudy) {
      onOpenStudy({ folder: folder.name, file: fileEntry.name, path: fileEntry.path });
      if (onShowStudy) onShowStudy();
    }
  };

  const sessionLabel = sessionActive ? t('companion.session.end') : t('companion.session.start');

  return (
    <div
      id="companion"
      className={`${embedded ? 'monika-embedded-panel' : 'absolute'} flex flex-col overflow-hidden rounded-xl border border-white/[0.14] bg-black/55 backdrop-blur-2xl shadow-2xl transition-[box-shadow,border-color] duration-200 ${
        activeDragElement === 'companion' ? 'ring-1 ring-white/50 border-white/30' : ''
      }`}
      style={embedded ? undefined : {
        width,
        height,
        left: position.x,
        top: position.y,
        transform: 'translate(-50%, -50%)',
        zIndex,
      }}
      onMouseDown={embedded ? undefined : onMouseDown}
    >
      <div
        className={`relative border-b border-white/10 bg-white/5 px-4 py-4 handle ${embedded ? '' : 'cursor-grab active:cursor-grabbing'}`}
        data-drag-handle={embedded ? undefined : true}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/8 text-white ring-1 ring-white/10">
              <Heart size={16} />
            </div>
            <div className="text-sm font-medium tracking-wider text-white/90 uppercase">{t('companion.title')}</div>
          </div>
          {!embedded && (
            <button onClick={onClose} className="rounded-lg p-1.5 text-white/50 transition-colors hover:bg-red-500/20 hover:text-red-400">
              <X size={15} />
            </button>
          )}
        </div>
      </div>

      <div className="border-b border-white/10 bg-black/10 px-4 py-3">
        <div className="grid grid-cols-3 gap-2">
          <TabButton active={activeTab === 'session'} icon={ClipboardList} label={t('companion.tabs.session')} onClick={() => setActiveTab('session')} />
          <TabButton active={activeTab === 'activities'} icon={Smile} label={t('companion.tabs.activities')} onClick={() => setActiveTab('activities')} />
          <TabButton active={activeTab === 'study'} icon={Book} label={t('companion.tabs.study')} onClick={() => setActiveTab('study')} />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {activeTab === 'session' ? (
          <div className="grid grid-cols-1 gap-4">
            <ActionTile
              icon={Coffee}
              title={sessionLabel}
              description={sessionActive ? t('companion.session.end_desc') : t('companion.session.start_desc')}
              onClick={() => {
                if (onToggleSession) onToggleSession();
              }}
              accentClass={sessionActive ? 'bg-amber-500/28 text-amber-200' : 'bg-amber-500/14 text-amber-300 group-hover:bg-amber-500/24'}
            />
          </div>
        ) : null}

        {activeTab === 'activities' ? (
          <div className="grid grid-cols-2 gap-4">
            <ActionTile
              icon={Utensils}
              title={t('companion.activities.eat')}
              description={t('companion.activities.eat_desc')}
              onClick={() => handleAction('eat')}
              accentClass={eatTogetherActive ? 'bg-orange-500/28 text-orange-200' : 'bg-orange-500/18 text-orange-300 group-hover:bg-orange-500/28'}
              trailing={
                eatTogetherActive ? (
                  <span className="rounded-full border border-orange-300/20 bg-orange-300/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-orange-100/80">
                    Active
                  </span>
                ) : null
              }
            />
            <ActionTile
              icon={Heart}
              title={t('companion.activities.headpat')}
              description={t('companion.activities.headpat_desc')}
              onClick={() => handleAction('headpat')}
              accentClass="bg-pink-500/18 text-pink-300 group-hover:bg-pink-500/28"
            />
            <ActionTile
              icon={Gift}
              title={t('companion.activities.gift')}
              description={t('companion.activities.gift_desc')}
              onClick={() => handleAction('gift')}
              accentClass="bg-violet-500/18 text-violet-300 group-hover:bg-violet-500/28"
              wide
            />
            {allowMinecraft && (
              <ActionTile
                icon={Gamepad2}
                title={t('companion.activities.minecraft') || 'Minecraft'}
                description={t('companion.activities.minecraft_desc') || 'Open the Minecraft companion activity panel.'}
                onClick={() => {
                  if (onToggleMinecraft) onToggleMinecraft();
                }}
                accentClass={showMinecraftWindow ? 'bg-emerald-500/28 text-emerald-200' : 'bg-emerald-500/18 text-emerald-300 group-hover:bg-emerald-500/28'}
                trailing={
                  showMinecraftWindow ? (
                    <span className="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-emerald-100/80">
                      Active
                    </span>
                  ) : null
                }
                wide={isWide}
              />
            )}
          </div>
        ) : null}

        {activeTab === 'study' ? (
          <div className="grid gap-4">
            <ActionTile
              icon={Book}
              title={t('companion.study.japanese_together')}
              description={t('companion.study.desc')}
              onClick={openSelectedStudy}
              accentClass="bg-cyan-500/18 text-cyan-200 group-hover:bg-cyan-500/28"
            />
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default CompanionWindow;
