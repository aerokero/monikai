import React from 'react';
import { FileText } from 'lucide-react';
import NoteWorkspace from '../NoteWorkspace';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import useElementSize from '../../hooks/useElementSize';

const NotesShellPanel = ({ socket }) => {
  const [panelRef, panelSize] = useElementSize();

  return (
    <ShellPanelFrame
      icon={FileText}
      title="Notes"
      bodyClassName="min-h-0"
    >
      <div ref={panelRef} className="h-full min-h-0 p-3">
        <div className="h-full min-h-0 overflow-hidden rounded-[18px] border border-white/10 bg-black/20">
          <NoteWorkspace
            socket={socket}
            defaultPath="notes.md"
            compact={panelSize.width > 0 && panelSize.width < 900}
            hidePaths
            shellMode
            shellWidth={panelSize.width}
          />
        </div>
      </div>
    </ShellPanelFrame>
  );
};

export default NotesShellPanel;
