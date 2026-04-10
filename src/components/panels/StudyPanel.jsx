/**
 * StudyPanel Component
 * Academic learning and practice
 * Displays study materials and progress
 */

import React, { useState } from 'react';
import PanelHeader from '../shared/PanelHeader';
import PanelContent from '../shared/PanelContent';
import { BookOpen, Folder } from 'lucide-react';

const StudyPanel = ({ socket = null }) => {
  const [selectedFolder, setSelectedFolder] = useState(null);
  
  const folders = [
    { id: 1, name: 'Genki 1', files: 3, progress: 65 },
    { id: 2, name: 'Genki 2', files: 5, progress: 42 },
    { id: 3, name: 'Kanji', files: 2, progress: 88 },
  ];

  return (
    <div className="h-full flex flex-col bg-black/20">
      <PanelHeader
        title="Study"
        subtitle="Learning materials"
        icon={BookOpen}
        collapsible
      />
      <PanelContent>
        <div className="space-y-2 text-sm">
          {folders.map(folder => (
            <div
              key={folder.id}
              onClick={() => setSelectedFolder(folder.id)}
              className={`p-2.5 rounded-lg cursor-pointer transition-colors ${
                selectedFolder === folder.id ? 'bg-cyan-500/20' : 'bg-white/5 hover:bg-white/10'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Folder size={14} className="text-cyan-400" />
                <span>{folder.name}</span>
              </div>
              <div className="h-1 rounded-full bg-white/10">
                <div className="h-full bg-teal-500 rounded-full" style={{ width: `${folder.progress}%` }} />
              </div>
              <div className="text-xs text-white/50 mt-1">{folder.progress}%</div>
            </div>
          ))}
        </div>
      </PanelContent>
    </div>
  );
};

export default StudyPanel;
