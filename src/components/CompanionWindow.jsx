import React, { useEffect, useState } from 'react';
import { Zap, Heart, Utensils, Gift, Smile, Book, ClipboardList, Coffee, Gamepad2 } from './icons';
import { useLanguage } from '../contexts/LanguageContext';
import ShellPanelFrame from './shared/ShellPanelFrame';
import { SegmentedTabs, ListContainer, ListRow, Badge } from './shared/panelPrimitives';

const CompanionWindow = ({
  socket,
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
  onToggleMinecraft,
  showMinecraftWindow,
  allowMinecraft = true,
}) => {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState('activities');

  const handleAction = (action) => {
    let text = '';
    switch (action) {
      case 'eat':
        if (eatTogetherActive) {
          if (onStopEatTogether) onStopEatTogether();
          text = t('companion.activities.eat_stop_message');
        } else {
          if (onStartEatTogether) onStartEatTogether();
          text = t('companion.activities.eat_start_message');
        }
        break;
      case 'headpat':
        text = t('companion.activities.headpat_message');
        if (onHeadpat) onHeadpat();
        break;
      case 'gift': {
        const gift = prompt(t('companion.activities.gift_prompt'));
        if (gift) text = t('companion.activities.gift_message', { gift });
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
    <ShellPanelFrame icon={Zap} title={t('companion.title')}>
      <div className="border-b border-[#2c1e15] px-6 pb-4">
        <SegmentedTabs
          value={activeTab}
          onChange={setActiveTab}
          options={[
            { value: 'session', label: t('companion.tabs.session'), icon: ClipboardList },
            { value: 'activities', label: t('companion.tabs.activities'), icon: Smile },
            { value: 'study', label: t('companion.tabs.study'), icon: Book },
          ]}
        />
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar">
        {activeTab === 'session' ? (
          <ListContainer>
            <ListRow
              icon={Coffee}
              title={sessionLabel}
              description={sessionActive ? t('companion.session.end_desc') : t('companion.session.start_desc')}
              onClick={() => {
                if (onToggleSession) onToggleSession();
              }}
              trailing={sessionActive ? <Badge tone="green">{t('common.active')}</Badge> : null}
              showChevron={!sessionActive}
            />
          </ListContainer>
        ) : null}

        {activeTab === 'activities' ? (
          <ListContainer>
            <ListRow
              icon={Utensils}
              title={t('companion.activities.eat')}
              description={t('companion.activities.eat_desc')}
              onClick={() => handleAction('eat')}
              trailing={eatTogetherActive ? <Badge tone="green">{t('common.active')}</Badge> : null}
              showChevron={!eatTogetherActive}
            />
            <ListRow
              icon={Heart}
              title={t('companion.activities.headpat')}
              description={t('companion.activities.headpat_desc')}
              onClick={() => handleAction('headpat')}
              showChevron
            />
            <ListRow
              icon={Gift}
              title={t('companion.activities.gift')}
              description={t('companion.activities.gift_desc')}
              onClick={() => handleAction('gift')}
              showChevron
            />
            {allowMinecraft && (
              <ListRow
                icon={Gamepad2}
                title={t('companion.activities.minecraft')}
                description={t('companion.activities.minecraft_desc')}
                onClick={() => {
                  if (onToggleMinecraft) onToggleMinecraft();
                }}
                trailing={showMinecraftWindow ? <Badge tone="green">{t('common.active')}</Badge> : null}
                showChevron={!showMinecraftWindow}
              />
            )}
          </ListContainer>
        ) : null}

        {activeTab === 'study' ? (
          <ListContainer>
            <ListRow
              icon={Book}
              title={t('companion.study.japanese_together')}
              description={t('companion.study.desc')}
              onClick={openSelectedStudy}
              showChevron
            />
          </ListContainer>
        ) : null}
      </div>
    </ShellPanelFrame>
  );
};

export default CompanionWindow;
