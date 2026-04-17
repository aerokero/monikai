/**
 * MonikaShell Component
 * New primary UI shell that wraps MonikaLayout and integrates VN background layer
 * Replaces AdaptiveShell as the main container for the Monika-First Adaptive UI
 */

import React from 'react';
import Visualizer from '../components/Visualizer';
import MonikaLayout from './MonikaLayout';
import ScreenWindow from '../components/ScreenWindow';
import CameraWindow from '../components/CameraWindow';

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
  toggleVideo = () => {},
}) => {
  return (
    <div className="monika-shell h-screen w-screen bg-black text-white/85 overflow-hidden relative">
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
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-15 mix-blend-overlay" />
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
    </div>
  );
};

export default MonikaShell;
