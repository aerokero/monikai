import { useEffect, useRef, useState } from 'react';

export const useRandomBlink = () => {
  const [isBlinking, setIsBlinking] = useState(false);
  const cycleTimeoutRef = useRef(null);
  const blinkResetTimeoutRef = useRef(null);

  useEffect(() => {
    const triggerBlink = () => {
      setIsBlinking(true);
      blinkResetTimeoutRef.current = setTimeout(() => setIsBlinking(false), 150);
      cycleTimeoutRef.current = setTimeout(triggerBlink, Math.random() * 3000 + 3000);
    };

    cycleTimeoutRef.current = setTimeout(triggerBlink, 3000);
    return () => {
      if (cycleTimeoutRef.current) clearTimeout(cycleTimeoutRef.current);
      if (blinkResetTimeoutRef.current) clearTimeout(blinkResetTimeoutRef.current);
    };
  }, []);

  return isBlinking;
};
