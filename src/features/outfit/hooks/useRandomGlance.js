import { useEffect, useRef, useState } from 'react';

export const useRandomGlance = () => {
  const [randomGlance, setRandomGlance] = useState(null);
  const cycleTimeoutRef = useRef(null);
  const resetTimeoutRef = useRef(null);

  useEffect(() => {
    const triggerGlance = () => {
      const roll = Math.random();
      if (roll < 0.3) {
        setRandomGlance('left');
        resetTimeoutRef.current = setTimeout(() => setRandomGlance(null), Math.random() * 1000 + 800);
      } else if (roll < 0.6) {
        setRandomGlance('right');
        resetTimeoutRef.current = setTimeout(() => setRandomGlance(null), Math.random() * 1000 + 800);
      }
      cycleTimeoutRef.current = setTimeout(triggerGlance, Math.random() * 5000 + 4000);
    };

    cycleTimeoutRef.current = setTimeout(triggerGlance, 5000);
    return () => {
      if (cycleTimeoutRef.current) clearTimeout(cycleTimeoutRef.current);
      if (resetTimeoutRef.current) clearTimeout(resetTimeoutRef.current);
    };
  }, []);

  return randomGlance;
};
