/**
 * ContextBar Component
 * Top bar showing current active context, time, and status indicators
 */

import React, { useState, useEffect } from 'react';
import { useMonika } from '../../contexts/MonikaContext';
import { useLanguage } from '../../contexts/LanguageContext';
import { getPanelById } from '../../config/panelRegistry';

const ContextBar = () => {
  const { activeContext } = useMonika();
  const { t } = useLanguage();
  const [currentTime, setCurrentTime] = useState('');
  
  const panel = getPanelById(activeContext);

  // Update time every minute
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(now.toLocaleTimeString('en-US', { 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: true 
      }));
    };
    
    updateTime();
    const interval = setInterval(updateTime, 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="
      monika-context-bar
      context-bar
      flex items-center justify-between
      px-4 py-2
      bg-black/40 backdrop-blur-lg
      border-b border-white/10
      text-sm
    ">
      {/* Left: Context Info */}
      <div className="flex items-center gap-3">
        {panel && (
          <>
            <div className="text-white/70">
              <span className="font-medium text-white/90">
                {t('panels.' + panel.id)}
              </span>
              <span className="text-white/40 mx-2">•</span>
              <span className="text-white/50">
                {panel.description}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Right: Time */}
      <div className="text-white/50 font-mono text-xs">
        {currentTime}
      </div>
    </div>
  );
};

export default ContextBar;
