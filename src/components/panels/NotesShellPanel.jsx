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
      icon={null}
      title={t('tools.notes') || 'Notes'}
      titleClassName="font-serif text-[28px] text-[#f5e6d3] font-normal tracking-wide py-1"
      headerClassName="flex items-start justify-between gap-4 border-b border-[#2c1e15] bg-transparent px-6 pt-6 pb-4"
      bodyClassName="flex flex-col h-full overflow-hidden"
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
