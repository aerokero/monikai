/**
 * CommsPanel Component
 * Communications hub - messaging and notifications
 */

import React from 'react';
import PanelHeader from '../shared/PanelHeader';
import PanelContent from '../shared/PanelContent';
import { MessageSquare, Bell, Clock } from 'lucide-react';

const CommsPanel = ({ socket = null }) => {
  const reminders = [
    { text: 'Standup in 10 min', time: '10:00 AM', read: false },
    { text: 'Lunch break', time: '12:30 PM', read: true },
    { text: 'Meditation session', time: '6:00 PM', read: true },
  ];

  const unread = reminders.filter(r => !r.read).length;

  return (
    <div className="h-full flex flex-col bg-black/20">
      <PanelHeader
        title="Communications"
        subtitle={unread > 0 ? `${unread} new` : 'All caught up'}
        icon={MessageSquare}
        collapsible
      />
      <PanelContent>
        <div className="space-y-2 text-sm">
          <div className="text-xs font-semibold text-white/70 flex items-center gap-1">
            <Bell size={12} />
            Reminders
          </div>
          {reminders.map((r, idx) => (
            <div
              key={idx}
              className={`p-2 rounded-lg border transition-colors ${
                r.read ? 'bg-white/5 border-white/10' : 'bg-cyan-500/10 border-cyan-500/30'
              }`}
            >
              <div className="flex justify-between items-start">
                <span className="text-white">{r.text}</span>
                {!r.read && <div className="w-2 h-2 rounded-full bg-cyan-400" />}
              </div>
              <div className="text-xs text-white/50 mt-0.5">{r.time}</div>
            </div>
          ))}
        </div>
      </PanelContent>
    </div>
  );
};

export default CommsPanel;
