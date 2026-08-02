import React from 'react';
import { Clock } from '../icons';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import ConversationHistory from './ConversationHistory';
import { useLanguage } from '../../contexts/LanguageContext';

// v3 Phase G: full rail panel with the conversation history —
// list of past conversations, stream day-cards, read-only transcripts.
const ConversationsShellPanel = ({ socket, onStarted = () => {} }) => {
  const { t } = useLanguage();

  return (
    <ShellPanelFrame
      icon={Clock}
      title={t('conversations.title') || 'Conversations'}
      bodyClassName="flex flex-col h-full overflow-hidden px-4 py-3"
    >
      <ConversationHistory socket={socket} active variant="shell" onStarted={onStarted} />
    </ShellPanelFrame>
  );
};

export default ConversationsShellPanel;
