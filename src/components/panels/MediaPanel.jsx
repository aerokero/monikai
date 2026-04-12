/**
 * MediaPanel Component
 * Entertainment and media browsing
 * Combines Browser, Minecraft, Visual Novel scenes
 */

import React, { useState } from 'react';
import PanelHeader from '../shared/PanelHeader';
import PanelContent from '../shared/PanelContent';
import { Gamepad2, Play } from 'lucide-react';

const MediaPanel = ({ socket = null }) => {
  const [activeTab, setActiveTab] = useState('media');

  const mediaItems = [
    { title: 'Study Music', subtitle: 'Lo-Fi Beats' },
    { title: 'Gaming Session', subtitle: 'Minecraft' },
    { title: 'VN Scene', subtitle: 'Welcome back' },
  ];

  return (
    <div className="h-full flex flex-col bg-black/20">
      <PanelHeader
        title="Media"
        subtitle="Browser, games, stories"
        icon={Gamepad2}
        collapsible
      />
      <PanelContent>
        <div className="space-y-2 text-sm">
          <div className="flex gap-2 border-b border-white/10 pb-2">
            {['media', 'games', 'scenes'].map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  activeTab === tab ? 'bg-cyan-500 text-white' : 'text-white/60'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
          {mediaItems.map((item, idx) => (
            <div key={idx} className="p-2 rounded bg-white/5 hover:bg-white/10 cursor-pointer flex justify-between items-center text-xs">
              <div>
                <div className="font-medium text-white">{item.title}</div>
                <div className="text-white/60">{item.subtitle}</div>
              </div>
              <Play size={14} className="text-white/40" />
            </div>
          ))}
        </div>
      </PanelContent>
    </div>
  );
};

export default MediaPanel;
