/**
 * PanelRouter Component
 * Dynamically renders the correct panel based on activeContext
 * Passes shared state (chat, socket, etc) to panels
 */

import React from 'react';
import { useMonika } from '../../contexts/MonikaContext';
import { useLanguage } from '../../contexts/LanguageContext';
import ChatPanel from './ChatPanel';
import StudyShellPanel from './StudyShellPanel';
import NotesShellPanel from './NotesShellPanel';
import CalendarShellPanel from './CalendarShellPanel';
import ProfileShellPanel from './ProfileShellPanel';
import SettingsPanel from './SettingsPanel';
import ConversationsShellPanel from './ConversationsShellPanel';
import WorldsShellPanel from './WorldsShellPanel';
import ResearchShellPanel from './ResearchShellPanel';
import DocsShellPanel from './DocsShellPanel';

const PANEL_COMPONENTS = {
  chat: ChatPanel,
  conversations: ConversationsShellPanel,
  worlds: WorldsShellPanel,
  study: StudyShellPanel,
  notes: NotesShellPanel,
  docs: DocsShellPanel,
  research: ResearchShellPanel,
  calendar: CalendarShellPanel,
  profile: ProfileShellPanel,
  settings: SettingsPanel,
};

/**
 * PanelRouter
 * Routes to correct panel component based on activeContext
 * Passes shared app state (chat, socket, etc) to all panels
 * 
 * @param {Object} props - Shared state from App
 * @param {Array} props.messages - Chat message history
 * @param {string} props.inputValue - Current chat input
 * @param {Function} props.setInputValue - Update input value
 * @param {Function} props.handleSend - Send message callback
 * @param {Object} props.socket - Socket.io client
 * @param {boolean} props.userSpeaking - Is user currently speaking
 * @param {Object} props.micAudioData - Microphone audio data
 */
const PanelRouter = ({
  messages = [],
  inputValue = '',
  setInputValue = () => {},
  handleSend = () => {},
  socket = null,
  userSpeaking = false,
  micAudioData = null,
  language = 'en',
  studyCatalog = { folders: [] },
  studySelection = { folder: '', file: '', path: '' },
  onSelectStudy = () => {},
  onRefreshCatalog = () => {},
  shareRef = null,
  excludeChat = true,
  micDevices = [],
  speakerDevices = [],
  webcamDevices = [],
  selectedMicId = '',
  setSelectedMicId = () => {},
  selectedSpeakerId = '',
  setSelectedSpeakerId = () => {},
  selectedWebcamId = '',
  setSelectedWebcamId = () => {},
  isCameraFlipped = false,
  setIsCameraFlipped = () => {},
  toolPermissions = {},
  onTogglePermission = () => {},
  handleFileUpload = () => {},
  skills = [],
  skillsLoading = false,
  skillsActionBusy = false,
  onRefreshSkills = () => {},
  onUploadSkillZip = () => {},
  onInstallSkillSource = () => {},
  onUninstallSkill = () => {},
  geminiModelPreset = '2.5',
  onModelPresetChange = () => {},
  geminiVoice = 'Leda',
  onVoiceChange = () => {},
}) => {
  const { activeContext, setActiveContext } = useMonika();
  const { t } = useLanguage();

  // If excludeChat is true and activeContext is chat, show study panel instead
  // (chat is rendered as persistent window in MonikaLayout)
  const panelContext = excludeChat && activeContext === 'chat' ? 'study' : activeContext;
  const PanelComponent = PANEL_COMPONENTS[panelContext];

  if (!PanelComponent) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-white/50 text-sm">{t('errors.panel_not_found', { context: panelContext })}</div>
      </div>
    );
  }

  const sharedProps = (() => {
    switch (panelContext) {
      case 'study':
        return {
          socket,
          catalog: studyCatalog,
          selection: studySelection,
          onSelectStudy,
          onRefreshCatalog,
          shareRef,
        };
      case 'conversations':
        return {
          socket,
          // After "new"/"continue" jump back to the live chat.
          onStarted: () => setActiveContext('chat'),
        };
      case 'worlds':
        return {
          socket,
        };
      case 'notes':
        return {
          socket,
        };
      case 'calendar':
        return {
          socket,
        };
      case 'profile':
      case 'research':
      case 'docs':
        return {
          socket,
        };
      case 'settings':
        return {
          micDevices,
          speakerDevices,
          webcamDevices,
          selectedMicId,
          setSelectedMicId,
          selectedSpeakerId,
          setSelectedSpeakerId,
          selectedWebcamId,
          setSelectedWebcamId,
          isCameraFlipped,
          setIsCameraFlipped,
          toolPermissions,
          onTogglePermission,
          handleFileUpload,
          skills,
          skillsLoading,
          skillsActionBusy,
          onRefreshSkills,
          onUploadSkillZip,
          onInstallSkillSource,
          onUninstallSkill,
          geminiModelPreset,
          onModelPresetChange,
          geminiVoice,
          onVoiceChange,
          socket,
        };
      case 'chat':
      default:
        return {
          messages,
          inputValue,
          setInputValue,
          handleSend,
          socket,
          userSpeaking,
          micAudioData,
        };
    }
  })();

  return (
    <PanelComponent {...sharedProps} />
  );
};

export default PanelRouter;
