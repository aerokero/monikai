/**
 * AnalyticsPanel Component
 * Memory, mood, and usage insights
 */

import React from 'react';
import PanelHeader from '../shared/PanelHeader';
import PanelContent from '../shared/PanelContent';
import { BarChart3 } from 'lucide-react';

const AnalyticsPanel = ({ socket = null }) => {
  const stats = [
    { label: 'Messages', value: '24' },
    { label: 'Study Time', value: '2.5h' },
    { label: 'Tasks Done', value: '8' },
    { label: 'Mood', value: '7.2/10' },
  ];

  const weekData = [
    { day: 'Mon', val: 65 },
    { day: 'Tue', val: 72 },
    { day: 'Wed', val: 68 },
    { day: 'Thu', val: 81 },
    { day: 'Fri', val: 75 },
    { day: 'Sat', val: 70 },
    { day: 'Sun', val: 78 },
  ];

  const maxVal = Math.max(...weekData.map(d => d.val));

  return (
    <div className="h-full flex flex-col bg-black/20">
      <PanelHeader
        title="Analytics"
        subtitle="Insights and data"
        icon={BarChart3}
        collapsible
      />
      <PanelContent>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-2">
            {stats.map((stat, idx) => (
              <div key={idx} className="p-2 rounded bg-white/5 border border-white/10">
                <div className="text-xs text-white/60">{stat.label}</div>
                <div className="font-bold text-white">{stat.value}</div>
              </div>
            ))}
          </div>
          <div className="p-2 rounded bg-white/5 border border-white/10">
            <div className="flex items-end justify-between h-12 gap-1">
              {weekData.map((day, idx) => (
                <div key={idx} className="flex-1 flex flex-col items-center">
                  <div
                    className="w-full bg-cyan-500 rounded-t"
                    style={{ height: `${(day.val / maxVal) * 45}px` }}
                  />
                  <div className="text-xs text-white/40">{day.day}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </PanelContent>
    </div>
  );
};

export default AnalyticsPanel;
