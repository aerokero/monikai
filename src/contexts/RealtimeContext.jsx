import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

const RealtimeContext = createContext(null);

export const RealtimeProvider = ({ children, socket }) => {
  const [isConnected, setIsConnected] = useState(Boolean(socket?.connected));
  const [lastEvent, setLastEvent] = useState(null);

  useEffect(() => {
    if (!socket) return undefined;

    const handleConnect = () => {
      setIsConnected(true);
      setLastEvent({ type: 'connect', at: Date.now() });
    };

    const handleDisconnect = (reason) => {
      setIsConnected(false);
      setLastEvent({ type: 'disconnect', reason, at: Date.now() });
    };

    const handleAnyEvent = (eventName, payload) => {
      setLastEvent({
        type: eventName,
        at: Date.now(),
        hasPayload: typeof payload !== 'undefined',
      });
    };

    socket.on('connect', handleConnect);
    socket.on('disconnect', handleDisconnect);
    socket.onAny(handleAnyEvent);

    return () => {
      socket.off('connect', handleConnect);
      socket.off('disconnect', handleDisconnect);
      socket.offAny(handleAnyEvent);
    };
  }, [socket]);

  const value = useMemo(
    () => ({
      socket,
      isConnected,
      lastEvent,
    }),
    [socket, isConnected, lastEvent],
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
};

export const useRealtime = () => {
  const ctx = useContext(RealtimeContext);
  if (!ctx) {
    throw new Error('useRealtime must be used inside RealtimeProvider');
  }
  return ctx;
};
