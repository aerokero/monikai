import { useCallback, useEffect, useRef, useState } from 'react';

export const useHeadpat = (durationMs = 2200) => {
  const [headpatActive, setHeadpatActive] = useState(false);
  const headpatTimerRef = useRef(null);

  const triggerHeadpat = useCallback(() => {
    setHeadpatActive(true);
    if (headpatTimerRef.current) {
      clearTimeout(headpatTimerRef.current);
    }
    headpatTimerRef.current = setTimeout(() => {
      setHeadpatActive(false);
    }, durationMs);
  }, [durationMs]);

  useEffect(() => {
    return () => {
      if (headpatTimerRef.current) {
        clearTimeout(headpatTimerRef.current);
      }
    };
  }, []);

  return { headpatActive, triggerHeadpat };
};
