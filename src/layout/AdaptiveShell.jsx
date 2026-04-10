import React from 'react';
import { useLayout } from '../contexts/LayoutContext';

const AdaptiveShell = ({ children }) => {
  const { viewport, isPortrait } = useLayout();

  return (
    <div
      className="adaptive-shell"
      data-portrait={isPortrait ? 'true' : 'false'}
      style={{ '--viewport-w': `${viewport.width}px`, '--viewport-h': `${viewport.height}px` }}
    >
      <div className="adaptive-shell__atmosphere" aria-hidden="true" />
      <div className="adaptive-shell__content">{children}</div>
    </div>
  );
};

export default AdaptiveShell;
