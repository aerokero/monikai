import React, { createContext, useContext } from 'react';

const AudioVideoContext = createContext();

export const AudioVideoProvider = ({ 
  children,
  isMuted,
  toggleMute,
  isVideoOn,
  toggleVideo,
  visionMode,
  toggleScreenCapture,
  isConnected,
  togglePower,
  onLogout,
  onMonikaTemporaryMood
}) => {
  const value = {
    isMuted,
    toggleMute,
    isVideoOn,
    toggleVideo,
    visionMode,
    toggleScreenCapture,
    isConnected,
    togglePower,
    onLogout,
    onMonikaTemporaryMood,
  };

  return (
    <AudioVideoContext.Provider value={value}>
      {children}
    </AudioVideoContext.Provider>
  );
};

export const useAudioVideo = () => {
  const context = useContext(AudioVideoContext);
  if (!context) {
    throw new Error('useAudioVideo must be used within AudioVideoProvider');
  }
  return context;
};

export default AudioVideoContext;
