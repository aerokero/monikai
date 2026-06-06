import React from 'react';
import { X, FileText } from './icons';
import { useLanguage } from '../contexts/LanguageContext';
import NoteWorkspace from './NoteWorkspace';

const NotesWindow = ({
  socket,
  onClose,
  position,
  onMouseDown,
  activeDragElement,
  zIndex,
  width = 620,
  height = 640,
  embedded = false,
}) => {
  const { t } = useLanguage();

  return (
    <div
      id="notes"
      className={`${embedded ? 'monika-embedded-panel' : 'absolute'} flex flex-col transition-[box-shadow,border-color] duration-200
        backdrop-blur-2xl bg-black/55 border border-white/[0.14] shadow-2xl overflow-hidden rounded-xl
        ${activeDragElement === 'notes' ? 'ring-1 ring-white/50 border-white/30' : ''}
      `}
      style={embedded ? undefined : {
        left: position.x,
        top: position.y,
        transform: 'translate(-50%, -50%)',
        width,
        height,
        pointerEvents: 'auto',
        zIndex,
      }}
      onMouseDown={embedded ? undefined : onMouseDown}
    >
      <div
        className={`flex items-center justify-between p-4 border-b border-white/10 bg-white/5 shrink-0 ${embedded ? '' : 'cursor-grab active:cursor-grabbing'}`}
        data-drag-handle={embedded ? undefined : true}
      >
        <div className="flex items-center gap-3">
          <FileText size={18} className="text-white" />
          <span className="text-sm font-medium tracking-wider text-white/90 uppercase">{t('notes.title')}</span>
        </div>
        {!embedded && (
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-red-500/20 hover:text-red-400 rounded-lg text-white/50 transition-colors"
          >
            <X size={16} />
          </button>
        )}
      </div>

      <div className="flex-1 min-h-0">
        <NoteWorkspace
          socket={socket}
          defaultPath="notes.md"
        />
      </div>
    </div>
  );
};

export default NotesWindow;
