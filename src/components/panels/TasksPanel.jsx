/**
 * TasksPanel Component
 * Goal and task management
 * Displays active goals, tasks, and progress
 */

import React, { useState } from 'react';
import PanelHeader from '../shared/PanelHeader';
import PanelContent from '../shared/PanelContent';
import { CheckSquare } from 'lucide-react';

const TasksPanel = ({ socket = null }) => {
  const [tasks] = useState([
    { id: 1, title: 'Complete daily standup', completed: false },
    { id: 2, title: 'Review project timeline', completed: true },
    { id: 3, title: 'Prepare presentation', completed: false },
  ]);

  const completedCount = tasks.filter(t => t.completed).length;
  const progress = (completedCount / tasks.length) * 100;

  return (
    <div className="h-full flex flex-col bg-black/20">
      <PanelHeader
        title="Tasks & Goals"
        subtitle={`${completedCount}/${tasks.length} completed`}
        icon={CheckSquare}
        collapsible
      />
      <PanelContent>
        <div className="space-y-3 text-sm">
          <div className="h-2 rounded-full bg-white/10">
            <div 
              className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full" 
              style={{ width: `${progress}%` }}
            />
          </div>
          {tasks.map(task => (
            <div key={task.id} className="flex items-center gap-2 p-2 rounded bg-white/5">
              <input type="checkbox" checked={task.completed} readOnly className="w-4 h-4" />
              <span className={task.completed ? 'text-white/40 line-through' : 'text-white/80'}>{task.title}</span>
            </div>
          ))}
        </div>
      </PanelContent>
    </div>
  );
};

export default TasksPanel;
