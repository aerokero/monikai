/**
 * MonikaLayout Component
 * Main responsive layout wrapper for Monika-First Adaptive UI
 * Renders responsive grid based on viewport size
 */

import React, { useMemo, useState } from 'react';
import useLayoutMode from '../hooks/useLayoutMode';
import { useMonika } from '../contexts/MonikaContext';
import { useSettings } from '../contexts/SettingsContext';
import MonikaSprite from './MonikaSprite';
import MASClock from './MASClock';
import RailNav from '../components/shared/RailNav';
import WindowTopBar from '../components/shared/WindowTopBar';
import ContextBar from '../components/shared/ContextBar';
import PanelRouter from '../components/panels/PanelRouter';
import ChatPanel from '../components/panels/ChatPanel';
import '../styles/monika-layout.css';

/**
 * MonikaLayout
 * Root layout container providing responsive grid structure
 * Monika sprite is central, panels adapt around her based on viewport
 *
 * Auto-wires: RailNav, ContextBar, and PanelRouter based on activeContext
 *
 * @component
 * @param {Object} props
 * @param {Object} props.personalityState - Monika personality state from backend
 * @param {Array} props.messages - Chat message history (for panels)
 * @param {string} props.inputValue - Current chat input (for panels)
 * @param {Function} props.setInputValue - Update input value (for panels)
 * @param {Function} props.handleSend - Send message callback (for panels)
 * @param {Object} props.socket - Socket.io client (for panels)
 * @param {boolean} props.userSpeaking - Is user speaking (for panels)
 * @param {Object} props.micAudioData - Microphone audio data (for panels)
 * @returns {React.ReactNode}
 */
