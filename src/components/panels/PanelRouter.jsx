/**
 * PanelRouter Component
 * Dynamically renders the correct panel based on activeContext
 * Passes shared state (chat, socket, etc) to panels
 */

import React from 'react';
import { useMonika } from '../../contexts/MonikaContext';
import ChatPanel from './ChatPanel';
import CompanionWindow from '../CompanionWindow';
import StudyShellPanel from './StudyShellPanel';
import NotesShellPanel from './NotesShellPanel';
import DailyBriefingShellPanel from './DailyBriefingShellPanel';
import GoalsShellPanel from './GoalsShellPanel';

const PANEL_COMPONENTS = {
  chat: ChatPanel,
  study: StudyShellPanel,
  notes: NotesShellPanel,
  daily_briefing: DailyBriefingShellPanel,
  companion: CompanionWindow,
  goals: GoalsShellPanel,
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
  personalityState = {},
  studyCatalog = { folders: [] },
  studySelection = { folder: '', file: '', path: '' },
  onSelectStudy = () => {},
  onRefreshCatalog = () => {},
  shareRef = null,
  sessionActive = false,
  onToggleSession = () => {},
  eatTogetherActive = false,
  onStartEatTogether = () => {},
  onStopEatTogether = () => {},
  onHeadpat = () => {},
  excludeChat = true,
}) => {
  const { activeContext, setActiveContext } = useMonika();
  
  // If excludeChat is true and activeContext is chat, show study panel instead
  // (chat is rendered as persistent window in MonikaLayout)
  const panelContext = excludeChat && activeContext === 'chat' ? 'study' : activeContext;
  const PanelComponent = PANEL_COMPONENTS[panelContext];

  if (!PanelComponent) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-white/50 text-sm">Panel not found: {panelContext}</div>
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
      case 'notes':
        return {
          socket,
        };
      case 'daily_briefing':
        return {
          socket,
          language,
        };
      case 'companion':
        return {
          socket,
          studyCatalog,
          studySelection,
          onOpenStudy: onSelectStudy,
          onShowStudy: () => setActiveContext('study'),
          onHeadpat,
          sessionActive,
          onToggleSession,
          eatTogetherActive,
          onStartEatTogether,
          onStopEatTogether,
          personalityState,
          allowMinecraft: false,
          embedded: true,
        };
      case 'goals':
        return {
          personalityState,
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
