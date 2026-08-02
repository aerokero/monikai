// Used by ChatPanel's attach/quick-action menu (companion center was removed
// 2026-08-02; this used to also be shared with its "Activities" tab).
export function createCompanionAction({
  t,
  socket,
  eatTogetherActive,
  onStartEatTogether,
  onStopEatTogether,
  onHeadpat,
}) {
  return (action) => {
    let text = '';
    switch (action) {
      case 'eat':
        if (eatTogetherActive) {
          if (onStopEatTogether) onStopEatTogether();
          text = t('companion.activities.eat_stop_message');
        } else {
          if (onStartEatTogether) onStartEatTogether();
          text = t('companion.activities.eat_start_message');
        }
        break;
      case 'headpat':
        text = t('companion.activities.headpat_message');
        if (onHeadpat) onHeadpat();
        break;
      case 'gift': {
        const gift = prompt(t('companion.activities.gift_prompt'));
        if (gift) text = t('companion.activities.gift_message', { gift });
        break;
      }
      default:
        return;
    }
    if (text && socket) {
      socket.emit('user_input', { text });
    }
  };
}
