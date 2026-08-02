import React from 'react';
import { FileText } from '../icons';
import NoteWorkspace from '../NoteWorkspace';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import useElementSize from '../../hooks/useElementSize';
import { useLanguage } from '../../contexts/LanguageContext';

const NotesShellPanel = ({ socket }) => {
  const [panelRef, panelSize] = useElementSize();
  const { t } = useLanguage();

  return (
    <ShellPanelFrame
      icon={FileText}
      title={t('tools.notes') || 'Notes'}
    >
      <div ref={panelRef} className="flex-1 min-h-0 overflow-hidden">
        <NoteWorkspace
          socket={socket}
          defaultPath="notes.md"
          compact={panelSize.width > 0 && panelSize.width < 900}
          hidePaths
          shellMode
          shellWidth={panelSize.width}
        />
      </div>
    </ShellPanelFrame>
  );
};

export default NotesShellPanel;
