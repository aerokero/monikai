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
      bg-[rgba(24,17,12,0.58)] backdrop-blur-lg
      border-b border-[rgba(232,178,102,0.14)]
      text-sm
    ">
      {/* Left: Context Info */}
      <div className="flex items-center gap-3">
        {panel && (
          <>
            <div className="text-[rgba(255,240,218,0.68)]">
              <span className="font-medium text-[rgba(255,246,233,0.94)]">
                {t('panels.' + panel.id)}
              </span>
              <span className="text-[rgba(232,178,102,0.36)] mx-2">•</span>
              <span className="text-[rgba(255,224,190,0.46)]">
                {panel.description}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Right: Time */}
      <div className="text-[rgba(255,224,190,0.5)] font-mono text-xs">
        {currentTime}
      </div>
    </div>
  );
};

export default ContextBar;
