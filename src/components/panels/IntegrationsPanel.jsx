/**
 * IntegrationsPanel Component
 * External services and integrations
 * Spotify, Kasa, Calendar, Email
 */

import React, { useState } from 'react';
import PanelHeader from '../shared/PanelHeader';
import PanelContent from '../shared/PanelContent';
import { Zap, Wifi } from 'lucide-react';

const IntegrationsPanel = ({ socket = null }) => {
  const [activeTab, setActiveTab] = useState('services');

  const services = [
    { name: 'Spotify', status: 'connected' },
    { name: 'Gmail', status: 'connected' },
    { name: 'Minecraft', status: 'ready' },
    { name: 'Telegram', status: 'disconnected' },
  ];

  const skills = [
    { name: 'Music Player', enabled: true },
    { name: 'Email Manager', enabled: true },
    { name: 'Weather', enabled: false },
    { name: 'Notes', enabled: true },
  ];

  return (
    <div className="h-full flex flex-col bg-black/20">
      <PanelHeader
        title="Integrations"
        subtitle="Apps and services"
        icon={Zap}
        collapsible
      />
      <PanelContent>
        <div className="space-y-2 text-sm">
          <div className="flex gap-2 border-b border-white/10 pb-2">
            {['services', 'skills'].map(tab => (
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

          {activeTab === 'services' && (
            <div className="space-y-1.5">
              {services.map((svc, idx) => (
                <div key={idx} className="flex justify-between items-center p-2 rounded bg-white/5 text-xs">
                  <div className="flex items-center gap-2">
                    <Wifi size={12} />
                    {svc.name}
                  </div>
                  <span
                    className={`px-1.5 py-0.5 rounded text-xs ${
                      svc.status === 'connected'
                        ? 'bg-green-500/30 text-green-200'
                        : svc.status === 'ready'
                        ? 'bg-blue-500/30 text-blue-200'
                        : 'bg-red-500/30 text-red-200'
                    }`}
                  >
                    {svc.status}
                  </span>
                </div>
              ))}
            </div>
          )}

          {activeTab === 'skills' && (
            <div className="space-y-1.5">
              {skills.map((skill, idx) => (
                <div key={idx} className="flex justify-between items-center p-2 rounded bg-white/5 text-xs">
                  {skill.name}
                  <input type="checkbox" checked={skill.enabled} readOnly />
                </div>
              ))}
            </div>
          )}
        </div>
      </PanelContent>
    </div>
  );
};

export default IntegrationsPanel;
