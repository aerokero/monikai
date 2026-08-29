/**
 * MonikaShell Component
 * New primary UI shell that wraps MonikaLayout and integrates VN background layer
 * Replaces AdaptiveShell as the main container for the Monika-First Adaptive UI
 */

import React, { useState, useMemo } from 'react';
import Visualizer from '../components/Visualizer';
import MonikaLayout from './MonikaLayout';
import ScreenWindow from '../components/ScreenWindow';
import CameraWindow from '../components/CameraWindow';
import MiniCompanionWindow from '../components/companion/MiniCompanionWindow';

const MonikaShell = ({
  // Visualizer props (from App)
  audioData,
  intensity,
  width,
  height,
  backgroundSrc,
  layers,
  sprites,
  isAssistantSpeaking,
  isUserSpeaking,
  characterScale,
  characterY,
  characterX,
  characterAnchorBottom,
  characterBottomOffset,
  characterTransitionMs,
  headpatActive,
  petpetSrc,
  // Layout props
  personalityState,
  // Chat/App state (for panels)
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
  visionMode = 'none',
  visionFrame = null,
  toggleScreenCapture = () => {},
  isVideoOn = false,
  videoRef = null,
  isCameraFlipped = false,
  setIsCameraFlipped = () => {},
  toggleVideo = () => {},
  micDevices = [],
  speakerDevices = [],
  webcamDevices = [],
  selectedMicId = '',
  setSelectedMicId = () => {},
  selectedSpeakerId = '',
  setSelectedSpeakerId = () => {},
  selectedWebcamId = '',
  setSelectedWebcamId = () => {},
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
  const [companionMode, setCompanionMode] = useState(() => {
    return localStorage.getItem('monikai_companion_mode') === 'true';
  });

  const toggleCompanionMode = () => {
    setCompanionMode(prev => {
      const next = !prev;
      localStorage.setItem('monikai_companion_mode', String(next));
      return next;
    });
  };

  const lastMonikaMessage = useMemo(() => {
    const assistantMsgs = (messages || []).filter(m => m.sender === 'assistant' || m.sender === 'monika' || m.type === 'model');
    return assistantMsgs.length > 0 ? assistantMsgs[assistantMsgs.length - 1].text : 'Cześć! Jestem Twoim małym towarzyszem na pulpicie~ ✨';
  }, [messages]);

  return (
    <div className={`monika-shell h-screen w-screen ${companionMode ? 'bg-transparent' : 'bg-black'} text-white/85 overflow-hidden relative`}>
      {/* Mini Companion Window Mode */}
      {companionMode ? (
        <MiniCompanionWindow
          onExpandToFull={() => toggleCompanionMode()}
          lastMessage={lastMonikaMessage}
          onSendMessage={handleSend}
          isListening={userSpeaking}
          onToggleMic={() => {}}
          socket={socket}
        />
      ) : (
        <>
          {/* VN FULLSCREEN BACKGROUND + CHARACTER (behind UI) */}
          <div className="fixed inset-0 z-0 pointer-events-none">
            <Visualizer
              audioData={audioData}
              intensity={intensity}
              width={width}
              height={height}
              backgroundSrc={backgroundSrc}
              layers={layers}
              sprites={sprites}
              isAssistantSpeaking={isAssistantSpeaking}
              isUserSpeaking={isUserSpeaking}
              characterScale={characterScale}
              characterY={characterY}
              characterX={characterX}
              characterAnchorBottom={characterAnchorBottom}
              characterBottomOffset={characterBottomOffset}
              characterTransitionMs={characterTransitionMs}
              headpatActive={headpatActive}
              petpetSrc={petpetSrc}
            />
            {/* Subtle VN vignette */}
            <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-black/20 to-black/55" />
          </div>

          {/* NEW MONIKA-FIRST ADAPTIVE UI SHELL */}
          <div className="relative z-10">
            <MonikaLayout
              personalityState={personalityState}
              messages={messages}
              inputValue={inputValue}
              setInputValue={setInputValue}
              handleSend={handleSend}
              socket={socket}
              userSpeaking={userSpeaking}
              micAudioData={micAudioData}
              language={language}
              studyCatalog={studyCatalog}
              studySelection={studySelection}
              onToggleCompanionMode={toggleCompanionMode}
          onSelectStudy={onSelectStudy}
          onRefreshCatalog={onRefreshCatalog}
          shareRef={shareRef}
          onShareStudyPage={onShareStudyPage}
          agenticLogs={agenticLogs}
          onChatMinimizedChange={onChatMinimizedChange}
          onChatSizeChange={onChatSizeChange}
          sessionActive={sessionActive}
          onToggleSession={onToggleSession}
          eatTogetherActive={eatTogetherActive}
          onStartEatTogether={onStartEatTogether}
          onStopEatTogether={onStopEatTogether}
          onHeadpat={onHeadpat}
          onToggleMinecraft={onToggleMinecraft}
          showMinecraftWindow={showMinecraftWindow}
          onOpenStudy={onOpenStudy}
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

        {visionMode === 'screen' && (
          <ScreenWindow
            imageSrc={visionFrame}
            onClose={toggleScreenCapture}
          />
        )}

        {isVideoOn && (
          <CameraWindow
            videoRef={videoRef}
            isCameraFlipped={isCameraFlipped}
            onClose={toggleVideo}
          />
        )}
      </div>
    </>
    )}
  </div>
);
};

export default MonikaShell;