const MonikaLayout = ({
  personalityState = {},
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
  onShareStudyPage = () => {},
  agenticLogs = [],
  onChatMinimizedChange = () => {},
  onChatSizeChange = () => {},
  sessionActive = false,
  onToggleSession = () => {},
  eatTogetherActive = false,
  onStartEatTogether = () => {},
  onStopEatTogether = () => {},
  onHeadpat = () => {},
  onToggleMinecraft = () => {},
  showMinecraftWindow = false,
  onOpenStudy = () => {},
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
  const {
    layoutMode,
    monikaConfig,
    viewport
  } = useLayoutMode();

  const { activeContext, setActiveContext } = useMonika();
  const { openSettings } = useSettings();
  const isElectron = typeof window !== 'undefined' && typeof window.require === 'function';

  const [isExpanded, setIsExpanded] = useState(false);

  // CSS class for current layout mode
  const layoutClassName = useMemo(() => {
    return `monika-layout monika-layout--${layoutMode}`;
  }, [layoutMode]);

  // Monika sprite scale based on layout mode
  const monikaScale = useMemo(() => {
    return monikaConfig.scale || 1.0;
  }, [monikaConfig]);

  const chatWindowClassName = useMemo(() => {
    return `monika-chat-window monika-chat-window--${layoutMode}`;
  }, [layoutMode]);

  return (
    <div className={`${layoutClassName} ${isElectron ? 'monika-layout--with-window-topbar' : ''}`}>
      {isElectron && <WindowTopBar />}

      {/* Rail Navigation (Left/Bottom/Top depending on layout) */}
      <RailNav />

      {/* Context Bar (Top, shows current activity) */}
      <ContextBar />

      {/* Main Workspace (Monika + Other Panels) */}
      <div className="monika-workspace" role="main">
        <MASClock personalityState={personalityState} />

        {/* Monika Sprite (Primary focal point) */}
        <div className="monika-sprite-container">
          <MonikaSprite
            scale={monikaScale}
            personalityState={personalityState}
          />
        </div>

        {/* Non-Chat Panel Container (Study, Tasks, Media, etc.) - Hidden when chat is selected */}
        {activeContext !== 'chat' && (
          <div className={`monika-panel-container ${['settings', 'calendar', 'notes'].includes(activeContext) ? 'is-settings' : ''}`} role="region" aria-live="polite" aria-label="Content panel">
            <PanelRouter
              messages={messages}
              inputValue={inputValue}
              setInputValue={setInputValue}
              handleSend={handleSend}
              socket={socket}
              userSpeaking={userSpeaking}
              micAudioData={micAudioData}
              language={language}
              personalityState={personalityState}
              studyCatalog={studyCatalog}
              studySelection={studySelection}
              onSelectStudy={onSelectStudy}
              onRefreshCatalog={onRefreshCatalog}
              shareRef={shareRef}
              sessionActive={sessionActive}
              onToggleSession={onToggleSession}
              eatTogetherActive={eatTogetherActive}
              onStartEatTogether={onStartEatTogether}
              onStopEatTogether={onStopEatTogether}
              onHeadpat={onHeadpat}
              excludeChat={true}
              micDevices={micDevices}
              speakerDevices={speakerDevices}
              webcamDevices={webcamDevices}
              selectedMicId={selectedMicId}
              setSelectedMicId={setSelectedMicId}
              selectedSpeakerId={selectedSpeakerId}
              setSelectedSpeakerId={setSelectedSpeakerId}
              selectedWebcamId={selectedWebcamId}
              setSelectedWebcamId={setSelectedWebcamId}
              isCameraFlipped={isCameraFlipped}
              setIsCameraFlipped={setIsCameraFlipped}
              toolPermissions={toolPermissions}
              onTogglePermission={onTogglePermission}
              handleFileUpload={handleFileUpload}
              skills={skills}
              skillsLoading={skillsLoading}
              skillsActionBusy={skillsActionBusy}
              onRefreshSkills={onRefreshSkills}
              onUploadSkillZip={onUploadSkillZip}
              onInstallSkillSource={onInstallSkillSource}
              onUninstallSkill={onUninstallSkill}
              geminiModelPreset={geminiModelPreset}
              onModelPresetChange={onModelPresetChange}
              geminiVoice={geminiVoice}
              onVoiceChange={onVoiceChange}
            />
          </div>
        )}

        {/* Chat Panel - Persistent Floating Window */}
        <div
          className={`${chatWindowClassName} ${isExpanded ? 'is-expanded' : ''}`}
          role="region"
          aria-label="Chat"
          style={{ transform: 'translateX(-50%)' }}
        >
          <ChatPanel
            messages={messages}
            inputValue={inputValue}
            setInputValue={setInputValue}
            handleSend={handleSend}
            socket={socket}
            userSpeaking={userSpeaking}
            micAudioData={micAudioData}
            isExpanded={isExpanded}
            onToggleExpand={() => setIsExpanded((current) => !current)}
            agenticLogs={agenticLogs}
            studyModeActive={activeContext === 'study'}
            onShareStudyPage={onShareStudyPage}
            onMinimizedChange={onChatMinimizedChange}
            onSizeChange={onChatSizeChange}
            onOpenSettings={() => setActiveContext('settings')}
            onHeadpat={onHeadpat}
            eatTogetherActive={eatTogetherActive}
            onStartEatTogether={onStartEatTogether}
            onStopEatTogether={onStopEatTogether}
            onToggleMinecraft={onToggleMinecraft}
            showMinecraftWindow={showMinecraftWindow}
            sessionActive={sessionActive}
            onToggleSession={onToggleSession}
            onOpenStudy={onOpenStudy}
          />
        </div>
      </div>

      {/* Debug info (development only) */}
      {import.meta.env.DEV && false && (
        <div style={{
          position: 'fixed',
          bottom: 80,
          right: 10,
          fontSize: '10px',
          color: 'rgba(255,255,255,0.3)',
          fontFamily: 'monospace',
          background: 'rgba(0,0,0,0.5)',
          padding: '5px',
          borderRadius: '4px',
          zIndex: 999
        }}>
          <div>Mode: {layoutMode}</div>
          <div>Size: {viewport.width}x{viewport.height}</div>
          <div>Context: {activeContext}</div>
        </div>
      )}
    </div>
  );
};

export default React.memo(MonikaLayout);
