import React from 'react';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import ConversationHistory from './ConversationHistory';
import { useLanguage } from '../../contexts/LanguageContext';

// v3 Phase G: full rail panel with the conversation history —
// list of past conversations, stream day-cards, read-only transcripts.
const ConversationsShellPanel = ({ socket, onStarted = () => {} }) => {
  const { t } = useLanguage();

  return (
    <ShellPanelFrame
      icon={null}
      title={t('conversations.title') || 'Conversations'}
      titleClassName="font-serif text-[28px] text-[#f5e6d3] font-normal tracking-wide py-1"
      headerClassName="flex items-start justify-between gap-4 border-b border-[#2c1e15] bg-transparent px-6 pt-6 pb-4"
      bodyClassName="flex flex-col h-full overflow-hidden px-4 py-3"
    >
      <ConversationHistory socket={socket} active variant="shell" onStarted={onStarted} />
    </ShellPanelFrame>
  );
};

export default ConversationsShellPanel;
