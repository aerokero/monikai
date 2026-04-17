import { useEffect, useRef, useState } from 'react';

export const useRandomPose = (aiSpeaking) => {
  const [randomPose, setRandomPose] = useState(null);
  const aiSpeakingRef = useRef(aiSpeaking);
  const cycleTimeoutRef = useRef(null);
  const resetTimeoutRef = useRef(null);

  useEffect(() => {
    aiSpeakingRef.current = aiSpeaking;
  }, [aiSpeaking]);

  useEffect(() => {
    const triggerPose = () => {
      const isSpeaking = aiSpeakingRef.current;
      const roll = Math.random();

      if (isSpeaking) {
        if (roll < 0.5) {
          setRandomPose('restpoint');
          resetTimeoutRef.current = setTimeout(() => setRandomPose(null), Math.random() * 3000 + 3000);
        } else if (roll < 0.7) {
          setRandomPose('point');
          resetTimeoutRef.current = setTimeout(() => setRandomPose(null), Math.random() * 2000 + 2000);
        } else {
          setRandomPose(null);
        }
        cycleTimeoutRef.current = setTimeout(triggerPose, Math.random() * 3000 + 2000);
      } else {
        if (roll < 0.2) {
          setRandomPose('crossed');
          resetTimeoutRef.current = setTimeout(() => setRandomPose(null), Math.random() * 5000 + 5000);
        } else if (roll < 0.9) {
          setRandomPose('steepling');
          resetTimeoutRef.current = setTimeout(() => setRandomPose(null), Math.random() * 5000 + 5000);
        } else {
          setRandomPose(null);
        }
        cycleTimeoutRef.current = setTimeout(triggerPose, Math.random() * 5000 + 5000);
      }
    };

    cycleTimeoutRef.current = setTimeout(triggerPose, 2000);
    return () => {
      if (cycleTimeoutRef.current) clearTimeout(cycleTimeoutRef.current);
      if (resetTimeoutRef.current) clearTimeout(resetTimeoutRef.current);
    };
  }, []);

  return randomPose;
};
